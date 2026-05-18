#!/usr/bin/env python3
"""BAR.SCN runtime-placement validation harness.

Generates scene-space overlay images for validating PLAY placement:
- BAR background
- decoded compiled BLOCK polygons from BAR.SCN chunk 0x3334000C
- PLAY nominal/fallback coordinates from bar_scene_space_playback_timeline.csv

This is validation tooling: it does not claim to compute final snapped coordinates.
"""
from __future__ import annotations
import csv, json, math, os, struct, zipfile
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/mnt/data')
OUT = ROOT / 'bar_runtime_placement_validation'
SCN = ROOT / 'BAR.SCN'
SCENE_ZIP = ROOT / 'bar_scene_space_playback_outputs.zip'

POLY_RECORD_SIZE_T1 = 104
POLY_PATH_COMPILED = 0
POLY_NPATH_COMPILED = 1
POLY_BLOCK_COMPILED = 2
POLY_REFER_COMPILED = 3
POLY_EXIT_COMPILED = 5
POLY_TAG_COMPILED = 6


def read_chunks(data: bytes):
    off = 0
    out = []
    while off < len(data):
        if off + 8 > len(data): break
        cid, nxt = struct.unpack_from('<II', data, off)
        end = nxt if nxt else len(data)
        out.append({'offset': off, 'id': cid, 'next': nxt, 'payload': off+8, 'end': end, 'size': end-(off+8)})
        if nxt == 0: break
        off = nxt
    return out


def parse_scene(data: bytes):
    chunks = {c['id']: c for c in read_chunks(data)}
    scene_chunk = chunks[0x3334000E]
    vals = struct.unpack_from('<8I', data, scene_chunk['payload'])
    return {
        'numEntrance': vals[0], 'numPoly': vals[1], 'numTaggedActor': vals[2], 'defRefer': vals[3],
        'hSceneScript': vals[4], 'hEntrance': vals[5], 'hPoly': vals[6], 'hTaggedActor': vals[7],
    }, chunks


def parse_compiled_polys(data: bytes, hpoly: int, num_poly: int):
    start = hpoly & 0x007FFFFF
    polys = []
    for i in range(num_poly):
        off = start + i * POLY_RECORD_SIZE_T1
        vals = struct.unpack_from('<26i', data, off)
        ptype = vals[0]
        xs = list(vals[1:5])
        ys = list(vals[5:9])
        polys.append({
            'index': i,
            'offset': off,
            'compiled_type': ptype,
            'runtime_type': ({POLY_PATH_COMPILED:'PATH', POLY_NPATH_COMPILED:'PATH_NODE', POLY_BLOCK_COMPILED:'BLOCK', POLY_REFER_COMPILED:'REFER', POLY_EXIT_COMPILED:'EXIT', POLY_TAG_COMPILED:'TAG'}).get(ptype, 'UNKNOWN'),
            'x': xs,
            'y': ys,
            'tagx': vals[9], 'tagy': vals[10], 'hTagtext': vals[11],
            'nodex': vals[12], 'nodey': vals[13], 'hFilm': vals[14],
            'reftype': vals[15], 'id': vals[16], 'scale1': vals[17], 'scale2': vals[18],
            'reel': vals[19], 'zFactor': vals[20], 'nodecount': vals[21],
            'pnodelistx': vals[22], 'pnodelisty': vals[23], 'plinelist': vals[24], 'hScript': vals[25],
        })
    return polys


def extract_scene_zip():
    temp = OUT / '_scene_zip'
    if temp.exists():
        import shutil; shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SCENE_ZIP) as z:
        z.extractall(temp)
    return temp


def load_timeline(temp: Path):
    rows = []
    with open(temp / 'bar_scene_space_playback_timeline.csv', newline='') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def unique_play_events(rows):
    d = {}
    for r in rows:
        if r['libcall'] != 'PLAY':
            continue
        seq = int(r['event_seq'])
        if seq not in d:
            d[seq] = {
                'event_seq': seq,
                'film': r['film'],
                'x': int(r['x_used']),
                'y': int(r['y_used']),
                'position_source': r['position_source'],
                'frame_count': 0,
            }
        d[seq]['frame_count'] += 1
    return [d[k] for k in sorted(d)]


