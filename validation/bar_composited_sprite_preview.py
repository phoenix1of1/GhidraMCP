#!/usr/bin/env python3
"""
BAR.SCN composited sprite preview prototype.

Composites character/actor sprites onto the BAR.SCN background using decoded placement/anchor data and outputs a preview image for regression/testing.
"""
from __future__ import annotations
import json, csv, zipfile, shutil

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Update these paths to match your local asset locations
ROOT = Path(__file__).parent.parent
GAME_ASSETS = ROOT / 'clean-game' / 'DISCWLD'
CHAR_PACKS = ROOT / 'bar_character_asset_pack'  # Update if needed
TIMELINE_ZIP = ROOT / 'bar_scene_space_playback_outputs.zip'  # Update if needed
TIMELINE_CSV_GENERATED = ROOT.parent / 'discworld_all_generated_csvs' / 'bar_scene_space_playback_timeline_full.csv'
TIMELINE_CSV_FALLBACK = ROOT.parent / 'discworld_all_generated_csvs' / 'bar_scene_space_playback_timeline.csv'
VISUAL_MANIFEST_FALLBACK = ROOT / 'outputs' / 'bar_pipeline' / 'visual_asset_export' / 'bar' / 'manifest.json'
OUT = ROOT / 'bar_composited_sprite_preview_outputs'
PKG = ROOT / 'bar_composited_sprite_preview_outputs.zip'

CANVAS_W, CANVAS_H = 640, 400
SCALE = 2


def extract(zip_path: Path, dest: Path):
    if dest.exists(): shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)

def rgba(path: Path) -> Image.Image:
    return Image.open(path).convert('RGBA')

def load_font(size=12):
    try: return ImageFont.truetype('DejaVuSans.ttf', size)
    except Exception: return ImageFont.load_default()

