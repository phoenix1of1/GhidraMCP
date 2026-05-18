#!/usr/bin/env python3
"""BAR.SCN scene-space playback viewer prototype.

Builds an approximate scene-space playback validation artifact from the existing
BAR ANI_SCRIPT frame expansion and PLAY placement metadata.
"""
from __future__ import annotations
import json, csv, zipfile, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/mnt/data')
ANI_ZIP = ROOT/'bar_ani_script_playback_outputs.zip'
PLACE_ZIP = ROOT/'bar_play_placement_semantics_outputs.zip'
OUT = ROOT/'bar_scene_space_playback'
PKG = ROOT/'bar_scene_space_playback_outputs.zip'

CANVAS_W, CANVAS_H = 640, 400
BG_SIZE = (320, 200)
SCALE = 2
MAX_OUTPUT_FRAMES = 48


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
    # Coordinates are nominal scene-space; center sprite lower-midpoint at (x,y).
    sw, sh = sprite.size
    px = int(x*SCALE - sw//2)
    py = int(y*SCALE - sh)
    canvas.alpha_composite(sprite, (px, py))
    return px, py, sw, sh


def make_placeholder(canvas, draw, x, y, label):
    sx, sy = int(x*SCALE), int(y*SCALE)
    draw.rectangle([sx-10, sy-10, sx+10, sy+10], outline=(255,255,0,255), width=2)
    draw.line([sx-14, sy, sx+14, sy], fill=(255,255,0,255), width=1)
    draw.line([sx, sy-14, sx, sy+14], fill=(255,255,0,255), width=1)
    draw.text((sx+12, sy-10), label, fill=(255,255,0,255), font=load_font(10))


def main():
    work = ROOT/'tmp_bar_scene_space_viewer'
    if work.exists(): shutil.rmtree(work)
    (work/'ani').mkdir(parents=True)
    (work/'place').mkdir(parents=True)
    extract(ANI_ZIP, work/'ani')
    extract(PLACE_ZIP, work/'place')

    ani_base = work/'ani'/'bar_ani_script_playback'
    place_base = work/'place'/'bar_play_placement_semantics'
    manifest = json.loads((ani_base/'bar_ani_script_manifest.json').read_text())
    place_manifest = json.loads((place_base/'bar_play_placement_manifest.json').read_text())
    place_by_seq = {e['seq']: e for e in place_manifest.get('events', [])}

    if OUT.exists(): shutil.rmtree(OUT)
    (OUT/'frames').mkdir(parents=True)
    (OUT/'overlays').mkdir(parents=True)

    # Background: use first BACKGROUND frame, scale to 640x400.
    bg_event = next(e for e in manifest['events'] if e['libcall']=='BACKGROUND')
    bg_dir = next((ani_base/'frames').glob(f"event_{bg_event['seq']:03d}_BACKGROUND_*"))
    bg_frame = sorted(bg_dir.glob('frame_*.png'))[0]
    bg = rgba(bg_frame).resize((CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)
    bg.save(OUT/'bar_background_scene_scaled.png')

    film_events = [e for e in manifest['events'] if e['libcall'] in ('PLAY','STAND','BACKGROUND')]
    output_rows = []
    frame_paths = []
    total = 0
    event_index = 0

    for e in film_events:
        if total >= MAX_OUTPUT_FRAMES: break
        lib = e['libcall']
        seq = e['seq']
        film = e['film_handle'] if 'film_handle' in e else e.get('film')
        ev_dir_glob = list((ani_base/'frames').glob(f"event_{seq:03d}_{lib}_*"))
        frame_files = sorted(ev_dir_glob[0].glob('frame_*.png')) if ev_dir_glob else []
        # Determine nominal position for PLAY; background always covers canvas.
        placement = place_by_seq.get(seq, {}).get('play_placement', {})
        nominal = placement.get('nominal_arg_position') or {}
        x = nominal.get('x')
        y = nominal.get('y')
        has_nominal = isinstance(x, int) and isinstance(y, int) and x >= 0 and y >= 0
        # For events lacking coords, distribute along bottom as validation placeholders.
        fallback_x = 80 + (event_index % 6)*90
        fallback_y = 180 - (event_index//6)*30
        draw_x = x if has_nominal else fallback_x
        draw_y = y if has_nominal else fallback_y
        per_event_limit = 1 if lib=='BACKGROUND' else min(8, len(frame_files))
        if per_event_limit == 0: continue
        for fi, fr_path in enumerate(frame_files[:per_event_limit]):
            canvas = bg.copy()
            d = ImageDraw.Draw(canvas)
            if lib != 'BACKGROUND':
                spr = rgba(fr_path)
                px, py, sw, sh = paste_sprite(canvas, spr, draw_x, draw_y)
                # Overlay nominal point and footprint placeholder rectangle.
                sx, sy = int(draw_x*SCALE), int(draw_y*SCALE)
                d.rectangle([sx-20, sy-16, sx+20, sy+16], outline=(0,255,255,255), width=2)
                d.ellipse([sx-3, sy-3, sx+3, sy+3], fill=(255,255,0,255))
                coord_note = 'nominal' if has_nominal else 'fallback/no runtime snap'
            else:
                coord_note = 'background'
            # Header panel.
            d.rectangle([0,0,CANVAS_W,42], fill=(0,0,0,160))
            text = f"BAR scene-space prototype | event {seq:03d} {lib} {film} | frame {fi:02d} | {coord_note}"
            d.text((6,6), text, fill=(255,255,255,255), font=load_font(13))
            if lib == 'PLAY':
                d.text((6,24), "PLAY placement: nominal coords shown; BLOCK snap pending full runtime state", fill=(255,220,120,255), font=load_font(11))
            outp = OUT/'frames'/f'frame_{total:03d}_event_{seq:03d}_{lib}.png'
            canvas.convert('RGB').save(outp)
            frame_paths.append(outp)
            output_rows.append({
                'output_frame': total,
                'event_seq': seq,
                'libcall': lib,
                'film': film,
                'event_frame': fi,
                'x_used': draw_x,
                'y_used': draw_y,
                'position_source': 'nominal_pcode' if has_nominal else ('background' if lib=='BACKGROUND' else 'fallback_visual_validation'),
                'runtime_snap_applied': False,
                'source_png': str(fr_path.relative_to(ani_base)),
            })
            total += 1
            if total >= MAX_OUTPUT_FRAMES: break
        event_index += 1

    # Contact sheet
    thumbs = []
    for p in frame_paths[:24]:
        im = Image.open(p).resize((320,200), Image.Resampling.BILINEAR)
        thumbs.append(im)
    cols=3; rows=(len(thumbs)+cols-1)//cols
    sheet = Image.new('RGB',(cols*320,rows*200),(30,30,30))
    for i,im in enumerate(thumbs): sheet.paste(im,((i%cols)*320,(i//cols)*200))
    sheet.save(OUT/'bar_scene_space_contact_sheet.png')

    # GIF
    gif_frames=[Image.open(p).convert('P', palette=Image.Palette.ADAPTIVE) for p in frame_paths[:36]]
    if gif_frames:
        gif_frames[0].save(OUT/'bar_scene_space_playback.gif', save_all=True, append_images=gif_frames[1:], duration=140, loop=0)

    with (OUT/'bar_scene_space_playback_timeline.csv').open('w',newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(output_rows[0].keys()))
        w.writeheader(); w.writerows(output_rows)

    report={
        'scene':'BAR.SCN',
        'prototype':'scene-space playback viewer',
        'scope':'validation-oriented approximate scene-space rendering; runtime snap not yet applied',
        'output_frames': total,
        'film_events_considered': len(film_events),
        'play_events_with_nominal_positions': sum(1 for r in output_rows if r['libcall']=='PLAY' and r['position_source']=='nominal_pcode'),
        'runtime_snap_applied': False,
        'limitations':[
            'Uses nominal PCODE coordinates where available; otherwise fallback validation positions.',
            'BLOCK polygon snapped coordinates are not applied yet because full live scheduler state is not emulated.',
            'Layering is approximate and single-event focused, not multi-actor compositing.'
        ],
        'outputs': {
            'contact_sheet':'bar_scene_space_contact_sheet.png',
            'gif':'bar_scene_space_playback.gif',
            'frames_dir':'frames/',
            'timeline':'bar_scene_space_playback_timeline.csv'
        }
    }
    (OUT/'bar_scene_space_playback_manifest.json').write_text(json.dumps(report, indent=2))
    (OUT/'README.md').write_text('# BAR Scene-space Playback Viewer Prototype\n\nApproximate scene-space validation output. Nominal coordinates are shown; runtime BLOCK snap is not yet applied.\n')

    if PKG.exists(): PKG.unlink()
    shutil.make_archive(str(PKG.with_suffix('')), 'zip', OUT)
    print(json.dumps(report, indent=2))

if __name__=='__main__': main()
