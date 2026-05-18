#!/usr/bin/env python3
"""Emit lossless sprite/image assets at native resolution with deterministic metadata."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


def _load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _default_output(repo_root: Path) -> Path:
    return repo_root / "outputs" / "sprites" / "latest_lossless"


def _normalize_scene_names(scene_args: list[str], default_scenes: list[str]) -> list[str]:
    if not scene_args:
        return list(default_scenes)

    normalized = []
    for scene in scene_args:
        upper = scene.upper()
        if not upper.endswith(".SCN"):
            upper += ".SCN"
        normalized.append(upper)
    return normalized


def _to_rgba_bytes(scene, rec) -> tuple[bytearray, bytearray, int]:
    indexed_pixels, stats = scene.render_wrt_nonzero(rec)
    palette = scene.palette(rec.palette_offset)

    rgba = bytearray()
    for pixel_index in indexed_pixels:
        rgba.extend(palette[pixel_index])

    return indexed_pixels, rgba, stats.consumed_index_bytes


def _save_png_rgba(renderer_mod, width: int, height: int, rgba: bytes, out_path: Path) -> None:
    image_cls = getattr(renderer_mod, "Image", None)
    if image_cls is None:
        raise RuntimeError("Pillow is required for PNG export")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image = image_cls.frombytes("RGBA", (width, height), rgba)
    image.save(out_path)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    refresh_mod = _load_module(
        "refresh_snapshot_baselines_module",
        repo_root / "scripts" / "refresh_snapshot_baselines.py",
    )
    renderer_mod = _load_module(
        "tinsel1_renderer_module_sprite_extract",
        repo_root / "extractor" / "tinsel1_renderer.py",
    )

    parser = argparse.ArgumentParser(description="Extract lossless native-resolution sprite/image PNG assets")
    parser.add_argument("--input", help="Dataset path containing INDEX and SCN files")
    parser.add_argument("--output", help="Output directory (default: outputs/sprites/latest_lossless)")
    parser.add_argument("--scenes", nargs="*", default=[], help="Scene files to process (for example BAR.SCN CLIMAX.SCN)")
    parser.add_argument(
        "--limit-per-scene",
        type=int,
        default=0,
        help="Maximum images per scene (0 means all non-empty images)",
    )
    parser.add_argument(
        "--max-dimension",
        type=int,
        default=0,
        help="Skip images wider or taller than this threshold (0 means no limit)",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete output directory before extraction",
    )
    args = parser.parse_args()

    try:
        dataset_dir = refresh_mod._resolve_dataset_dir(repo_root, args.input)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output).resolve() if args.output else _default_output(repo_root)
    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_names = _normalize_scene_names(args.scenes, refresh_mod.SPRITE_CONTRACT_SCENES)

    manifest_scenes = {}
    total_exported = 0
    total_skipped = 0

    for scene_name in scene_names:
        scene_path = dataset_dir / scene_name
        if not scene_path.exists():
            print(f"warning: missing scene {scene_name}", file=sys.stderr)
            continue

        scene = renderer_mod.Tinsel1Scene(scene_path)
        records = scene.image_records()
        scene_dir = output_dir / scene_name.split(".", 1)[0].lower()
        scene_dir.mkdir(parents=True, exist_ok=True)

        exported = []
        skipped = []
        for rec in records:
            if rec.width <= 0 or rec.height <= 0:
                continue
            if args.max_dimension > 0 and (rec.width > args.max_dimension or rec.height > args.max_dimension):
                skipped.append({"index": rec.index, "width": rec.width, "height": rec.height, "reason": "max_dimension"})
                continue
            if args.limit_per_scene > 0 and len(exported) >= args.limit_per_scene:
                break

            indexed_pixels, rgba, consumed_index_bytes = _to_rgba_bytes(scene, rec)
            png_name = f"{scene_name.split('.', 1)[0].lower()}_{rec.index:04d}_{rec.width}x{rec.height}.png"
            png_path = scene_dir / png_name
            _save_png_rgba(renderer_mod, rec.width, rec.height, bytes(rgba), png_path)

            png_bytes = png_path.read_bytes()
            exported.append(
                {
                    "index": rec.index,
                    "width": rec.width,
                    "height": rec.height,
                    "anim_x": rec.anim_x,
                    "anim_y": rec.anim_y,
                    "bitmap_offset": rec.bitmap_offset,
                    "palette_offset": rec.palette_offset,
                    "pixel_count": rec.width * rec.height,
                    "consumed_index_bytes": consumed_index_bytes,
                    "indexed_sha256": hashlib.sha256(bytes(indexed_pixels)).hexdigest(),
                    "rgba_sha256": hashlib.sha256(bytes(rgba)).hexdigest(),
                    "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
                    "png": png_name,
                }
            )

        scene_manifest = {
            "scene": scene_name,
            "images_available": len([r for r in records if r.width > 0 and r.height > 0]),
            "images_exported": len(exported),
            "images_skipped": len(skipped),
            "exported": exported,
            "skipped": skipped,
        }
        (scene_dir / "manifest.json").write_text(json.dumps(scene_manifest, indent=2) + "\n", encoding="utf-8")

        manifest_scenes[scene_name] = {
            "scene_dir": scene_dir.name,
            "images_available": scene_manifest["images_available"],
            "images_exported": scene_manifest["images_exported"],
            "images_skipped": scene_manifest["images_skipped"],
            "manifest": f"{scene_dir.name}/manifest.json",
        }
        total_exported += len(exported)
        total_skipped += len(skipped)

    manifest = {
        "scope": "lossless sprite/image extraction",
        "dataset": str(dataset_dir),
        "output": str(output_dir),
        "scene_count": len(manifest_scenes),
        "total_images_exported": total_exported,
        "total_images_skipped": total_skipped,
        "scenes": manifest_scenes,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("Extracted lossless sprite/image assets")
    print("Dataset:", dataset_dir)
    print("Output:", output_dir)
    print("Scenes:", ", ".join(sorted(manifest_scenes.keys())))
    print("Images exported:", total_exported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
