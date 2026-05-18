#!/usr/bin/env python3
import json, zipfile, csv, os, shutil, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/mnt/data')
OUT = ROOT / 'bar_playback_prototype'
VIS = ROOT / 'bar_visual_full' / 'visual_asset_export' / 'bar'
TIMELINE_ZIP = ROOT / 'tinsel1_scene_timeline_outputs.zip'
OUT.mkdir(exist_ok=True)
(OUT/'frames').mkdir(exist_ok=True)

# Load timeline and visual manifest
with zipfile.ZipFile(TIMELINE_ZIP) as z:
    timeline = json.loads(z.read('scene_timeline/BAR.json'))
vis_manifest = json.loads((VIS/'manifest.json').read_text())

# Map film handle -> first rendered image + frame info
film_to_first = {}
film_to_count = {}
for fg in vis_manifest.get('film_graph', []):
    fh = fg.get('film_handle')
    imgs = []
    frame_count = 0
    for reel in fg.get('reels', []):
        for fr in reel.get('frames', []):
            frame_count += 1
            for im in fr.get('images', []):
                if im.get('png'):
                    imgs.append(im)
    film_to_count[fh] = {'frames': frame_count, 'images': len(imgs)}
    if fh and imgs and fh not in film_to_first:
        film_to_first[fh] = imgs[0]

font = ImageFont.load_default()

def fit_thumb(img, max_w=180, max_h=100):
    img = img.convert('RGBA')
    w,h=img.size
    if w==0 or h==0: return img
    scale = min(max_w/w, max_h/h, 1.0)
    nw, nh = max(1,int(w*scale)), max(1,int(h*scale))
    return img.resize((nw,nh), Image.Resampling.NEAREST)

def text_panel(lines, size=(220,140)):
    im = Image.new('RGBA', size, (245,245,245,255))
    d = ImageDraw.Draw(im)
    y=6
    for line in lines:
        wrapped = textwrap.wrap(str(line), width=34) or ['']
        for part in wrapped:
            d.text((6,y), part, fill=(0,0,0,255), font=font)
            y += 11
        y += 1
        if y > size[1]-12: break
    d.rectangle((0,0,size[0]-1,size[1]-1), outline=(0,0,0,255))
    return im

