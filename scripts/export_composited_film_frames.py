#!/usr/bin/env python3
"""Export fully-composited per-film frame sequences from a scene visual manifest.

For each unique film in the scene's visual_asset_export manifest:
  - Composites all part images per frame (handles multi-part frames via anim offsets).
  - Strips black-box mattes.
  - Saves each frame as outputs/<scene>/composited_films/<film_handle>/frame_NNNN.png.
  - Saves a contact sprite-sheet  outputs/<scene>/composited_films/<film_handle>/sheet.png.
  - Writes a top-level manifest composited_films_manifest.json with anchor metadata.

Usage
-----
  python scripts/export_composited_film_frames.py --scene finale
  python scripts/export_composited_film_frames.py --scene bar
  python scripts/export_composited_film_frames.py --manifest path/to/manifest.json --out path/to/output
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_ROOT = ROOT / "outputs"


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def strip_black_matte(image: Image.Image) -> Image.Image:
    """Remove solid-black pixels that form a border matte (>= 60 % of border pixels)."""
    w, h = image.size
    if w < 4 or h < 4:
        return image

    px = image.load()
    border = 0
    border_black = 0
    for x in range(w):
        for y in (0, h - 1):
            r, g, b, a = px[x, y]
            if a > 0:
                border += 1
                if r == 0 and g == 0 and b == 0:
                    border_black += 1
    for y in range(1, h - 1):
        for x in (0, w - 1):
            r, g, b, a = px[x, y]
            if a > 0:
                border += 1
                if r == 0 and g == 0 and b == 0:
                    border_black += 1

    if border == 0 or (border_black / border) < 0.6:
        return image

    out = image.copy()
    opx = out.load()
    for yy in range(h):
        for xx in range(w):
            r, g, b, a = opx[xx, yy]
            if a > 0 and r == 0 and g == 0 and b == 0:
                opx[xx, yy] = (0, 0, 0, 0)
    return out


def compose_frame_parts(parts: list[tuple[Image.Image, int, int]]) -> tuple[Image.Image, int, int]:
    """Composite part images at their anim offsets; return (composed, anchor_x, anchor_y).

    anchor_x/anchor_y is the pixel distance from the top-left corner of the
    composed image to the logical origin (0,0) of the animation coordinate space.
    """
    if not parts:
        blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return blank, 0, 0

    min_x = min(ox for _img, ox, _oy in parts)
    min_y = min(oy for _img, _ox, oy in parts)
    max_x = max(ox + img.width  for img, ox, _oy in parts)
    max_y = max(oy + img.height for img, _ox, oy in parts)

    w = max(1, max_x - min_x)
    h = max(1, max_y - min_y)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for img, ox, oy in parts:
        canvas.alpha_composite(img, (ox - min_x, oy - min_y))

    anchor_x = -min_x
    anchor_y = -min_y
    return canvas, anchor_x, anchor_y


def make_sheet(frames: list[Image.Image], max_cols: int = 10) -> Image.Image:
    """Arrange frames in a grid sprite-sheet (transparent background)."""
    if not frames:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    cols = min(len(frames), max_cols)
    rows = (len(frames) + cols - 1) // cols
    cell_w = max(f.width  for f in frames)
    cell_h = max(f.height for f in frames)
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (0, 0, 0, 0))
    for i, frm in enumerate(frames):
        col = i % cols
        row = i // cols
        sheet.alpha_composite(frm, (col * cell_w, row * cell_h))
    return sheet


# ---------------------------------------------------------------------------
# Core export logic
# ---------------------------------------------------------------------------

def export_scene(manifest_path: Path, out_root: Path, sheet_cols: int = 10) -> dict:
    manifest_path = manifest_path.resolve()
    base_dir = manifest_path.parent

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_by_handle = {
        img["image_handle"]: img
        for img in data.get("images", [])
        if img.get("image_handle")
    }

    # Deduplicate films by handle (manifest may list the same film multiple times).
    unique_films: dict[str, dict] = {}
    for film in data.get("film_graph", []):
        fh = film.get("film_handle")
        if fh and fh not in unique_films:
            unique_films[fh] = film

    out_root.mkdir(parents=True, exist_ok=True)

    export_records = []
    total_frames_written = 0
    skipped_films = 0

    for film_handle, film in sorted(unique_films.items()):
        # Collect compositable frames in reel order.
        compositable_frames = []
        for reel in film.get("reels", []):
            for frame in reel.get("frames", []):
                imgs = frame.get("images", [])
                if not imgs:
                    # Placeholder / blank frame — include as transparent.
                    compositable_frames.append(([], False))
                else:
                    compositable_frames.append((imgs, True))

        if not compositable_frames:
            skipped_films += 1
            continue

        film_dir = out_root / film_handle.replace("0x", "").upper()
        film_dir.mkdir(parents=True, exist_ok=True)

        composed_frames: list[Image.Image] = []
        frame_records = []

        for fidx, (img_refs, has_images) in enumerate(compositable_frames):
            if not has_images:
                blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                composed_frames.append(blank)
                frame_records.append({
                    "frame_index": fidx,
                    "anchor_x": 0,
                    "anchor_y": 0,
                    "width": 1,
                    "height": 1,
                    "png": f"frame_{fidx:04d}.png",
                    "has_images": False,
                })
                blank.save(film_dir / f"frame_{fidx:04d}.png")
                continue

            parts: list[tuple[Image.Image, int, int]] = []
            for img_ref in img_refs:
                h = img_ref.get("image_handle")
                meta = image_by_handle.get(h)
                if not meta:
                    continue
                rel = meta.get("png")
                if not rel:
                    continue
                src = base_dir / rel
                if not src.exists():
                    continue
                img = strip_black_matte(rgba(src))
                ox = int(meta.get("anim_offset_x") or 0)
                oy = int(meta.get("anim_offset_y") or 0)
                parts.append((img, ox, oy))

            if not parts:
                blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                composed_frames.append(blank)
                frame_records.append({
                    "frame_index": fidx,
                    "anchor_x": 0,
                    "anchor_y": 0,
                    "width": 1,
                    "height": 1,
                    "png": f"frame_{fidx:04d}.png",
                    "has_images": False,
                })
                blank.save(film_dir / f"frame_{fidx:04d}.png")
                continue

            composed, anchor_x, anchor_y = compose_frame_parts(parts)
            out_path = film_dir / f"frame_{fidx:04d}.png"
            composed.save(out_path)
            composed_frames.append(composed)
            total_frames_written += 1
            frame_records.append({
                "frame_index": fidx,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "width": composed.width,
                "height": composed.height,
                "png": f"frame_{fidx:04d}.png",
                "has_images": True,
            })

        # Sprite sheet.
        visible = [f for f, r in zip(composed_frames, frame_records) if r["has_images"]]
        if visible:
            sheet = make_sheet(visible, max_cols=sheet_cols)
            sheet.save(film_dir / "sheet.png")

        export_records.append({
            "film_handle": film_handle,
            "frame_count": len(compositable_frames),
            "compositable_count": sum(1 for r in frame_records if r["has_images"]),
            "frames": frame_records,
            "output_dir": film_dir.name,
        })

    result_manifest = {
        "source_manifest": str(manifest_path),
        "total_unique_films": len(unique_films),
        "exported_films": len(export_records),
        "skipped_films": skipped_films,
        "total_frames_written": total_frames_written,
        "films": export_records,
    }
    (out_root / "composited_films_manifest.json").write_text(
        json.dumps(result_manifest, indent=2), encoding="utf-8"
    )
    return result_manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_manifest_and_out(args) -> tuple[Path, Path]:
    if args.manifest:
        manifest_path = Path(args.manifest)
        out_root = Path(args.out) if args.out else manifest_path.parent / "composited_films"
        return manifest_path, out_root

    scene = args.scene.lower()
    # Try to infer pipeline directory name from scene name.
    pipeline_name = f"{scene}_pipeline"
    manifest_path = OUTPUTS_ROOT / pipeline_name / "visual_asset_export" / scene / "manifest.json"
    if not manifest_path.exists():
        # Fallback: search for any manifest under outputs matching the scene name.
        candidates = list(OUTPUTS_ROOT.rglob(f"{scene}/manifest.json"))
        if not candidates:
            raise FileNotFoundError(
                f"Cannot find manifest for scene '{scene}'. "
                f"Tried: {manifest_path}\n"
                "Use --manifest to specify the path directly."
            )
        manifest_path = candidates[0]

    out_root = OUTPUTS_ROOT / pipeline_name / "visual_asset_export" / scene / "composited_films"
    if args.out:
        out_root = Path(args.out)
    return manifest_path, out_root


def main():
    parser = argparse.ArgumentParser(description="Export composited film frames from a scene visual manifest.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scene", help="Scene name, e.g. 'finale' or 'bar'.")
    group.add_argument("--manifest", help="Direct path to a scene manifest.json.")
    parser.add_argument("--out", help="Override output directory.")
    parser.add_argument("--sheet-cols", type=int, default=10, help="Columns in sprite sheet (default: 10).")
    args = parser.parse_args()

    manifest_path, out_root = _resolve_manifest_and_out(args)
    print(f"Manifest : {manifest_path}")
    print(f"Output   : {out_root}")

    result = export_scene(manifest_path, out_root, sheet_cols=args.sheet_cols)

    print(f"\nDone.")
    print(f"  Unique films    : {result['total_unique_films']}")
    print(f"  Exported films  : {result['exported_films']}")
    print(f"  Frames written  : {result['total_frames_written']}")
    print(f"  Manifest        : {out_root / 'composited_films_manifest.json'}")


if __name__ == "__main__":
    main()
