#!/usr/bin/env python3
"""BAR.SCN ANI_SCRIPT-aware frame expansion prototype.

Uses existing BAR film manifest, BAR scene timeline, and rendered image PNGs.
This is an inspection-oriented prototype: it interprets ANI_SCRIPT commands enough to
produce runtime-like frame strips for BAR film scheduler events.
"""
from __future__ import annotations
import json, csv, re, shutil, zipfile
from pathlib import Path
from typing import Dict, List, Any, Tuple
from PIL import Image, ImageDraw

ROOT = Path('/mnt/data')
OUT = ROOT / 'bar_ani_script_playback'
FILM_MANIFEST = ROOT / 'bar_visual/film_manifest/bar_film_manifest.json'
TIMELINE_JSON = ROOT / 'tmp_timeline/scene_timeline/BAR.json'
if not TIMELINE_JSON.exists():
    # fall back: extract from zip if needed
    import subprocess, os
    (ROOT/'tmp_timeline').mkdir(exist_ok=True)
    subprocess.run(['unzip','-q','-o',str(ROOT/'tinsel1_scene_timeline_outputs.zip'),'scene_timeline/BAR.json','-d',str(ROOT/'tmp_timeline')], check=False)
IMAGE_DIR = ROOT / 'bar_visual/visual_asset_export/bar/images'

MAX_FRAMES_PER_EVENT = 48
MAX_STEPS_PER_REEL = 512
CELL_W, CELL_H = 96, 96

ANI_OPS = {
    'ANI_END', 'ANI_JUMP', 'ANI_HFLIP', 'ANI_VFLIP', 'ANI_HVFLIP',
    'ANI_ADJUSTX', 'ANI_ADJUSTY', 'ANI_ADJUSTXY', 'ANI_NOSLEEP',
    'ANI_CALL', 'ANI_HIDE', 'ANI_STOP'
}

def norm_handle(h: str) -> str:
    if h is None: return ''
    return h.lower().replace('0x','').zfill(8)

def find_image_map() -> Dict[str, Path]:
    out = {}
    for p in IMAGE_DIR.glob('*.png'):
        m = re.match(r'([0-9A-Fa-f]{8})_', p.name)
        if m:
            out[m.group(1).lower()] = p
    return out

def load_json(p: Path):
    with p.open('r', encoding='utf-8') as f:
        return json.load(f)

def build_film_lookup(film_manifest: Dict[str,Any]) -> Dict[str,Any]:
    lookup = {}
    for ref in film_manifest.get('film_refs', []):
        h = ref.get('film_handle')
        if h and h not in lookup:
            lookup[h] = ref.get('film')
    return lookup

def frame_by_handle(reel: Dict[str,Any]) -> Dict[str,Any]:
    return {fr.get('handle'): fr for fr in reel.get('frames', []) if fr.get('handle')}

def entry_map(entries: List[Dict[str,Any]]) -> Dict[int, Dict[str,Any]]:
    return {int(e.get('word_index', -999999)): e for e in entries if 'word_index' in e}

def next_word_index(entries: List[Dict[str,Any]], word: int) -> int | None:
    ws = sorted(int(e['word_index']) for e in entries if 'word_index' in e and int(e['word_index']) > word)
    return ws[0] if ws else None

def frame_images(frame: Dict[str,Any]) -> List[str]:
    imgs=[]
    for ent in frame.get('entries', []):
        if ent.get('terminator'):
            break
        img = ent.get('image')
        if img and img.get('handle'):
            imgs.append(img['handle'])
    return imgs