# Create a visual card per scheduler event
cards=[]
proto_events=[]
for ev in timeline['events']:
    seq = ev.get('seq')
    lib = ev.get('libcall')
    cat = ev.get('category')
    film = None
    if ev.get('args'):
        for a in ev['args']:
            if a.get('type') == 'film':
                film = a.get('value')
                break
    title = f"#{seq} {lib}"
    subtitle = ev.get('args_display','')
    detail = f"src={ev.get('source')} ip={ev.get('ip')}"
    if film and film in film_to_first:
        imeta = film_to_first[film]
        png_path = VIS / imeta['png']
        thumb = fit_thumb(Image.open(png_path))
        card = Image.new('RGBA', (220,140), (255,255,255,255))
        d=ImageDraw.Draw(card)
        d.text((6,4), title, fill=(0,0,0,255), font=font)
        d.text((6,16), film, fill=(0,0,0,255), font=font)
        card.alpha_composite(thumb, ((220-thumb.width)//2, 34))
        d.rectangle((0,0,219,139), outline=(0,0,0,255))
        kind='rendered_film_preview'
        preview_rel = str(Path('frames') / f"event_{seq:03d}_{lib}.png")
        card.save(OUT/preview_rel)
    else:
        lines=[title, cat, subtitle or '(no args)', detail]
        card = text_panel(lines)
        kind='text_only_event'
        preview_rel = str(Path('frames') / f"event_{seq:03d}_{lib}.png")
        card.save(OUT/preview_rel)
    cards.append(card)
    proto_events.append({
        'seq':seq,'libcall':lib,'category':cat,'source':ev.get('source'),
        'script_handle':ev.get('script_handle'),'ip':ev.get('ip'),
        'args_display':ev.get('args_display'), 'film':film,
        'preview_kind':kind, 'preview_png':preview_rel,
        'film_frame_image_counts': film_to_count.get(film) if film else None,
        'interpretation': 'timeline order is VM-lite symbolic order; not exact runtime playback timing'
    })

# Timeline contact sheet
cols=4; cell_w=220; cell_h=140
rows=(len(cards)+cols-1)//cols
sheet=Image.new('RGBA',(cols*cell_w, rows*cell_h),(230,230,230,255))
for i, card in enumerate(cards):
    x=(i%cols)*cell_w; y=(i//cols)*cell_h
    sheet.alpha_composite(card,(x,y))
sheet.save(OUT/'bar_timeline_contact_sheet.png')

# film-only strip
film_cards=[cards[i] for i,e in enumerate(proto_events) if e['film']]
cols2=5; rows2=(len(film_cards)+cols2-1)//cols2
strip=Image.new('RGBA',(cols2*cell_w, max(1,rows2)*cell_h),(230,230,230,255))
for i, card in enumerate(film_cards):
    strip.alpha_composite(card,((i%cols2)*cell_w,(i//cols2)*cell_h))
strip.save(OUT/'bar_film_event_strip.png')

# Copy background preview if present
bg_event = next((e for e in proto_events if e['libcall']=='BACKGROUND' and e['film']), None)
if bg_event and bg_event['film'] in film_to_first:
    src = VIS / film_to_first[bg_event['film']]['png']
    shutil.copy2(src, OUT/'bar_background_preview.png')

# Manifest and CSV
manifest={
    'scene':'BAR.SCN',
    'prototype_type':'bounded VM-lite scheduler playback validation',
    'source_timeline':'scene_timeline/BAR.json',
    'source_visual_manifest':str(VIS/'manifest.json'),
    'event_count':len(proto_events),
    'film_event_count':sum(1 for e in proto_events if e['film']),
    'rendered_film_previews':sum(1 for e in proto_events if e['preview_kind']=='rendered_film_preview'),
    'text_only_events':sum(1 for e in proto_events if e['preview_kind']=='text_only_event'),
    'limitations':[
        'VM-lite symbolic ordering, not exact runtime timing',
        'PLAY placement not yet applied spatially',
        'events are previewed as representative first film images, not full animation playback',
        'wait/dialogue/control events are shown as text panels'
    ],
    'events':proto_events
}
(OUT/'bar_playback_manifest.json').write_text(json.dumps(manifest,indent=2))
with open(OUT/'bar_playback_timeline.csv','w',newline='') as f:
    w=csv.DictWriter(f, fieldnames=['seq','libcall','category','film','source','ip','args_display','preview_kind','preview_png'])
    w.writeheader()
    for e in proto_events:
        w.writerow({k:e.get(k) for k in w.fieldnames})

# README
(OUT/'README.md').write_text(f"""# BAR.SCN Minimal Playback Prototype\n\nThis is a bounded visual validation prototype for `BAR.SCN`. It uses the VM-lite scheduler timeline and film/image renderer to create ordered event previews.\n\n## Outputs\n\n- `bar_timeline_contact_sheet.png` — all 41 scheduler events in VM-lite order\n- `bar_film_event_strip.png` — film-related events only\n- `bar_background_preview.png` — first BACKGROUND film preview\n- `bar_playback_manifest.json` — structured prototype manifest\n- `bar_playback_timeline.csv` — flat event table\n- `frames/` — per-event preview cards\n\n## Counts\n\n- events: {len(proto_events)}\n- film events: {sum(1 for e in proto_events if e['film'])}\n- rendered film previews: {sum(1 for e in proto_events if e['preview_kind']=='rendered_film_preview')}\n\n## Limitations\n\nThis is not exact in-game playback. It validates that timeline events resolve to renderable films/images and provides an inspectable order. Runtime placement, full animation timing, branch determinism, and scheduler side effects remain future work.\n""")

# zip
zip_path=ROOT/'bar_scene_playback_prototype_outputs.zip'
if zip_path.exists(): zip_path.unlink()
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        z.write(p, p.relative_to(OUT.parent))
print(json.dumps({'out':str(OUT),'zip':str(zip_path),'events':len(proto_events),'film_events':sum(1 for e in proto_events if e['film'])}, indent=2))