def poly_bbox(poly):
    return min(poly['x']), min(poly['y']), max(poly['x']), max(poly['y'])


def draw_poly_set(draw, polys, fill, outline, label_prefix):
    for p in polys:
        pts = list(zip(p['x'], p['y']))
        draw.polygon(pts, fill=fill, outline=outline)
        cx = sum(p['x'])/4; cy = sum(p['y'])/4
        draw.text((cx, cy), f"{label_prefix}{p['index']}", fill=(255,255,255,255))

def draw_overlay(bg: Image.Image, block_polys, path_polys, refer_polys, tag_polys, exit_polys, play_events, outpath: Path, title: str):
    img = bg.convert('RGBA')
    draw = ImageDraw.Draw(img, 'RGBA')
    draw_poly_set(draw, path_polys, (0,180,255,28), (0,180,255,210), 'P')
    draw_poly_set(draw, block_polys, (255,0,0,40), (255,0,0,230), 'B')
    draw_poly_set(draw, refer_polys, (255,255,0,22), (255,255,0,190), 'R')
    draw_poly_set(draw, exit_polys, (255,128,0,30), (255,128,0,210), 'E')
    draw_poly_set(draw, tag_polys, (255,0,255,18), (255,0,255,150), 'T')
    # Draw play target points
    for ev in play_events:
        x,y = ev['x'], ev['y']
        r=5
        draw.ellipse((x-r,y-r,x+r,y+r), fill=(0,255,255,220), outline=(0,0,0,255))
        draw.text((x+7,y-7), f"E{ev['event_seq']}", fill=(0,255,255,255))
    # Legend
    draw.rectangle((5,5,455,58), fill=(0,0,0,150))
    draw.text((12,10), title, fill=(255,255,255,255))
    draw.text((12,30), "blue=PATH/NPATH, red=BLOCK, yellow=REFER, orange=EXIT, magenta=TAG, cyan=PLAY point", fill=(255,255,255,255))
    img.save(outpath)
    return img


