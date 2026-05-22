#!/usr/bin/env python3
"""FINALE.SCN composited sprite preview prototype.

Composites FINALE character/actor sprites onto a FINALE background using the
generated FINALE placement timeline and character asset pack.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
TIMELINE_CSV = ROOT.parent / "discworld_all_generated_csvs" / "finale_scene_space_playback_timeline_full.csv"
CHAR_PACKS = ROOT / "finale_character_asset_pack"
VISUAL_MANIFEST = ROOT / "outputs" / "finale_pipeline" / "visual_asset_export" / "finale" / "manifest.json"
OUT = ROOT / "finale_composited_sprite_preview_outputs"
PKG = ROOT / "finale_composited_sprite_preview_outputs.zip"

CANVAS_W, CANVAS_H = 640, 400
SCALE = 2


def rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def load_font(size=12):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def paste_sprite(canvas: Image.Image, sprite: Image.Image, x: int, y: int):
    sw, sh = sprite.size
    px = int(x * SCALE - sw // 2)
    py = int(y * SCALE - sh)
    canvas.alpha_composite(sprite, (px, py))
    return px, py, sw, sh


def paste_sprite_with_anchor(canvas: Image.Image, sprite: Image.Image, anchor_x: int, anchor_y: int, x: int, y: int):
    px = int(x * SCALE - anchor_x)
    py = int(y * SCALE - anchor_y)
    canvas.alpha_composite(sprite, (px, py))
    return px, py, sprite.width, sprite.height


def classify_layer(sprite_w: int, sprite_h: int, x: int, y: int):
    # Deterministic scene-oriented layering heuristic.
    if y <= 40:
        return "overlay_back", 0
    if sprite_w >= 120 and sprite_h >= 110:
        return "creature_back", 1
    if sprite_w <= 45 and sprite_h <= 45:
        return "fx_front", 4
    if sprite_h >= 60 and sprite_w >= 50:
        return "actor_mid", 3
    return "mid", 2


def strip_black_box_if_needed(image: Image.Image) -> Image.Image:
    # Some extracted sprites carry opaque black matte; remove exact black when border is mostly black.
    rgba_img = image.convert("RGBA")
    w, h = rgba_img.size
    if w < 4 or h < 4:
        return rgba_img

    px = rgba_img.load()
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
        return rgba_img

    out = rgba_img.copy()
    opx = out.load()
    for yy in range(h):
        for xx in range(w):
            r, g, b, a = opx[xx, yy]
            if a > 0 and r == 0 and g == 0 and b == 0:
                opx[xx, yy] = (0, 0, 0, 0)
    return out


def load_background_from_visual_manifest(timeline_rows):
    if not VISUAL_MANIFEST.exists():
        return None
    try:
        visual = json.loads(VISUAL_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None

    bg_film = None
    for row in timeline_rows:
        if row.get("libcall") == "BACKGROUND":
            bg_film = row.get("film")
            break

    film_graph = visual.get("film_graph", [])
    base_dir = VISUAL_MANIFEST.parent

    def resolve_film_png(film_handle):
        for film in film_graph:
            if film.get("film_handle") != film_handle:
                continue
            for reel in film.get("reels", []):
                for frame in reel.get("frames", []):
                    for image in frame.get("images", []):
                        png = image.get("png")
                        if png:
                            p = base_dir / png
                            if p.exists():
                                return p
        return None

    bg_path = resolve_film_png(bg_film) if bg_film else None
    if bg_path is None:
        for image in visual.get("images", []):
            if int(image.get("width", 0)) >= 600 and int(image.get("height", 0)) >= 180:
                png = image.get("png")
                if png:
                    p = base_dir / png
                    if p.exists():
                        bg_path = p
                        break
    if bg_path is None:
        return None
    return rgba(bg_path).resize((CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)


def build_visual_indexes():
    if not VISUAL_MANIFEST.exists():
        return {}, {}, {}
    visual = json.loads(VISUAL_MANIFEST.read_text(encoding="utf-8"))
    image_by_handle = {img.get("image_handle"): img for img in visual.get("images", []) if img.get("image_handle")}
    film_by_handle = {film.get("film_handle"): film for film in visual.get("film_graph", []) if film.get("film_handle")}
    return visual, image_by_handle, film_by_handle


def compose_film_frame(film_handle: str, frame_index: int, image_by_handle: dict, film_by_handle: dict):
    film = film_by_handle.get(film_handle)
    if not film:
        return None

    frames = []
    for reel in film.get("reels", []):
        for frame in reel.get("frames", []):
            if frame.get("images"):
                frames.append(frame)
    if not frames:
        return None

    selected = frames[frame_index % len(frames)]
    parts = []
    for image_ref in selected.get("images", []):
        h = image_ref.get("image_handle")
        meta = image_by_handle.get(h)
        if not meta:
            continue
        rel = meta.get("png")
        if not rel:
            continue
        p = VISUAL_MANIFEST.parent / rel
        if not p.exists():
            continue
        img = strip_black_box_if_needed(rgba(p))
        ox = int(meta.get("anim_offset_x") or 0)
        oy = int(meta.get("anim_offset_y") or 0)
        parts.append((img, ox, oy))

    if not parts:
        return None

    min_x = min(ox for _img, ox, _oy in parts)
    min_y = min(oy for _img, _ox, oy in parts)
    max_x = max(ox + img.width for img, ox, _oy in parts)
    max_y = max(oy + img.height for img, _ox, oy in parts)

    width = max(1, max_x - min_x)
    height = max(1, max_y - min_y)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for img, ox, oy in parts:
        canvas.alpha_composite(img, (ox - min_x, oy - min_y))

    anchor_x = int(-min_x)
    anchor_y = int(-min_y)
    return canvas, anchor_x, anchor_y, len(frames)


def main():
    if not TIMELINE_CSV.exists():
        raise FileNotFoundError(f"Timeline CSV not found: {TIMELINE_CSV}")

    with TIMELINE_CSV.open("r", encoding="utf-8", newline="") as f:
        timeline = list(csv.DictReader(f))

    bg = load_background_from_visual_manifest(timeline)
    if bg is None:
        bg = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 20, 20, 255))

    visual, image_by_handle, film_by_handle = build_visual_indexes()

    char_manifest_path = CHAR_PACKS / "manifest.json"
    has_character_assets = char_manifest_path.exists()
    film_to_pack = {}
    if has_character_assets:
        char_manifest = json.loads(char_manifest_path.read_text(encoding="utf-8"))
        film_to_pack = {p["film_handle"]: p for p in char_manifest.get("packs", [])}

    canvas = bg.copy()
    draw = ImageDraw.Draw(canvas)

    play_events = [row for row in timeline if row.get("libcall") == "PLAY"]
    # Approximate scene depth: lower Y tends to be visually in front.
    play_events.sort(key=lambda r: (int(r.get("y_used") or 0), int(r.get("event_seq") or 0)))

    rendered_sprite_count = 0
    missing_asset_count = 0
    film_occurrence_index = {}
    source_counts = {}
    layer_class_counts = {}
    render_items = []

    for ev in play_events:
        film = ev.get("film") or ""
        x = int(ev.get("x_used") or 0)
        y = int(ev.get("y_used") or 0)
        source = ev.get("position_source") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        idx = film_occurrence_index.get(film, 0)
        film_occurrence_index[film] = idx + 1

        rendered = False
        sprite = None
        mode = ""
        anchor_x = 0
        anchor_y = 0

        visual_frame = compose_film_frame(film, idx, image_by_handle, film_by_handle)
        if visual_frame is not None:
            sprite, ax, ay, _frame_count = visual_frame
            anchor_x = ax
            anchor_y = ay
            mode = "anchor"
            rendered = True

        if not rendered:
            pack = film_to_pack.get(film)
            if pack:
                frame_dir = CHAR_PACKS / pack["asset_id"] / "frames"
                frame_files = sorted(frame_dir.glob("*.png")) if frame_dir.exists() else []
                if frame_files:
                    sprite = strip_black_box_if_needed(rgba(frame_files[idx % len(frame_files)]))
                    mode = "feet"
                    rendered = True

        if not rendered:
            missing_asset_count += 1
            continue

        layer_name, layer_priority = classify_layer(sprite.width, sprite.height, x, y)
        layer_class_counts[layer_name] = layer_class_counts.get(layer_name, 0) + 1
        render_items.append(
            {
                "film": film,
                "x": x,
                "y": y,
                "event_seq": int(ev.get("event_seq") or 0),
                "sprite": sprite,
                "mode": mode,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "layer_name": layer_name,
                "layer_priority": layer_priority,
            }
        )

    render_items.sort(key=lambda i: (int(i["y"]), int(i["layer_priority"]), int(i["event_seq"])))
    for item in render_items:
        if item["mode"] == "anchor":
            paste_sprite_with_anchor(canvas, item["sprite"], int(item["anchor_x"]), int(item["anchor_y"]), int(item["x"]), int(item["y"]))
        else:
            paste_sprite(canvas, item["sprite"], int(item["x"]), int(item["y"]))
        rendered_sprite_count += 1

        sx, sy = int(item["x"] * SCALE), int(item["y"] * SCALE)
        draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(255, 255, 0, 255))

    draw.rectangle([0, 0, CANVAS_W, 38], fill=(0, 0, 0, 160))
    draw.text(
        (6, 6),
        "FINALE.SCN composited sprite preview | PLAY events composited",
        fill=(255, 255, 255, 255),
        font=load_font(13),
    )

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    out_img = OUT / "finale_composited_sprite_preview.png"
    canvas.save(out_img)

    manifest = {
        "scene": "FINALE.SCN",
        "prototype": "composited sprite preview",
        "events_composited": len(play_events),
        "character_assets_available": has_character_assets,
        "rendered_sprite_count": rendered_sprite_count,
        "missing_asset_count": missing_asset_count,
        "position_source_counts": dict(sorted(source_counts.items())),
        "layer_class_counts": dict(sorted(layer_class_counts.items())),
        "outputs": {"preview": out_img.name},
        "limitations": [
            "Uses per-event frame selection by film occurrence; does not run full ANI_SCRIPT playback.",
            "Composes parts using visual-manifest image anchor offsets; fallback uses pack frames.",
            "Z-order is approximate scene-depth sort by y_used + deterministic layer class + event order.",
            "No palette/effect logic applied.",
            "Runtime BLOCK snap follows timeline pre-resolution, not full VM state emulation.",
        ],
    }
    (OUT / "finale_composited_sprite_preview_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if PKG.exists():
        PKG.unlink()
    shutil.make_archive(str(PKG.with_suffix("")), "zip", OUT)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