def paste_sprite(canvas: Image.Image, sprite: Image.Image, x: int, y: int):
    sw, sh = sprite.size
    px = int(x*SCALE - sw//2)
    py = int(y*SCALE - sh)
    canvas.alpha_composite(sprite, (px, py))
    return px, py, sw, sh


def load_background_from_visual_manifest(timeline_rows):
    if not VISUAL_MANIFEST_FALLBACK.exists():
        return None
    try:
        visual = json.loads(VISUAL_MANIFEST_FALLBACK.read_text(encoding='utf-8'))
    except Exception:
        return None

    bg_film = None
    for row in timeline_rows:
        if row.get('libcall') == 'BACKGROUND':
            bg_film = row.get('film')
            break

    film_graph = visual.get('film_graph', [])
    base_dir = VISUAL_MANIFEST_FALLBACK.parent

    def resolve_film_png(film_handle):
        for film in film_graph:
            if film.get('film_handle') != film_handle:
                continue
            for reel in film.get('reels', []):
                for frame in reel.get('frames', []):
                    for image in frame.get('images', []):
                        png = image.get('png')
                        if png:
                            path = base_dir / png
                            if path.exists():
                                return path
        return None

    bg_path = resolve_film_png(bg_film) if bg_film else None
    if bg_path is None:
        # Fallback: pick a likely scene background image by dimensions.
        for image in visual.get('images', []):
            if int(image.get('width', 0)) >= 600 and int(image.get('height', 0)) >= 180:
                png = image.get('png')
                if png:
                    candidate = base_dir / png
                    if candidate.exists():
                        bg_path = candidate
                        break
    if bg_path is None:
        return None
    return rgba(bg_path).resize((CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)

def main():

    work = ROOT / 'tmp_bar_composited_sprite_preview'
    if work.exists(): shutil.rmtree(work)
    (work / 'timeline').mkdir(parents=True)
    # If timeline and background are not available, skip extraction and use fallback
    timeline_csv = work / 'timeline' / 'bar_scene_space_playback_timeline.csv'
    bg_path = work / 'timeline' / 'bar_background_scene_scaled.png'
    if TIMELINE_ZIP.exists():
        extract(TIMELINE_ZIP, work / 'timeline')
    else:
        print(f"Warning: {TIMELINE_ZIP} not found. Using fallback timeline and background.")
    if not timeline_csv.exists() and TIMELINE_CSV_GENERATED.exists():
        timeline_csv = TIMELINE_CSV_GENERATED
    if not timeline_csv.exists() and TIMELINE_CSV_FALLBACK.exists():
        timeline_csv = TIMELINE_CSV_FALLBACK
    if not timeline_csv.exists():
        print("Error: Timeline CSV not found. Please provide bar_scene_space_playback_timeline.csv.")
        return
    with open(timeline_csv, newline='') as f:
        timeline = list(csv.DictReader(f))
    if bg_path.exists():
        bg = rgba(bg_path)
    else:
        bg = load_background_from_visual_manifest(timeline)
        if bg is None:
            # Fallback: create a blank background
            bg = Image.new('RGBA', (CANVAS_W, CANVAS_H), (20, 20, 20, 255))
    # Load character asset pack manifest
    char_manifest_path = CHAR_PACKS / 'manifest.json'
    film_to_pack = {}
    has_character_assets = char_manifest_path.exists()
    if has_character_assets:
        char_manifest = json.loads(char_manifest_path.read_text())
        film_to_pack = {p['film_handle']: p for p in char_manifest.get('packs', [])}
    else:
        print(f"Warning: Character asset pack manifest not found at {char_manifest_path}. Rendering placement markers only.")
    # Compose a single preview frame with all PLAY events composited
    canvas = bg.copy()
    d = ImageDraw.Draw(canvas)
    # Sort PLAY events by event_seq (approx z-order)
    play_events = [r for r in timeline if r['libcall'] == 'PLAY']
    play_events.sort(key=lambda r: int(r['event_seq']))
    missing_asset_count = 0
    rendered_sprite_count = 0
    for ev in play_events:
        film = ev['film']
        x = int(ev['x_used'])
        y = int(ev['y_used'])
        pack = film_to_pack.get(film)
        if pack:
            # Use first frame as preview (could be improved)
            frame_dir = CHAR_PACKS / pack['asset_id'] / 'frames'
            frame_files = sorted(frame_dir.glob('*.png')) if frame_dir.exists() else []
            if frame_files:
                sprite = rgba(frame_files[0])
                paste_sprite(canvas, sprite, x, y)
                rendered_sprite_count += 1
            else:
                missing_asset_count += 1
        else:
            missing_asset_count += 1

        # Always draw anchor/placement marker for validation.
        sx, sy = int(x * SCALE), int(y * SCALE)
        d.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(255, 255, 0, 255))
        d.text((sx + 6, sy - 10), f"{film}", fill=(255, 255, 0, 255), font=load_font(10))
    # Header
    d.rectangle([0, 0, CANVAS_W, 38], fill=(0, 0, 0, 160))
    d.text((6, 6), "BAR.SCN composited sprite preview | PLAY events composited", fill=(255, 255, 255, 255), font=load_font(13))
    OUT.mkdir(parents=True, exist_ok=True)
    out_img = OUT / 'bar_composited_sprite_preview.png'
    canvas.save(out_img)
    # Manifest
    manifest = {
        'scene': 'BAR.SCN',
        'prototype': 'composited sprite preview',
        'events_composited': len(play_events),
        'character_assets_available': has_character_assets,
        'rendered_sprite_count': rendered_sprite_count,
        'missing_asset_count': missing_asset_count,
        'outputs': {'preview': str(out_img.name)},
        'limitations': [
            'Uses first frame of each PLAY event; does not animate.',
            'Z-order is event order; not true runtime layering.',
            'No palette/effect logic applied (not yet decoded for BAR).',
            'No runtime BLOCK snap; uses nominal/fallback positions.',
            'When character packs are unavailable, preview renders placement markers only.'
        ]
    }
    (OUT / 'bar_composited_sprite_preview_manifest.json').write_text(json.dumps(manifest, indent=2))
    if PKG.exists(): PKG.unlink()
    shutil.make_archive(str(PKG.with_suffix('')), 'zip', OUT)
    print(json.dumps(manifest, indent=2))

if __name__=='__main__': main()
