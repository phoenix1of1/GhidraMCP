#!/usr/bin/env python3
"""BAR.SCN animation strip prototype.

Consumes the previously generated BAR timeline prototype and BAR visual manifest,
then expands film scheduler events into ordered frame strips using the resolved
FILM -> reel -> frame -> image graph.
"""
from __future__ import annotations

import json
import csv
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

BASE = Path('/mnt/data')
PLAYBACK_MANIFEST = BASE / 'bar_playback_prototype' / 'bar_playback_manifest.json'
VISUAL_ROOT = BASE / 'bar_visual_full' / 'visual_asset_export' / 'bar'
VISUAL_MANIFEST = VISUAL_ROOT / 'manifest.json'
OUT = BASE / 'bar_animation_strips'
STRIPS = OUT / 'strips'
ANIM = OUT / 'animations'
FRAMES = OUT / 'frames'

MAX_FRAMES_PER_EVENT = 24
THUMB_MAX_W = 120
THUMB_MAX_H = 100
CARD_W = 150
CARD_H = 145
LABEL_H = 36
PADDING = 8
BG = (238, 238, 238, 255)
CARD_BG = (255, 255, 255, 255)
TEXT = (0, 0, 0, 255)
BORDER = (80, 80, 80, 255)


def load_json(path: Path) -> Any:
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def handle_key(h: str) -> str:
    return h.upper().replace('0X', '0x')


def safe_name(s: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in s)


def get_font(size: int = 12):
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size)
    except Exception:
        return ImageFont.load_default()


def fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = img.convert('RGBA')
    w, h = img.size
    if w == 0 or h == 0:
        return img
    scale = min(max_w / w, max_h / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    if (nw, nh) == img.size:
        return img.copy()
    return img.resize((nw, nh), Image.Resampling.NEAREST)


def find_film_graph(visual: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in visual.get('film_graph', []):
        h = item.get('film_handle')
        if h and h not in out:
            out[handle_key(h)] = item
    return out


def collect_frame_sequence(film: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten reels into a visual frame sequence.

    The existing film manifest already resolves ANI_SCRIPT/frame handles into a
    conservative list. We retain only frames with concrete images, preserving
    order and reel index. This avoids inventing animation commands beyond the
    decoded manifest.
    """
    seq: List[Dict[str, Any]] = []
    for reel in film.get('reels', []):
        reel_idx = reel.get('reel_index', 0)
        for frame_idx, frame in enumerate(reel.get('frames', [])):
            images = [img for img in frame.get('images', []) if img.get('png')]
            if not images:
                continue
            seq.append({
                'reel_index': reel_idx,
                'frame_index': frame_idx,
                'frame_handle': frame.get('frame_handle'),
                'images': images,
            })
    return seq


def make_composite(frame: Dict[str, Any]) -> Optional[Image.Image]:
    """Make a simple composite for all images in a frame.

    This is not placement-accurate. It centers images on a transparent canvas and
    stacks multiple images left-to-right if needed.
    """
    imgs: List[Image.Image] = []
    for imeta in frame.get('images', []):
        p = VISUAL_ROOT / imeta['png']
        if p.exists():
            imgs.append(Image.open(p).convert('RGBA'))
    if not imgs:
        return None
    if len(imgs) == 1:
        return imgs[0]
    total_w = sum(i.width for i in imgs) + (len(imgs)-1)*4
    max_h = max(i.height for i in imgs)
    canvas = Image.new('RGBA', (total_w, max_h), (0,0,0,0))
    x = 0
    for img in imgs:
        canvas.alpha_composite(img, (x, max(0, (max_h - img.height)//2)))
        x += img.width + 4
    return canvas


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[int,int], width: int, font, fill=TEXT, max_lines=3):
    words = text.split()
    lines=[]
    cur=''
    for w in words:
        test = (cur + ' ' + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] - bbox[0] <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    y=xy[1]
    for line in lines[:max_lines]:
        draw.text((xy[0], y), line, font=font, fill=fill)
        y += 13


def make_strip(event: Dict[str, Any], film: Dict[str, Any], seq: List[Dict[str, Any]]) -> Tuple[Path, List[Dict[str, Any]], Optional[Path]]:
    font = get_font(11)
    title_font = get_font(12)
    frames_to_use = seq[:MAX_FRAMES_PER_EVENT]
    n = max(1, len(frames_to_use))
    W = n * CARD_W + PADDING * 2
    H = CARD_H + PADDING * 2 + 36
    strip = Image.new('RGBA', (W, H), BG)
    draw = ImageDraw.Draw(strip)
    title = f"event {event['seq']:03d} {event['libcall']} film={event.get('film')} frate={film.get('frate')} frames={len(seq)} shown={len(frames_to_use)}"
    draw.text((PADDING, 4), title, font=title_font, fill=TEXT)
    frame_records=[]
    gif_frames=[]
    for i, frame in enumerate(frames_to_use):
        x0 = PADDING + i * CARD_W
        y0 = PADDING + 28
        draw.rectangle((x0, y0, x0+CARD_W-6, y0+CARD_H-1), fill=CARD_BG, outline=BORDER)
        comp = make_composite(frame)
        if comp is not None:
            # Save individual composite frame
            event_dir = FRAMES / f"event_{event['seq']:03d}_{event['libcall']}_{safe_name(event.get('film','nofilm'))}"
            event_dir.mkdir(parents=True, exist_ok=True)
            frame_path = event_dir / f"frame_{i:03d}_reel{frame['reel_index']}_idx{frame['frame_index']}.png"
            comp.save(frame_path)
            thumb = fit_image(comp, THUMB_MAX_W, THUMB_MAX_H)
            tx = x0 + (CARD_W-6 - thumb.width)//2
            ty = y0 + 6 + (THUMB_MAX_H - thumb.height)//2
            strip.alpha_composite(thumb, (tx, ty))
            gif_frame = Image.new('RGBA', (THUMB_MAX_W, THUMB_MAX_H), (0,0,0,0))
            gif_frame.alpha_composite(fit_image(comp, THUMB_MAX_W, THUMB_MAX_H), ((THUMB_MAX_W-fit_image(comp, THUMB_MAX_W, THUMB_MAX_H).width)//2, (THUMB_MAX_H-fit_image(comp, THUMB_MAX_W, THUMB_MAX_H).height)//2))
            gif_frames.append(gif_frame.convert('P', palette=Image.Palette.ADAPTIVE))
            frame_records.append({
                'sequence_index': i,
                'reel_index': frame['reel_index'],
                'frame_index': frame['frame_index'],
                'frame_handle': frame.get('frame_handle'),
                'image_count': len(frame.get('images', [])),
                'png': str(frame_path.relative_to(OUT)),
                'image_handles': [img.get('image_handle') for img in frame.get('images', [])],
            })
        label = f"#{i} r{frame['reel_index']} f{frame['frame_index']}\n{frame.get('frame_handle','')}"
        draw_wrapped(draw, label, (x0+4, y0+THUMB_MAX_H+10), CARD_W-14, font, max_lines=2)
    strip_path = STRIPS / f"event_{event['seq']:03d}_{event['libcall']}_{safe_name(event.get('film','nofilm'))}_strip.png"
    strip.save(strip_path)
    gif_path = None
    if gif_frames:
        gif_path = ANIM / f"event_{event['seq']:03d}_{event['libcall']}_{safe_name(event.get('film','nofilm'))}.gif"
        # use frate if available, assume frame rate per second; cap duration readable
        frate = film.get('frate') or 12
        duration = max(60, min(250, int(1000 / max(1, frate))))
        gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=duration, loop=0, transparency=0, disposal=2)
    return strip_path, frame_records, gif_path


def make_timeline_contact(strips: List[Path]) -> Path:
    font=get_font(12)
    thumbs=[]
    for p in strips:
        img=Image.open(p).convert('RGBA')
        thumbs.append((p, fit_image(img, 340, 160)))
    cols=2
    cell_w=360; cell_h=200
    rows=(len(thumbs)+cols-1)//cols
    sheet=Image.new('RGBA',(cols*cell_w+PADDING*2, rows*cell_h+PADDING*2), BG)
    draw=ImageDraw.Draw(sheet)
    for idx,(p,img) in enumerate(thumbs):
        col=idx%cols; row=idx//cols
        x=PADDING+col*cell_w; y=PADDING+row*cell_h
        draw.rectangle((x,y,x+cell_w-8,y+cell_h-8), fill=CARD_BG, outline=BORDER)
        sheet.alpha_composite(img,(x+8,y+8))
        draw_wrapped(draw,p.name,(x+8,y+172),cell_w-20,font,max_lines=2)
    out=OUT/'bar_animation_timeline_sheet.png'
    sheet.save(out)
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    STRIPS.mkdir(parents=True)
    ANIM.mkdir(parents=True)
    FRAMES.mkdir(parents=True)

    playback = load_json(PLAYBACK_MANIFEST)
    visual = load_json(VISUAL_MANIFEST)
    film_by_handle = find_film_graph(visual)

    film_events = [e for e in playback['events'] if e.get('category') == 'film' and e.get('film')]
    event_records=[]
    strip_paths=[]
    failures=[]

    for e in film_events:
        film=film_by_handle.get(handle_key(e['film']))
        if not film:
            failures.append({'seq': e['seq'], 'film': e['film'], 'reason': 'film not found in visual manifest'})
            continue
        seq=collect_frame_sequence(film)
        if not seq:
            failures.append({'seq': e['seq'], 'film': e['film'], 'reason': 'no concrete image frames in film graph'})
            continue
        strip_path, frame_records, gif_path = make_strip(e, film, seq)
        strip_paths.append(strip_path)
        event_records.append({
            'seq': e['seq'],
            'libcall': e['libcall'],
            'film': e['film'],
            'frate': film.get('frate'),
            'reel_count': film.get('numreels'),
            'available_visual_frames': len(seq),
            'exported_frames': len(frame_records),
            'strip_png': str(strip_path.relative_to(OUT)),
            'animated_gif': str(gif_path.relative_to(OUT)) if gif_path else None,
            'frames': frame_records,
            'args_display': e.get('args_display'),
            'limitations': [
                'frame sequence is derived from resolved manifest frames; complex ANI_SCRIPT loops/commands are not fully runtime-emulated',
                'multi-image frame placement is approximate/inspection-oriented',
                'PLAY spatial placement is not applied to the strip output',
            ]
        })

    contact = make_timeline_contact(strip_paths) if strip_paths else None

    summary = {
        'scene': 'BAR.SCN',
        'prototype_type': 'film-event animation frame strips',
        'film_events_seen': len(film_events),
        'film_events_exported': len(event_records),
        'render_failures': len(failures),
        'max_frames_per_event': MAX_FRAMES_PER_EVENT,
        'total_available_visual_frames': sum(r['available_visual_frames'] for r in event_records),
        'total_exported_frames': sum(r['exported_frames'] for r in event_records),
        'timeline_contact_sheet': str(contact.relative_to(OUT)) if contact else None,
        'events': event_records,
        'failures': failures,
        'interpretation': 'This validates film-frame ordering visually but is not exact runtime playback.',
    }
    (OUT/'bar_animation_strip_manifest.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    with (OUT/'bar_animation_strip_summary.csv').open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=['seq','libcall','film','frate','reel_count','available_visual_frames','exported_frames','strip_png','animated_gif'])
        w.writeheader()
        for r in event_records:
            w.writerow({k:r.get(k) for k in w.fieldnames})

    readme = f"""# BAR.SCN Animation Strip Prototype\n\nThis output expands BAR scheduler film events into ordered frame strips.\n\n## Results\n\n- Film events seen: {len(film_events)}\n- Film events exported: {len(event_records)}\n- Total available visual frames: {summary['total_available_visual_frames']}\n- Total exported frames: {summary['total_exported_frames']}\n- Render failures: {len(failures)}\n\n## Important limitations\n\n- This is not exact runtime playback.\n- ANI_SCRIPT command behavior is only represented through the existing resolved film manifest frame order.\n- Multi-image frame placement is approximate.\n- PLAY spatial placement is not applied.\n\nSee `bar_animation_strip_manifest.json` for the structured event/frame data.\n"""
    (OUT/'README.md').write_text(readme, encoding='utf-8')

    zip_path=BASE/'bar_animation_strips_outputs.zip'
    if zip_path.exists(): zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', OUT)
    print(json.dumps({'out':str(OUT),'zip':str(zip_path),'summary':summary}, indent=2)[:4000])

if __name__=='__main__':
    main()
