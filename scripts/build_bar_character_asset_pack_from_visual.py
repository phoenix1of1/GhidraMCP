#!/usr/bin/env python3
"""Build scene character asset packs from visual manifest film graph.

This converts scene visual film_graph frames into reusable per-film frame PNGs
and writes a pack manifest compatible with validation/bar_composited_sprite_preview.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISUAL_MANIFEST = REPO_ROOT / "outputs" / "bar_pipeline" / "visual_asset_export" / "bar" / "manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "bar_character_asset_pack"


def _safe_film_id(film_handle: str) -> str:
    return f"film_{film_handle.replace('0x', '').upper()}"


def _load_image(path: Path) -> Image.Image | None:
    if not path.exists():
        return None
    return Image.open(path).convert("RGBA")


def _compose_frame(images: list[dict], visual_root: Path) -> Image.Image | None:
    loaded: list[Image.Image] = []
    for image in images:
        rel = image.get("png")
        if not rel:
            continue
        img = _load_image(visual_root / rel)
        if img is not None:
            loaded.append(img)

    if not loaded:
        return None
    if len(loaded) == 1:
        return loaded[0]

    # Conservative composition: center each part on max bounds.
    w = max(img.width for img in loaded)
    h = max(img.height for img in loaded)
    canvas = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    for img in loaded:
        canvas.alpha_composite(img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2))
    return canvas


def build_pack(visual_manifest_path: Path, out_dir: Path) -> dict:
    visual = json.loads(visual_manifest_path.read_text(encoding="utf-8"))
    visual_root = visual_manifest_path.parent
    scene_name = str(visual.get("scene") or "UNKNOWN.SCN")
    films = visual.get("film_graph", [])

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    packs = []
    total_frames = 0

    for film in films:
        film_handle = film.get("film_handle")
        if not film_handle:
            continue

        asset_id = _safe_film_id(film_handle)
        pack_dir = out_dir / asset_id
        frames_dir = pack_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        frame_records = []
        frame_idx = 0
        for reel in film.get("reels", []):
            for frame in reel.get("frames", []):
                images = frame.get("images", [])
                if not images:
                    continue
                composed = _compose_frame(images, visual_root)
                if composed is None:
                    continue
                frame_name = f"frame_{frame_idx:03d}.png"
                composed.save(frames_dir / frame_name)
                frame_records.append(
                    {
                        "frame_index": frame_idx,
                        "frame_handle": frame.get("frame_handle"),
                        "reel_index": reel.get("reel_index"),
                        "png": f"frames/{frame_name}",
                        "image_count": len(images),
                    }
                )
                frame_idx += 1

        if not frame_records:
            continue

        pack_manifest = {
            "scene": scene_name,
            "asset_id": asset_id,
            "film_handle": film_handle,
            "frame_count_exported": len(frame_records),
            "frames": frame_records,
            "runtime_limitations": [
                "Frame composition is visual-manifest based and not full runtime ANI_SCRIPT playback.",
                "Multi-image frames use centered conservative composition.",
            ],
        }
        (pack_dir / "manifest.json").write_text(json.dumps(pack_manifest, indent=2), encoding="utf-8")

        packs.append(
            {
                "asset_id": asset_id,
                "film_handle": film_handle,
                "frame_count_exported": len(frame_records),
                "manifest": str((pack_dir / "manifest.json").relative_to(out_dir)),
            }
        )
        total_frames += len(frame_records)

    top_manifest = {
        "compiler": "build_bar_character_asset_pack_from_visual.py",
        "scene": scene_name,
        "source_visual_manifest": str(visual_manifest_path),
        "pack_count": len(packs),
        "total_frames": total_frames,
        "packs": packs,
    }
    (out_dir / "manifest.json").write_text(json.dumps(top_manifest, indent=2), encoding="utf-8")
    return top_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_VISUAL_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if not source.exists():
        raise FileNotFoundError(f"Visual manifest not found: {source}")

    manifest = build_pack(source, output)
    print(json.dumps({"pack_count": manifest["pack_count"], "total_frames": manifest["total_frames"], "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
