#!/usr/bin/env python3
"""Run placement validation harness on scenes with compiled POLY_BLOCK records.

Finds scenes containing compiled POLY_BLOCK records, then generates a focused
overlay for FINALE.SCN because it has both a BLOCK polygon and an exported
background film image in the current artifact set.
"""
from __future__ import annotations
import csv, json, os, re, shutil, struct, zipfile
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw

ROOT = Path('/mnt/data')
OUT = ROOT / 'block_scene_placement_validation'
POLY_RECORD_SIZE_T1 = 104
TYPE_NAMES = {0:'PATH', 1:'NPATH', 2:'BLOCK', 3:'REFER', 4:'EFFECT', 5:'EXIT', 6:'TAG', 7:'SCALE'}

def read_chunks(data: bytes):
    out = {}
    off = 0
    while off < len(data):
        if off + 8 > len(data):
            break
        cid, nxt = struct.unpack_from('<II', data, off)
        end = nxt if nxt else len(data)
        out[cid] = (off + 8, end)
        if nxt == 0:
            break
        off = nxt
    return out

def scene_record(data: bytes):
    chunks = read_chunks(data)
    if 0x3334000E not in chunks or 0x3334000C not in chunks:
        return None
    p, _ = chunks[0x3334000E]
    vals = struct.unpack_from('<8I', data, p)
    return {
        'numEntrance': vals[0],
        'numPoly': vals[1],
        'numTaggedActor': vals[2],
        'hSceneScript': vals[4],
        'hPoly': vals[6],
        'hTaggedActor': vals[7],
    }

def parse_polys(data: bytes, scene):
    start = scene['hPoly'] & 0x007FFFFF
    polys = []
    for i in range(scene['numPoly']):
        off = start + i * POLY_RECORD_SIZE_T1
        if off + POLY_RECORD_SIZE_T1 > len(data):
            break
        vals = struct.unpack_from('<26i', data, off)
        polys.append({
            'index': i,
            'compiled_type': vals[0],
            'category': TYPE_NAMES.get(vals[0], f'UNKNOWN_{vals[0]}'),
            'x': list(vals[1:5]),
            'y': list(vals[5:9]),
            'offset': off,
        })
    return polys

def scan_scenes():
    rows = []
    for path in sorted(ROOT.glob('*.SCN')):
        data = path.read_bytes()
        scene = scene_record(data)
        if not scene:
            continue
        polys = parse_polys(data, scene)
        counts = Counter(p['compiled_type'] for p in polys)
        rows.append({
            'scene': path.name,
            'num_poly': scene['numPoly'],
            'PATH': counts.get(0, 0),
            'NPATH': counts.get(1, 0),
            'BLOCK': counts.get(2, 0),
            'REFER': counts.get(3, 0),
            'EFFECT': counts.get(4, 0),
            'EXIT': counts.get(5, 0),
            'TAG': counts.get(6, 0),
            'SCALE': counts.get(7, 0),
        })
    return rows

def extract_support_artifacts():
    tmp = OUT / '_support'
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for zname in ['tinsel1_visual_asset_export_outputs.zip', 'tinsel1_scene_timeline_outputs.zip']:
        zpath = ROOT / zname
        if zpath.exists():
            with zipfile.ZipFile(zpath) as z:
                z.extractall(tmp)
    return tmp

def parse_args_display(s: str):
    args = {}
    for part in s.split('|'):
        part = part.strip()
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        v = v.strip()
        if v.startswith('imm:'):
            try:
                v = int(v[4:])
            except ValueError:
                v = v[4:]
        args[k.strip()] = v
    return args

def load_play_events(tmp: Path, scene: str):
    csv_path = tmp / 'scene_timeline' / f'{scene}_timeline.csv'
    rows = []
    if not csv_path.exists():
        return rows
    with open(csv_path, newline='') as f:
        for r in csv.DictReader(f):
            if r.get('libcall') != 'PLAY':
                continue
            a = parse_args_display(r.get('args_display', ''))
            rows.append({
                'seq': int(r['seq']),
                'film': a.get('film', r.get('film_args')),
                'x': a.get('x'),
                'y': a.get('y'),
                'args_display': r.get('args_display'),
            })
    return rows

def block_candidate_points(poly):
    # Conservative visual approximation of the recovered 4-corner / 4-pixel nudge model.
    pts = []
    xs, ys = poly['x'], poly['y']
    cx = sum(xs) / 4.0
    cy = sum(ys) / 4.0
    for i, (x, y) in enumerate(zip(xs, ys)):
        nx = 4 if x >= cx else -4
        ny = 4 if y >= cy else -4
        pts.append({'corner': i, 'corner_x': x, 'corner_y': y, 'candidate_x': x + nx, 'candidate_y': y + ny})
    return pts