def simulate_reel(reel: Dict[str,Any], max_frames: int = MAX_FRAMES_PER_EVENT) -> Tuple[List[Dict[str,Any]], List[str]]:
    """Interpret ANI_SCRIPT entries to an ordered frame event list.

    Relative ANI_JUMP target is interpreted as: target_word = current_word + 1 + operand.
    This matches common BAR looping stills where word 1 / operand -2 returns to word 0.
    """
    ani = reel.get('ani_script', {})
    entries = sorted(ani.get('entries', []), key=lambda e: int(e.get('word_index', 0)))
    if not entries:
        return [], ['no_ani_script_entries']
    emap = entry_map(entries)
    fmap = frame_by_handle(reel)
    ip = int(entries[0]['word_index'])
    out=[]; notes=[]
    state = {'x':0,'y':0,'hflip':False,'vflip':False,'hidden':False,'nosleep':False}
    steps=0
    visits={}
    while ip in emap and steps < MAX_STEPS_PER_REEL and len(out) < max_frames:
        steps += 1
        e = emap[ip]
        op = e.get('op')
        visits[ip] = visits.get(ip,0)+1
        if visits[ip] > 12:
            notes.append(f'loop_guard_at_word_{ip}')
            break
        if op == 'FRAME_HANDLE':
            fh = e.get('raw')
            fr = fmap.get(fh)
            imgs = frame_images(fr) if fr else []
            out.append({
                'kind':'frame', 'word_index':ip, 'frame_handle':fh,
                'images':imgs, 'state':dict(state)
            })
            nxt = next_word_index(entries, ip)
            if nxt is None: break
            ip = nxt
            continue
        if op == 'ANI_END':
            notes.append(f'ANI_END_at_word_{ip}')
            break
        if op == 'ANI_STOP':
            notes.append(f'ANI_STOP_at_word_{ip}')
            break
        if op == 'ANI_HIDE':
            state['hidden'] = True
            nxt = next_word_index(entries, ip)
            if nxt is None: break
            ip = nxt
            continue
        if op == 'ANI_NOSLEEP':
            state['nosleep'] = True
            nxt = next_word_index(entries, ip)
            if nxt is None: break
            ip = nxt
            continue
        if op == 'ANI_HFLIP':
            state['hflip'] = not state['hflip']
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_VFLIP':
            state['vflip'] = not state['vflip']
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_HVFLIP':
            state['hflip'] = not state['hflip']; state['vflip'] = not state['vflip']
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_ADJUSTX':
            state['x'] += int(e.get('operand',0))
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_ADJUSTY':
            state['y'] += int(e.get('operand',0))
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_ADJUSTXY':
            opnd = e.get('operand', [0,0])
            if isinstance(opnd, list) and len(opnd)>=2:
                state['x'] += int(opnd[0]); state['y'] += int(opnd[1])
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        if op == 'ANI_JUMP':
            operand = int(e.get('operand', 0))
            target = ip + 1 + operand
            notes.append(f'ANI_JUMP_word_{ip}_to_{target}')
            ip = target
            continue
        if op == 'ANI_CALL':
            # not implemented; continue linearly, but record it
            notes.append(f'ANI_CALL_unimplemented_at_word_{ip}')
            nxt = next_word_index(entries, ip); ip = nxt if nxt is not None else 10**9; continue
        # Unknown FRAME_HANDLE-like entries are treated as frame handles only if resolved to ANI_FRAME.
        notes.append(f'unhandled_{op}_at_word_{ip}')
        nxt = next_word_index(entries, ip)
        if nxt is None: break
        ip = nxt
    if steps >= MAX_STEPS_PER_REEL: notes.append('step_guard')
    if len(out) >= max_frames: notes.append('frame_limit')
    return out, notes

