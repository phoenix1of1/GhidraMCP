#!/usr/bin/env python3
"""
discworld-extract: unified GPL-compatible CLI for Discworld PC / Tinsel 1 resources.

This CLI consolidates the validated standalone probes/exporters produced during
reverse engineering. It is intentionally extractor-oriented: modes generate raw
chunk maps, rendered image previews, PCODE scans, film manifests, VM-lite traces,
scheduler annotations, timelines, and bounded visual exports.

This script expects the helper modules produced alongside it:
  tinsel1_renderer.py
  tinsel1_pcode_scanner.py
  tinsel1_film_manifest_exporter.py
  tinsel1_vm_lite.py
  tinsel1_scheduler_trace_annotator.py
  tinsel1_scene_timeline_builder.py
  tinsel1_scenegraph_probe.py
"""
from __future__ import annotations
import argparse, csv, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent
HELPERS = {
    'renderer': ROOT / 'tinsel1_renderer.py',
    'pcode': ROOT / 'tinsel1_pcode_scanner.py',
    'films': ROOT / 'tinsel1_film_manifest_exporter.py',
    'vm': ROOT / 'tinsel1_vm_lite.py',
    'scheduler': ROOT / 'tinsel1_scheduler_trace_annotator.py',
    'timelines': ROOT / 'tinsel1_scene_timeline_builder.py',
    'scenegraph': ROOT / 'tinsel1_scenegraph_probe.py',
}

CHUNK_NAMES_V1 = {
    0x33340002: 'FIRST/UNKNOWN_ZERO',
    0x33340003: 'BITMAP_ARENA',
    0x33340004: 'TERMINATOR',
    0x33340005: 'PALETTE',
    0x33340006: 'IMAGE',
    0x33340007: 'UNKNOWN_07',
    0x33340008: 'FILM',
    0x3334000A: 'PCODE',
    0x3334000B: 'ENTRANCE',
    0x3334000C: 'POLYGONS',
    0x3334000D: 'ACTORS',
    0x3334000E: 'SCENE',
    0x3334000F: 'TOTAL_ACTORS',
    0x33340010: 'TOTAL_GLOBALS',
    0x33340011: 'TOTAL_OBJECTS',
    0x33340012: 'OBJECTS',
    0x33340015: 'TOTAL_POLY',
}


def u32le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+4], 'little', signed=False)


def decode_scnhandle(handle: int) -> Dict[str, int]:
    return {
        'file_index': (handle >> 23) & 0x1FF,
        'local_offset': handle & 0x007FFFFF,
    }


def encode_scnhandle(file_index: int, local_offset: int) -> int:
    if file_index < 0 or file_index > 0x1FF:
        raise ValueError('file_index must fit in 9 bits')
    if local_offset < 0 or local_offset > 0x007FFFFF:
        raise ValueError('local_offset must fit in 23 bits')
    return (file_index << 23) | local_offset


def walk_chunks(data: bytes) -> Iterable[Dict[str, Any]]:
    off = 0
    seen = set()
    while 0 <= off < len(data) and off not in seen and off + 8 <= len(data):
        seen.add(off)
        cid = u32le(data, off)
        nxt = u32le(data, off + 4)
        payload_end = nxt if nxt else len(data)
        yield {
            'offset': off,
            'chunk_id': f'0x{cid:08X}',
            'chunk_name': CHUNK_NAMES_V1.get(cid, 'UNKNOWN'),
            'next_offset': nxt,
            'payload_offset': off + 8,
            'payload_size': max(0, payload_end - (off + 8)),
        }
        if nxt == 0:
            break
        off = nxt