def draw_scene_overlay(bg, polys, play_events, outpath):
    img = bg.convert('RGBA')
    draw = ImageDraw.Draw(img, 'RGBA')
    colors = {
        'PATH': ((0,180,255,32),(0,180,255,220)),
        'NPATH': ((0,130,255,32),(0,130,255,220)),
        'BLOCK': ((255,0,0,70),(255,0,0,255)),
        'REFER': ((255,255,0,30),(255,255,0,220)),
        'EXIT': ((255,128,0,36),(255,128,0,220)),
        'TAG': ((255,0,255,25),(255,0,255,180)),
    }
    for p in polys:
        fill, outline = colors.get(p['category'], ((180,180,180,20),(180,180,180,180)))
        pts = list(zip(p['x'], p['y']))
        draw.polygon(pts, fill=fill, outline=outline)
        tx = sum(p['x'])/4
        ty = sum(p['y'])/4
        draw.text((tx,ty), f"{p['category'][0]}{p['index']}", fill=(255,255,255,255))
    for p in [p for p in polys if p['category']=='BLOCK']:
        for c in block_candidate_points(p):
            x,y=c['candidate_x'], c['candidate_y']
            draw.ellipse((x-4,y-4,x+4,y+4), fill=(0,255,0,230), outline=(0,0,0,255))
            draw.line((c['corner_x'], c['corner_y'], x, y), fill=(0,255,0,180), width=1)
            draw.text((x+5,y-5), f"C{c['corner']}", fill=(0,255,0,255))
    # PLAY points from nominal immediate coordinates only if meaningful.
    for ev in play_events:
        x,y=ev.get('x'), ev.get('y')
        if isinstance(x,int) and isinstance(y,int) and x >= 0 and y >= 0:
            draw.ellipse((x-5,y-5,x+5,y+5), fill=(0,255,255,230), outline=(0,0,0,255))
            draw.text((x+7,y-7), f"PLAY {ev['seq']}", fill=(0,255,255,255))
    draw.rectangle((5,5,650,62), fill=(0,0,0,160))
    draw.text((12,10), "FINALE.SCN placement validation: compiled polygons + BLOCK candidate points", fill=(255,255,255,255))
    draw.text((12,30), "red=BLOCK, blue=PATH/NPATH, yellow=REFER, orange=EXIT, magenta=TAG, green=BLOCK corner candidates", fill=(255,255,255,255))
    img.save(outpath)

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    scan = scan_scenes()
    with open(OUT / 'scenes_with_polygon_counts.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(scan[0].keys()))
        w.writeheader()
        w.writerows(scan)
    block_scenes = [r for r in scan if r['BLOCK'] > 0]

    chosen = 'FINALE'
    data = (ROOT / f'{chosen}.SCN').read_bytes()
    scene = scene_record(data)
    polys = parse_polys(data, scene)
    blocks = [p for p in polys if p['category'] == 'BLOCK']

    tmp = extract_support_artifacts()
    bg_path = tmp / 'finale' / 'images' / '0184CAD8_img0064_1600x200.png'
    if bg_path.exists():
        bg = Image.open(bg_path)
        bg_source = str(bg_path.relative_to(tmp))
    else:
        bg = Image.new('RGBA', (1600, 220), (20, 20, 20, 255))
        bg_source = 'blank fallback'

    play_events = load_play_events(tmp, chosen)
    draw_scene_overlay(bg, polys, play_events, OUT / 'finale_block_polygon_placement_overlay.png')

    with open(OUT / 'finale_decoded_polygons.json', 'w') as f:
        json.dump(polys, f, indent=2)
    with open(OUT / 'finale_block_candidate_points.json', 'w') as f:
        json.dump([{'poly_index': p['index'], 'candidates': block_candidate_points(p)} for p in blocks], f, indent=2)
    manifest = {
        'chosen_scene': f'{chosen}.SCN',
        'reason': 'contains compiled POLY_BLOCK records and has an exported background image available',
        'background_source': bg_source,
        'block_scenes_found': block_scenes,
        'chosen_scene_polygon_counts': Counter(p['category'] for p in polys),
        'play_events': len(play_events),
        'play_events_with_nonnegative_immediate_xy': sum(1 for ev in play_events if isinstance(ev.get('x'),int) and isinstance(ev.get('y'),int) and ev['x'] >= 0 and ev['y'] >= 0),
        'outputs': {
            'overlay': 'finale_block_polygon_placement_overlay.png',
            'polygon_counts': 'scenes_with_polygon_counts.csv',
            'decoded_polygons': 'finale_decoded_polygons.json',
            'block_candidates': 'finale_block_candidate_points.json',
        },
        'limitations': [
            'Overlay uses compiled POLY_BLOCK polygons, not live runtime polygon table after script mutations.',
            'Green candidate points visualize the recovered 4-corner/4-pixel nudge model conservatively.',
            'PLAY points are nominal immediate coordinates where available; final runtime-snapped coordinates are not claimed.'
        ]
    }
    # Counter not JSON serializable
    manifest['chosen_scene_polygon_counts'] = dict(manifest['chosen_scene_polygon_counts'])
    with open(OUT / 'block_scene_placement_validation_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    with open(OUT / 'README.md', 'w') as f:
        f.write('# Block Scene Placement Validation\n\n')
        f.write('This harness scans uploaded scenes for compiled POLY_BLOCK records and generates a focused FINALE.SCN overlay.\n')

    zip_path = ROOT / 'block_scene_placement_validation_outputs.zip'
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            z.write(p, p.relative_to(OUT.parent))
        z.write(ROOT / 'block_scene_placement_validation_harness.py', 'block_scene_placement_validation_harness.py')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
