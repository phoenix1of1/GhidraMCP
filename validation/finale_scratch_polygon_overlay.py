#!/usr/bin/env python3
"""Overlay recovered scratch-polygon model on FINALE.SCN BLOCK geometry.

This is a validation visualization, not a runtime snapshot. It shows:
- compiled FINALE polygons
- the real compiled BLOCK polygon
- the recovered 4-corner/4-pixel BLOCK candidate points
- scratch polygon rectangles generated from the recovered 0x37298 formula

Because we do not have a live DWB.EXE runtime memory snapshot, actual target_x/target_y
and footprint extents for each runtime PLAY call are not available. The overlay therefore
separates two layers:
  1. nominal/immediate PLAY scratch rectangles where PCODE gives non-negative x/y
  2. formula-demonstration scratch rectangles centered on BLOCK candidate points
"""
from __future__ import annotations
import csv, json, shutil, struct, zipfile
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw

ROOT = Path('/mnt/data')
OUT = ROOT/'finale_scratch_polygon_overlay'
POLY_RECORD_SIZE_T1 = 104
TYPE_NAMES = {0:'PATH',1:'NPATH',2:'BLOCK',3:'REFER',4:'EFFECT',5:'EXIT',6:'TAG',7:'SCALE'}


def read_chunks(data: bytes):
    out={}; off=0
    while off < len(data):
        if off+8 > len(data): break
        cid,nxt=struct.unpack_from('<II', data, off)
        end=nxt if nxt else len(data)
        out[cid]=(off+8,end)
        if nxt==0: break
        off=nxt
    return out


def scene_record(data: bytes):
    chunks=read_chunks(data)
    p,_=chunks[0x3334000E]
    vals=struct.unpack_from('<8I', data, p)
    return {'numEntrance':vals[0], 'numPoly':vals[1], 'numTaggedActor':vals[2], 'hSceneScript':vals[4], 'hPoly':vals[6]}


def parse_polys(data: bytes, scene):
    start=scene['hPoly'] & 0x007FFFFF
    polys=[]
    for i in range(scene['numPoly']):
        off=start+i*POLY_RECORD_SIZE_T1
        vals=struct.unpack_from('<26i', data, off)
        polys.append({'index':i,'compiled_type':vals[0],'category':TYPE_NAMES.get(vals[0],f'UNKNOWN_{vals[0]}'), 'x':list(vals[1:5]), 'y':list(vals[5:9]), 'offset':off})
    return polys


def extract_support():
    tmp=OUT/'_support'
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    for zname in ['tinsel1_visual_asset_export_outputs.zip','tinsel1_scene_timeline_outputs.zip']:
        zp=ROOT/zname
        if zp.exists():
            with zipfile.ZipFile(zp) as z: z.extractall(tmp)
    return tmp


def parse_args_display(s):
    args={}
    for part in s.split('|'):
        part=part.strip()
        if '=' not in part: continue
        k,v=part.split('=',1); k=k.strip(); v=v.strip()
        if v.startswith('imm:'):
            try: v=int(v[4:])
            except Exception: v=v[4:]
        args[k]=v
    return args


def load_play_events(tmp):
    p=tmp/'scene_timeline'/'FINALE_timeline.csv'
    rows=[]
    with open(p, newline='') as f:
        for r in csv.DictReader(f):
            if r.get('libcall')!='PLAY': continue
            a=parse_args_display(r.get('args_display',''))
            rows.append({'seq':int(r['seq']),'film':a.get('film'), 'x':a.get('x'), 'y':a.get('y'), 'args_display':r.get('args_display','')})
    return rows


def block_candidate_points(poly):
    pts=[]; xs=poly['x']; ys=poly['y']; cx=sum(xs)/4; cy=sum(ys)/4
    for i,(x,y) in enumerate(zip(xs,ys)):
        nx=4 if x>=cx else -4; ny=4 if y>=cy else -4
        pts.append({'corner':i,'corner_x':x,'corner_y':y,'candidate_x':x+nx,'candidate_y':y+ny})
    return pts


def scratch_rect(cx, cy, rx, ry):
    return [(cx-rx, cy-ry), (cx+rx, cy-ry), (cx+rx, cy+ry), (cx-rx, cy+ry)]