def read_index(index_path: Path) -> List[Dict[str, Any]]:
    if not index_path.exists():
        return []
    data = index_path.read_bytes()
    rows = []
    rec_size = 20 if len(data) % 20 == 0 else 24
    for i in range(0, len(data) - rec_size + 1, rec_size):
        raw = data[i:i+12]
        name = raw.split(b'\0', 1)[0].decode('ascii', errors='replace')
        if not name:
            continue
        size_flags = u32le(data, i+12)
        rows.append({'index': i // rec_size, 'filename': name, 'size_flags': f'0x{size_flags:08X}', 'record_offset': i})
    return rows


def ensure_out(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    return out


def run(cmd: List[str], cwd: Optional[Path]=None) -> None:
    print('+', ' '.join(map(str, cmd)))
    res = subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # Keep helper verbosity out of the chat/terminal; write last output to a side log when available.
    log = ROOT / 'discworld_extract_last_helper.log'
    try:
        log.write_text(res.stdout or '')
    except Exception:
        pass


def mode_chunks(input_dir: Path, out: Path, scenes: Optional[List[str]]=None) -> Path:
    ensure_out(out / 'chunks')
    files = sorted(input_dir.glob('*.SCN'))
    if scenes:
        wanted = {s.upper() if s.upper().endswith('.SCN') else s.upper()+'.SCN' for s in scenes}
        files = [p for p in files if p.name.upper() in wanted]
    index = read_index(input_dir / 'INDEX')
    summary = {'input': str(input_dir), 'index_records': index, 'files': []}
    rows = []
    for p in files:
        chunks = list(walk_chunks(p.read_bytes()))
        summary['files'].append({'file': p.name, 'size': p.stat().st_size, 'chunks': chunks})
        for c in chunks:
            rows.append({'file': p.name, **c})
    (out / 'chunks' / 'chunk_manifest.json').write_text(json.dumps(summary, indent=2))
    with (out / 'chunks' / 'chunk_summary.csv').open('w', newline='') as f:
        fieldnames = ['file','offset','chunk_id','chunk_name','next_offset','payload_offset','payload_size']
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(rows)
    return out / 'chunks' / 'chunk_manifest.json'


def mode_images(input_dir: Path, out: Path, scenes: List[str], limit: int) -> List[Path]:
    ensure_out(out / 'images')
    generated=[]
    for scene in scenes:
        name = scene.upper() if scene.upper().endswith('.SCN') else scene.upper()+'.SCN'
        scn = input_dir / name
        if not scn.exists():
            print(f'warning: missing scene {name}', file=sys.stderr)
            continue
        scene_out = out / 'images' / name.lower().replace('.scn','')
        scene_out.mkdir(parents=True, exist_ok=True)
        run([sys.executable, str(HELPERS['renderer']), str(scn), '--out', str(scene_out), '--limit', str(limit), '--manifest', str(scene_out/'manifest.json')])
        generated.append(scene_out/'manifest.json')
    return generated


def mode_scenegraph(input_dir: Path, out: Path) -> Path:
    ensure_out(out)
    target = out / 'tinsel1_scenegraph_report.json'
    run([sys.executable, str(HELPERS['scenegraph']), '--root', str(input_dir), '--out', str(target)])
    return target


def mode_pcode(input_dir: Path, out: Path) -> Path:
    ensure_out(out / 'pcode')
    run([sys.executable, str(HELPERS['pcode']), str(input_dir), '--outdir', str(out / 'pcode')])
    return out / 'pcode' / 'tinsel1_pcode_report.json'


def mode_films(input_dir: Path, out: Path) -> Path:
    ensure_out(out / 'film_manifest')
    refs = out / 'pcode' / 'tinsel1_pcode_film_refs.csv'
    if not refs.exists():
        mode_pcode(input_dir, out)
    run([sys.executable, str(HELPERS['films']), '--root', str(input_dir), '--film-refs', str(refs), '--outdir', str(out / 'film_manifest')])
    return out / 'film_manifest' / 'tinsel1_film_manifest_report.json'


def mode_visual(input_dir: Path, out: Path, scenes: List[str], max_images: int) -> Path:
    """Render PNGs from film manifests, using the validated visual exporter logic with explicit manifest dir."""
    sys.path.insert(0, str(ROOT))
    from tinsel1_visual_asset_exporter import collect_images_from_manifest, make_contact_sheet, safe_name
    from tinsel1_renderer import Tinsel1Scene
    manifest_dir = out / 'film_manifest'
    if not manifest_dir.exists():
        mode_films(input_dir, out)
    out_root = out / 'visual_asset_export'
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    results=[]
    for scene in scenes:
        scene = scene.upper() if scene.upper().endswith('.SCN') else scene.upper()+'.SCN'
        manifest_path = manifest_dir / f'{safe_name(scene)}_film_manifest.json'
        if not manifest_path.exists():
            results.append({'scene': scene, 'error': 'missing film manifest'})
            continue
        manifest = json.loads(manifest_path.read_text())
        images, graph = collect_images_from_manifest(manifest)
        selected = images if max_images == 0 else images[:max_images]
        scene_dir = out_root / safe_name(scene); img_dir = scene_dir / 'images'
        img_dir.mkdir(parents=True, exist_ok=True)
        renderers={}; exported=[]; errors=[]
        for item in selected:
            try:
                source = item['source_file']
                if source not in renderers:
                    renderers[source] = Tinsel1Scene(input_dir / source)
                rec = renderers[source].image_records()[item['image_index']]
                filename = f"{item['image_handle'].replace('0x','')}_img{item['image_index']:04d}_{item['width']}x{item['height']}.png"
                rel = f'images/{filename}'
                stats = renderers[source].save_png(rec, scene_dir / rel)
                copied = dict(item); copied['png'] = rel; copied['render_stats'] = stats.__dict__
                exported.append(copied)
            except Exception as e:
                err = dict(item); err['error']=str(e); errors.append(err)
        by_handle = {x['image_handle']: x for x in exported}
        for film in graph:
            for reel in film['reels']:
                for frame in reel['frames']:
                    for img_ref in frame['images']:
                        meta = by_handle.get(img_ref['image_handle'])
                        if meta:
                            img_ref.update({'png': meta['png'], 'image_index': meta['image_index'], 'size': [meta['width'], meta['height']]})
        contact = make_contact_sheet(scene_dir, scene, exported)
        sm = {'scene':scene,'source_manifest':str(manifest_path),'film_ref_count':manifest.get('film_ref_count'),
              'unique_film_count':manifest.get('unique_film_count'),'unique_images_available':len(images),
              'unique_images_exported':len(exported),'render_errors':errors,'contact_sheet':contact,'images':exported,'film_graph':graph}
        (scene_dir/'manifest.json').write_text(json.dumps(sm, indent=2))
        results.append({'scene':scene,'unique_images_available':len(images),'unique_images_exported':len(exported),'render_errors':len(errors),'manifest':str(scene_dir/'manifest.json'),'contact_sheet':str(scene_dir/contact) if contact else None})
    report={'mode':'visual','scenes':results,'total_pngs_exported':sum(r.get('unique_images_exported',0) for r in results),'total_render_errors':sum(r.get('render_errors',0) for r in results)}
    (out_root/'visual_asset_export_report.json').write_text(json.dumps(report, indent=2))
    with (out_root/'visual_asset_export_summary.csv').open('w', newline='') as f:
        fieldnames=['scene','unique_images_available','unique_images_exported','render_errors','manifest','contact_sheet','error']
        w=csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(results)
    return out_root/'visual_asset_export_report.json'


def mode_vm(input_dir: Path, out: Path, max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    ensure_out(out / 'vm_lite_trace')
    run([sys.executable, str(HELPERS['vm']), str(input_dir), '--outdir', str(out / 'vm_lite_trace'), '--max-scripts-per-file', str(max_scripts_per_file), '--max-steps', str(max_steps), '--max-paths', str(max_paths)])
    return out / 'vm_lite_trace' / 'vm_lite_report.json'


def annotate_scheduler(input_csv: Path, out: Path) -> Path:
    """Standalone copy of scheduler annotation with paths controlled by the CLI."""
    sys.path.insert(0, str(ROOT))
    # Import constants/helpers without executing hardcoded script top-level by reading its ARITY manually is awkward;
    # duplicate the stable trace-oriented table here.
    import re, collections
    ARITY = {
        'BACKGROUND': {'arity': 1, 'kind': 'film_scheduler', 'confidence': 'confirmed', 'args': ['film']},
        'PLAY': {'arity': 6, 'kind': 'film_scheduler', 'confidence': 'strong', 'args': ['film','x','y','z_or_layer','flags_or_hold','esc']},
        'TOPPLAY': {'arity': 6, 'kind': 'film_scheduler', 'confidence': 'working', 'args': ['film','x','y','z_or_layer','flags_or_hold','esc']},
        'SPLAY': {'arity': 6, 'kind': 'film_scheduler', 'confidence': 'working', 'args': ['film','x','y','z_or_layer','flags_or_hold','esc']},
        'STAND': {'arity': 5, 'kind': 'actor_pose', 'confidence': 'strong', 'args': ['actor','x','y','direction','flags']},
        'SWALK': {'arity': 6, 'kind': 'actor_walk', 'confidence': 'strong', 'args': ['actor','x','y','direction_or_x2','y2','flags']},
        'WALK': {'arity': 6, 'kind': 'actor_walk', 'confidence': 'working', 'args': ['actor','x','y','film_or_direction','hold_or_flags','esc']},
        'WAITFRAME': {'arity': 2, 'kind': 'scheduler_wait', 'confidence': 'working', 'args': ['target','frame']},
        'WAITTIME': {'arity': 1, 'kind': 'scheduler_wait', 'confidence': 'strong', 'args': ['ticks']},
        'EVENT': {'arity': 0, 'kind': 'event_wait', 'confidence': 'confirmed', 'args': []},
        'CONTROL': {'arity': 1, 'kind': 'control', 'confidence': 'strong', 'args': ['on_off']},
        'OFFSET': {'arity': 3, 'kind': 'camera_scroll', 'confidence': 'working', 'args': ['mode','x','y']},
        'SCROLL': {'arity': 3, 'kind': 'camera_scroll', 'confidence': 'working', 'args': ['mode','x','y']},
        'PLAYSAMPLE': {'arity': 2, 'kind': 'sound', 'confidence': 'strong', 'args': ['sample','mode_or_channel']},
        'STOPSAMPLE': {'arity': 1, 'kind': 'sound', 'confidence': 'working', 'args': ['sample_or_all']},
        'SETTAG': {'arity': 1, 'kind': 'tag', 'confidence': 'strong', 'args': ['tag']},
        'KILLTAG': {'arity': 1, 'kind': 'tag', 'confidence': 'confirmed', 'args': ['tag']},
        'TAGACTOR': {'arity': 2, 'kind': 'tag', 'confidence': 'working', 'args': ['actor','tag']},
        'TALK': {'arity': 1, 'kind': 'dialogue', 'confidence': 'working', 'args': ['string_id']},
        'TALKAT': {'arity': 3, 'kind': 'dialogue', 'confidence': 'working', 'args': ['string_id','x','y']},
        'PRINTOBJ': {'arity': 1, 'kind': 'dialogue', 'confidence': 'working', 'args': ['object_or_string']},
        'PRINTTAG': {'arity': 1, 'kind': 'dialogue', 'confidence': 'working', 'args': ['tag']},
    }
    FILM_RE=re.compile(r'film:(0x[0-9A-Fa-f]+)')
    def parse_stack(s):
        return [p.strip() for p in str(s or '').split('|') if p.strip() and p.strip()!='nan']
    def val(tok):
        tok=tok.strip(); m=FILM_RE.fullmatch(tok)
        if m: return {'type':'film','value':m.group(1).upper().replace('X','x')}
        if tok.startswith('imm:'):
            v=tok[4:]
            try: return {'type':'imm','value':int(v,0)}
            except Exception: return {'type':'imm','value':v}
        if tok.startswith('global:'): return {'type':'global','value':tok.split(':',1)[1]}
        if tok.startswith('local:'): return {'type':'local','value':tok.split(':',1)[1]}
        return {'type':'expr','value':tok}
    def fmt(v):
        if v['type']=='film': return v['value']
        return f"{v['type']}:{v['value']}"
    rows=[]
    with input_csv.open(newline='') as f:
        for r in csv.DictReader(f):
            name=r.get('libcall_name') or ''
            if name not in ARITY: continue
            spec=ARITY[name]; toks=parse_stack(r.get('stack_top','')); arity=spec['arity']
            vals=[val(t) for t in (toks[-arity:] if arity else [])]
            films=[v['value'] for v in vals if v.get('type')=='film']
            context=[m.group(1).upper().replace('X','x') for m in FILM_RE.finditer(str(r.get('stack_top','')))]
            rows.append({'file':r.get('file',''),'source':r.get('source',''),'script_handle':r.get('script_handle',''),
                         'ip':r.get('ip',''),'libcall':name,'kind':spec['kind'],'arity':arity,'confidence':spec['confidence'],
                         'arg_names':'|'.join(spec['args']),'args_display':' | '.join(f'{n}={fmt(v)}' for n,v in zip(spec['args'],vals)),
                         'film_args':' | '.join(films),'context_films':' | '.join(context),'stack_depth':r.get('stack_depth',''),
                         'visible_stack':r.get('stack_top',''),'args_json':json.dumps(vals,separators=(',',':'))})
    ensure_out(out / 'scheduler')
    csv_path = out / 'scheduler' / 'scheduler_trace_events.csv'
    with csv_path.open('w', newline='') as f:
        fields=['file','source','script_handle','ip','libcall','kind','arity','confidence','arg_names','args_display','film_args','context_films','stack_depth','visible_stack','args_json']
        w=csv.DictWriter(f, fields); w.writeheader(); w.writerows(rows)
    report={'annotated_events':len(rows),'scheduler_relevant_events':sum(1 for r in rows if r['kind'] in {'film_scheduler','actor_pose','actor_walk','scheduler_wait','camera_scroll','control'}),'film_scheduler_events':sum(1 for r in rows if r['kind']=='film_scheduler'),'counts_by_libcall':dict(collections.Counter(r['libcall'] for r in rows).most_common()),'arity_table':ARITY}
    (out/'scheduler'/'scheduler_arity_report.json').write_text(json.dumps(report, indent=2))
    return csv_path


def mode_scheduler(input_dir: Path, out: Path, max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    libcalls = out / 'vm_lite_trace' / 'vm_lite_libcalls.csv'
    if not libcalls.exists():
        mode_vm(input_dir, out, max_scripts_per_file, max_steps, max_paths)
    return annotate_scheduler(libcalls, out)


def mode_timelines(input_dir: Path, out: Path, max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    sched_csv = out / 'scheduler' / 'scheduler_trace_events.csv'
    if not sched_csv.exists():
        sched_csv = mode_scheduler(input_dir, out, max_scripts_per_file, max_steps, max_paths)
    ensure_out(out / 'scene_timeline')
    run([sys.executable, str(HELPERS['timelines']), str(sched_csv), '--out', str(out / 'scene_timeline')])
    return out / 'scene_timeline' / 'scene_timeline_summary.csv'


def zip_outputs(out: Path, zip_path: Optional[Path]=None) -> Path:
    if zip_path is None:
        zip_path = out.parent / f'{out.name}.zip'
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(Path(__file__), arcname='discworld_extract.py')
        for key,p in HELPERS.items():
            if p.exists(): z.write(p, arcname=f'helpers/{p.name}')
        for p in out.rglob('*'):
            if p.is_file(): z.write(p, arcname=str(p.relative_to(out)))
    return zip_path


def main():
    ap = argparse.ArgumentParser(description='Unified Discworld PC / Tinsel 1 resource extractor CLI')
    ap.add_argument('--input','-i', default='/mnt/data', help='Game/resource directory containing INDEX and .SCN files')
    ap.add_argument('--output','-o', default='/mnt/data/discworld_extract_out', help='Output directory')
    ap.add_argument('--mode','-m', choices=['chunks','images','scenegraph','pcode','films','visual','vm','scheduler','timelines','all'], default='all')
    ap.add_argument('--scenes', nargs='*', default=['BAR.SCN','CLIMAX.SCN','FINALE.SCN'], help='Scene names for image/visual modes')
    ap.add_argument('--image-limit', type=int, default=20)
    ap.add_argument('--max-images-per-scene', type=int, default=50, help='Visual mode limit; 0 = unbounded')
    ap.add_argument('--max-scripts-per-file', type=int, default=60)
    ap.add_argument('--max-steps', type=int, default=1200)
    ap.add_argument('--max-paths', type=int, default=32)
    ap.add_argument('--zip', action='store_true', help='Zip output directory after running')
    args = ap.parse_args()

    input_dir = Path(args.input).resolve(); out = ensure_out(Path(args.output).resolve())
    completed=[]
    if args.mode in ('chunks','all'):
        completed.append(('chunks', str(mode_chunks(input_dir, out))))
    if args.mode in ('images','all'):
        completed.append(('images', [str(p) for p in mode_images(input_dir, out, args.scenes, args.image_limit)]))
    if args.mode in ('scenegraph','all'):
        completed.append(('scenegraph', str(mode_scenegraph(input_dir, out))))
    if args.mode in ('pcode','all'):
        completed.append(('pcode', str(mode_pcode(input_dir, out))))
    if args.mode in ('films','all'):
        completed.append(('films', str(mode_films(input_dir, out))))
    if args.mode in ('visual','all'):
        completed.append(('visual', str(mode_visual(input_dir, out, args.scenes, args.max_images_per_scene))))
    if args.mode in ('vm','all'):
        completed.append(('vm', str(mode_vm(input_dir, out, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    if args.mode in ('scheduler','all'):
        completed.append(('scheduler', str(mode_scheduler(input_dir, out, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    if args.mode in ('timelines','all'):
        completed.append(('timelines', str(mode_timelines(input_dir, out, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    report={'input':str(input_dir),'output':str(out),'mode':args.mode,'completed':completed}
    (out/'discworld_extract_run_report.json').write_text(json.dumps(report, indent=2))
    if args.zip:
        zp=zip_outputs(out)
        report['zip']=str(zp)
        (out/'discworld_extract_run_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