def nearest_block_summary(block_polys, play_events):
    rows=[]
    for ev in play_events:
        x,y=ev['x'],ev['y']
        candidates=[]
        for p in block_polys:
            bx1,by1,bx2,by2=poly_bbox(p)
            # distance to bbox center and bbox containment approximation for review only
            cx=sum(p['x'])/4; cy=sum(p['y'])/4
            dist=abs(x-cx)+abs(y-cy)
            candidates.append((dist,p,bx1,by1,bx2,by2))
        candidates.sort(key=lambda t:t[0])
        for rank,(dist,p,bx1,by1,bx2,by2) in enumerate(candidates[:3], start=1):
            rows.append({
                'event_seq': ev['event_seq'], 'film': ev['film'], 'x': x, 'y': y,
                'position_source': ev['position_source'], 'rank': rank,
                'block_poly_index': p['index'], 'bbox': f'{bx1},{by1},{bx2},{by2}',
                'center_manhattan_distance': int(dist),
            })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = SCN.read_bytes()
    scene, chunks = parse_scene(data)
    polys = parse_compiled_polys(data, scene['hPoly'], scene['numPoly'])
    block_polys = [p for p in polys if p['compiled_type'] == POLY_BLOCK_COMPILED]
    path_polys = [p for p in polys if p['compiled_type'] in (POLY_PATH_COMPILED, POLY_NPATH_COMPILED)]
    refer_polys = [p for p in polys if p['compiled_type'] == POLY_REFER_COMPILED]
    tag_polys = [p for p in polys if p['compiled_type'] == POLY_TAG_COMPILED]
    exit_polys = [p for p in polys if p['compiled_type'] == POLY_EXIT_COMPILED]
    temp = extract_scene_zip()
    bg = Image.open(temp / 'bar_background_scene_scaled.png')
    rows = load_timeline(temp)
    play_events = unique_play_events(rows)

    overlay = draw_overlay(bg, block_polys, path_polys, refer_polys, tag_polys, exit_polys, play_events, OUT/'bar_polygon_play_overlay.png', 'BAR.SCN runtime-placement validation overlay')

    # Create per-event validation panels around first 13 PLAY events
    panels_dir = OUT/'event_panels'; panels_dir.mkdir(exist_ok=True)
    for ev in play_events:
        img = bg.convert('RGBA')
        draw = ImageDraw.Draw(img, 'RGBA')
        for p in block_polys:
            draw.polygon(list(zip(p['x'], p['y'])), fill=(255,0,0,24), outline=(255,0,0,180))
        x,y=ev['x'],ev['y']
        # draw an illustrative scratch-rectangle placeholder around target (not final runtime)
        # use 16x32 default review footprint; marked provisional
        hw,hh=16,32
        draw.rectangle((x-hw,y-hh,x+hw,y+hh), outline=(0,255,255,220), width=2)
        draw.ellipse((x-5,y-5,x+5,y+5), fill=(0,255,255,220), outline=(0,0,0,255))
        draw.rectangle((5,5,500,74), fill=(0,0,0,160))
        draw.text((12,10), f"PLAY event {ev['event_seq']} film {ev['film']}", fill=(255,255,255,255))
        draw.text((12,30), f"point=({x},{y}) source={ev['position_source']}", fill=(255,255,255,255))
        draw.text((12,50), "cyan rectangle = provisional target footprint placeholder; red = BLOCK polygons", fill=(255,255,255,255))
        img.save(panels_dir/f"event_{ev['event_seq']:03d}_{ev['film']}_placement_validation.png")

    nearest = nearest_block_summary(block_polys, play_events)
    with open(OUT/'bar_play_event_nearest_block_polygons.csv','w',newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(nearest[0].keys()) if nearest else [])
        w.writeheader(); w.writerows(nearest)

    with open(OUT/'bar_decoded_block_polygons.json','w') as f:
        json.dump(block_polys, f, indent=2)

    manifest={
        'scene':'BAR.SCN',
        'tool':'bar_runtime_placement_validation_harness.py',
        'purpose':'visual validation harness for runtime placement convergence',
        'num_polygons':scene['numPoly'],
        'compiled_path_polygons': len(path_polys),
        'compiled_block_polygons':len(block_polys),
        'compiled_refer_polygons': len(refer_polys),
        'compiled_exit_polygons': len(exit_polys),
        'compiled_tag_polygons': len(tag_polys),
        'play_events':len(play_events),
        'final_runtime_snap_computed':False,
        'limitations':[
            'PLAY points are nominal/fallback timeline coordinates, not final snapped runtime values.',
            'Scratch footprint rectangle in per-event panels is a placeholder unless runtime extents are supplied.',
            'Polygon overlay uses compiled polygon categories decoded from BAR.SCN; BAR has no compiled POLY_BLOCK records in this sample.'
        ],
        'outputs':{
            'overlay':'bar_polygon_play_overlay.png',
            'block_polygons':'bar_decoded_block_polygons.json',
            'nearest_block_csv':'bar_play_event_nearest_block_polygons.csv',
            'event_panels':'event_panels/'
        }
    }
    with open(OUT/'bar_runtime_placement_validation_manifest.json','w') as f:
        json.dump(manifest,f,indent=2)
    with open(OUT/'README.md','w') as f:
        f.write('# BAR Runtime Placement Validation Harness\n\n')
        f.write('This package overlays decoded BAR.SCN polygon categories and PLAY event target points to support visual validation of runtime placement semantics.\n\n')
        f.write('The output is a validation harness, not final snapped playback.\n')

    zip_path=ROOT/'bar_runtime_placement_validation_outputs.zip'
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for path in OUT.rglob('*'):
            z.write(path, path.relative_to(OUT.parent))
        z.write(ROOT/'bar_runtime_placement_validation_harness.py','bar_runtime_placement_validation_harness.py')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