def draw_overlay(bg, polys, play_events, outpath):
    img=bg.convert('RGBA')
    d=ImageDraw.Draw(img, 'RGBA')
    colors={'PATH':((0,180,255,30),(0,180,255,210)), 'NPATH':((0,130,255,30),(0,130,255,210)), 'BLOCK':((255,0,0,72),(255,0,0,255)), 'REFER':((255,255,0,28),(255,255,0,220)), 'EXIT':((255,128,0,35),(255,128,0,220)), 'TAG':((255,0,255,22),(255,0,255,180))}
    for p in polys:
        fill, outline=colors.get(p['category'], ((180,180,180,20),(180,180,180,180)))
        pts=list(zip(p['x'],p['y']))
        d.polygon(pts, fill=fill, outline=outline)
        d.text((sum(p['x'])/4, sum(p['y'])/4), f"{p['category'][0]}{p['index']}", fill=(255,255,255,255))

    blocks=[p for p in polys if p['category']=='BLOCK']
    demo_scratch=[]
    for p in blocks:
        for c in block_candidate_points(p):
            x,y=c['candidate_x'],c['candidate_y']
            d.ellipse((x-4,y-4,x+4,y+4), fill=(0,255,0,230), outline=(0,0,0,255))
            d.line((c['corner_x'],c['corner_y'],x,y), fill=(0,255,0,190), width=1)
            d.text((x+5,y-5), f"C{c['corner']}", fill=(0,255,0,255))
            # Demonstrate the 0x37298 scratch-rectangle formula using a fixed footprint extent.
            # This is not a claimed runtime value.
            rect=scratch_rect(x,y,16,28)
            demo_scratch.append({'center_x':x,'center_y':y,'rx':16,'ry':28,'source':'BLOCK_candidate_formula_demo','polygon':rect})
            d.polygon(rect, outline=(255,255,255,230), fill=(255,255,255,28))

    nominal=[]
    for ev in play_events:
        x,y=ev['x'],ev['y']
        if isinstance(x,int) and isinstance(y,int) and x>=0 and y>=0:
            # Draw nominal PCODE coordinate and small scratch rectangle using unknown/default extent marker.
            d.ellipse((x-5,y-5,x+5,y+5), fill=(0,255,255,230), outline=(0,0,0,255))
            d.text((x+7,y+2), f"PLAY {ev['seq']}", fill=(0,255,255,255))
            rect=scratch_rect(x,y,16,28)
            nominal.append({'seq':ev['seq'],'film':ev['film'],'target_x':x,'target_y':y,'rx_demo':16,'ry_demo':28,'polygon':rect})
            d.polygon(rect, outline=(0,255,255,220), fill=(0,255,255,22))

    d.rectangle((5,5,920,82), fill=(0,0,0,180))
    d.text((12,10), 'FINALE.SCN scratch-polygon visualization overlay', fill=(255,255,255,255))
    d.text((12,30), 'red=compiled BLOCK; green=BLOCK candidate points; white=0x37298 formula demo at candidates; cyan=nominal PLAY target scratch rectangles', fill=(255,255,255,255))
    d.text((12,50), 'Note: no live DWB.EXE runtime memory snapshot; scratch extents shown here are visualization/demo extents, not claimed final runtime values.', fill=(255,220,120,255))
    img.save(outpath)
    return nominal, demo_scratch


def main():
    shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir()
    tmp=extract_support()
    data=(ROOT/'FINALE.SCN').read_bytes()
    scene=scene_record(data); polys=parse_polys(data, scene)
    bg_path=tmp/'finale'/'images'/'0184CAD8_img0064_1600x200.png'
    bg=Image.open(bg_path) if bg_path.exists() else Image.new('RGBA',(1600,220),(20,20,20,255))
    play_events=load_play_events(tmp)
    nominal, demo=draw_overlay(bg, polys, play_events, OUT/'finale_scratch_polygon_overlay.png')
    blocks=[p for p in polys if p['category']=='BLOCK']
    counts=dict(Counter(p['category'] for p in polys))
    manifest={
        'scene':'FINALE.SCN',
        'purpose':'Integrate scratch-polygon visualization with FINALE BLOCK overlay.',
        'polygon_counts':counts,
        'compiled_block_polygons':len(blocks),
        'play_events_seen':len(play_events),
        'play_events_with_nominal_nonnegative_xy':len(nominal),
        'scratch_polygon_layers':{
            'nominal_play_targets':len(nominal),
            'block_candidate_formula_demo_rectangles':len(demo),
        },
        'runtime_claims':{
            'live_runtime_snapshot_available':False,
            'final_snapped_coordinates_computed':False,
            'scratch_extents_are_runtime_values':False,
        },
        'outputs':{
            'overlay':'finale_scratch_polygon_overlay.png',
            'manifest':'finale_scratch_polygon_overlay_manifest.json',
            'nominal_play_scratch_rectangles':'finale_nominal_play_scratch_rectangles.json',
            'block_candidate_scratch_rectangles':'finale_block_candidate_scratch_rectangles.json',
        }
    }
    (OUT/'finale_scratch_polygon_overlay_manifest.json').write_text(json.dumps(manifest, indent=2))
    (OUT/'finale_nominal_play_scratch_rectangles.json').write_text(json.dumps(nominal, indent=2))
    (OUT/'finale_block_candidate_scratch_rectangles.json').write_text(json.dumps(demo, indent=2))
    (OUT/'README.md').write_text('# FINALE Scratch Polygon Overlay\n\nValidation overlay integrating recovered scratch-polygon formula with FINALE BLOCK geometry.\n')
    zip_path=ROOT/'finale_scratch_polygon_overlay_outputs.zip'
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            z.write(p, p.relative_to(OUT.parent))
        z.write(ROOT/'finale_scratch_polygon_overlay.py','finale_scratch_polygon_overlay.py')
    entry=ROOT/'finale_scratch_polygon_overlay_entry.md'
    entry.write_text('''# 55. FINALE Scratch Polygon Overlay Integration\n\nIntegrated scratch-polygon visualization with the FINALE BLOCK overlay.\n\nKey result:\n\n```text\nThe recovered 0x37298 scratch-rectangle formula is now visualized alongside real compiled FINALE BLOCK geometry.\n```\n\nImportant validation caveat:\n\n```text\nNo live DWB.EXE runtime memory snapshot is available, so final runtime-snapped coordinates are not claimed.\n```\n\nResult:\n\n| Metric | Count |\n|---|---:|\n| compiled BLOCK polygons | {blocks} |\n| PLAY events seen | {events} |\n| nominal PLAY target scratch rectangles | {nominal} |\n| BLOCK-candidate formula-demo rectangles | {demo} |\n\nNext target:\n\n```text\nCapture or emulate RuntimeMoverPlacementState values for a PLAY event so scratch extents become runtime-derived rather than demo-derived.\n```\n'''.format(blocks=len(blocks), events=len(play_events), nominal=len(nominal), demo=len(demo)))
    print(json.dumps(manifest, indent=2))

if __name__=='__main__': main()