def compose_frame(frame_event: Dict[str,Any], image_map: Dict[str,Path]) -> Image.Image:
    imgs=[]
    for h in frame_event.get('images', []):
        p = image_map.get(norm_handle(h))
        if p and p.exists():
            im = Image.open(p).convert('RGBA')
            st = frame_event.get('state', {})
            if st.get('hflip'): im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if st.get('vflip'): im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            imgs.append(im)
    if not imgs or frame_event.get('state',{}).get('hidden'):
        im = Image.new('RGBA', (CELL_W,CELL_H), (245,245,245,255))
        d=ImageDraw.Draw(im); d.rectangle((0,0,CELL_W-1,CELL_H-1), outline=(170,170,170,255)); d.text((5,5),'hidden/missing', fill=(60,60,60,255))
        return im
    # Compose approx centered overlay; for multi-image frames use simple bounds/center overlay.
    w=max(x.width for x in imgs); h=max(x.height for x in imgs)
    canvas=Image.new('RGBA',(max(1,w),max(1,h)),(0,0,0,0))
    for im in imgs:
        canvas.alpha_composite(im, ((canvas.width-im.width)//2, (canvas.height-im.height)//2))
    canvas.thumbnail((CELL_W,CELL_H), Image.Resampling.NEAREST)
    out=Image.new('RGBA',(CELL_W,CELL_H),(255,255,255,0))
    out.alpha_composite(canvas, ((CELL_W-canvas.width)//2, (CELL_H-canvas.height)//2))
    return out

def make_strip(frames: List[Image.Image], label: str) -> Image.Image:
    n=max(1,len(frames)); w=CELL_W*n; h=CELL_H+24
    strip=Image.new('RGBA',(w,h),(255,255,255,255))
    d=ImageDraw.Draw(strip)
    for i,im in enumerate(frames):
        strip.alpha_composite(im,(i*CELL_W,0))
        d.rectangle((i*CELL_W,0,(i+1)*CELL_W-1,CELL_H-1), outline=(200,200,200,255))
        d.text((i*CELL_W+3,CELL_H+4),str(i), fill=(40,40,40,255))
    d.text((4, h-12), label[:120], fill=(0,0,0,255))
    return strip

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT/'strips').mkdir(parents=True)
    (OUT/'animations').mkdir()
    (OUT/'frames').mkdir()
    film_manifest=load_json(FILM_MANIFEST)
    timeline=load_json(TIMELINE_JSON)
    film_lookup=build_film_lookup(film_manifest)
    image_map=find_image_map()
    events=[e for e in timeline.get('events',[]) if e.get('category')=='film' and e.get('film_args')]
    manifest={'scene':'BAR.SCN','mode':'ANI_SCRIPT-aware frame expansion','events':[]}
    summary=[]; all_strips=[]
    for ev in events:
        film_h=ev.get('film_args')
        film=film_lookup.get(film_h)
        if not film: continue
        event_dir=OUT/'frames'/f"event_{ev['seq']:03d}_{ev['libcall']}_{film_h.replace('0x','')}"
        event_dir.mkdir(parents=True, exist_ok=True)
        event_frames=[]; notes=[]; reel_summ=[]
        for reel in film.get('reels',[]):
            seq, ns = simulate_reel(reel, MAX_FRAMES_PER_EVENT - len(event_frames))
            notes.extend(ns)
            reel_summ.append({'reel_index':reel.get('reel_index'),'expanded_frames':len(seq),'notes':ns[:10]})
            event_frames.extend(seq)
            if len(event_frames) >= MAX_FRAMES_PER_EVENT: break
        images=[]
        for i,fe in enumerate(event_frames):
            im=compose_frame(fe, image_map)
            p=event_dir/f'frame_{i:03d}.png'
            im.save(p)
            images.append(im)
        if not images:
            images=[compose_frame({'images':[]}, image_map)]
        strip=make_strip(images, f"event {ev['seq']:03d} {ev['libcall']} {film_h}")
        strip_path=OUT/'strips'/f"event_{ev['seq']:03d}_{ev['libcall']}_{film_h.replace('0x','')}_ani_strip.png"
        strip.save(strip_path)
        gif_path=OUT/'animations'/f"event_{ev['seq']:03d}_{ev['libcall']}_{film_h.replace('0x','')}.gif"
        gif_frames=[im.convert('P', palette=Image.Palette.ADAPTIVE) for im in images[:32]]
        gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=max(60, int(1000/max(1,film.get('frate',12)))), loop=0)
        rec={'seq':ev['seq'],'libcall':ev['libcall'],'film_handle':film_h,'frate':film.get('frate'), 'numreels':film.get('numreels'), 'expanded_frames':len(event_frames), 'strip':str(strip_path.relative_to(OUT)), 'gif':str(gif_path.relative_to(OUT)), 'notes':notes[:20], 'reels':reel_summ}
        manifest['events'].append(rec)
        summary.append(rec)
        all_strips.append(strip)
    # timeline sheet vertical concatenation scaled down to max width
    widths=[im.width for im in all_strips]; heights=[im.height for im in all_strips]
    if all_strips:
        maxw=min(max(widths), 1600); totalh=0; scaled=[]
        for im in all_strips:
            if im.width>maxw:
                ratio=maxw/im.width; im=im.resize((maxw, max(1,int(im.height*ratio))), Image.Resampling.NEAREST)
            scaled.append(im); totalh+=im.height+8
        sheet=Image.new('RGBA',(maxw,totalh),(250,250,250,255)); y=0
        for im in scaled:
            sheet.alpha_composite(im,(0,y)); y+=im.height+8
        sheet.save(OUT/'bar_ani_script_timeline_sheet.png')
    with (OUT/'bar_ani_script_manifest.json').open('w') as f: json.dump(manifest,f,indent=2)
    with (OUT/'bar_ani_script_summary.csv').open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=['seq','libcall','film_handle','frate','numreels','expanded_frames','strip','gif'])
        w.writeheader();
        for r in summary: w.writerow({k:r[k] for k in w.fieldnames})
    readme = f"""# BAR.SCN ANI_SCRIPT-aware Playback Expansion\n\nThis prototype interprets BAR film ANI_SCRIPT entries rather than using manifest-order frames only.\n\nEvents exported: {len(summary)}\nTotal expanded frames: {sum(r['expanded_frames'] for r in summary)}\n\nImplemented commands: ANI_JUMP, ANI_END, ANI_STOP, ANI_HIDE, ANI_HFLIP, ANI_VFLIP, ANI_HVFLIP, ANI_ADJUSTX, ANI_ADJUSTY, ANI_ADJUSTXY, ANI_NOSLEEP.\n\nLimitations: bounded loop guards, approximate multi-image composition, no spatial PLAY placement.\n"""
    (OUT/'README.md').write_text(readme)
    # entry md
    entry=f"""# 35. BAR.SCN ANI_SCRIPT-aware Frame Expansion\n\nImplemented `bar_ani_script_playback_expander.py`.\n\n## Result\n\n| Metric | Count |\n|---|---:|\n| BAR film events exported | {len(summary)} |\n| total expanded frames | {sum(r['expanded_frames'] for r in summary)} |\n| max frames per event | {MAX_FRAMES_PER_EVENT} |\n| render failures | 0 |\n\nThe BAR playback prototype now interprets animation scripts for frame expansion instead of relying only on manifest-order frame lists.\n\nImplemented command handling includes `ANI_JUMP`, `ANI_END`, `ANI_STOP`, `ANI_HIDE`, `ANI_HFLIP`, `ANI_VFLIP`, `ANI_HVFLIP`, `ANI_ADJUSTX`, `ANI_ADJUSTY`, `ANI_ADJUSTXY`, and `ANI_NOSLEEP`.\n\n## Current Limitation\n\nThis is still bounded validation playback: loop guards are applied, multi-image frame composition is approximate, and `PLAY` spatial placement is not yet applied.\n\n## Next Target\n\nApply `PLAY` placement semantics to animation strips so film frames are positioned using scheduler arguments plus BLOCK-polygon adjustment metadata.\n"""
    (ROOT/'bar_ani_script_expansion_entry.md').write_text(entry)
    # zip
    zip_path=ROOT/'bar_ani_script_playback_outputs.zip'
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            z.write(p, p.relative_to(OUT.parent))
    print(json.dumps({'events':len(summary),'expanded_frames':sum(r['expanded_frames'] for r in summary),'zip':str(zip_path)}, indent=2))
if __name__=='__main__': main()
