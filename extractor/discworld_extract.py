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
import argparse, csv, importlib.util, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = ROOT.parent / 'runtime'
HELPERS = {
    'renderer': ROOT / 'tinsel1_renderer.py',
    'pcode': RUNTIME_ROOT / 'tinsel1_pcode_scanner.py',
    'films': ROOT / 'tinsel1_film_manifest_exporter.py',
    'vm': RUNTIME_ROOT / 'tinsel1_vm_lite.py',
    'scheduler': ROOT / 'tinsel1_scheduler_trace_annotator.py',
    'timelines': RUNTIME_ROOT / 'tinsel1_scene_timeline_builder.py',
    'scenegraph': RUNTIME_ROOT / 'tinsel1_scenegraph_probe.py',
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
    merged_refs = out / 'film_manifest' / 'merged_film_refs.csv'
    rows = []
    seen = set()
    with refs.open(newline='') as f:
        for row in csv.DictReader(f):
            row = dict(row)
            key = (row.get('file'), row.get('script_handle'), row.get('source'), row.get('script_ip'), row.get('film_handle_hex'))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    vm_film_events = out / 'vm_lite_trace' / 'vm_lite_film_events.csv'
    if vm_film_events.exists():
        with vm_film_events.open(newline='') as f:
            for row in csv.DictReader(f):
                if row.get('event') != 'film_push':
                    continue
                film_hex = (row.get('film_handle') or '').strip()
                if not film_hex:
                    continue
                try:
                    film_int = int(film_hex, 16)
                except ValueError:
                    continue
                merged = {
                    'file': row.get('file', ''),
                    'script_handle': row.get('script_handle', ''),
                    'source': row.get('source', ''),
                    'script_ip': row.get('ip', ''),
                    'op': row.get('opcode', 'FILM') or 'FILM',
                    'film_handle': str(film_int),
                    'file_index': row.get('file_index', ''),
                    'offset': row.get('offset', ''),
                    'film_handle_hex': film_hex,
                }
                key = (merged.get('file'), merged.get('script_handle'), merged.get('source'), merged.get('script_ip'), merged.get('film_handle_hex'))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(merged)

    fieldnames = ['file', 'script_handle', 'source', 'script_ip', 'op', 'film_handle', 'file_index', 'offset', 'film_handle_hex']
    with merged_refs.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})

    run([sys.executable, str(HELPERS['films']), '--root', str(input_dir), '--film-refs', str(merged_refs), '--outdir', str(out / 'film_manifest')])
    return out / 'film_manifest' / 'tinsel1_film_manifest_report.json'


def mode_visual(input_dir: Path, out: Path, scenes: List[str], max_images: int) -> Path:
    """Render PNGs from film manifests, using the validated visual exporter logic with explicit manifest dir."""
    sys.path.insert(0, str(ROOT))
    from tinsel1_visual_asset_exporter import collect_images_from_manifest, make_contact_sheet, safe_name
    from tinsel1_renderer import Tinsel1Scene
    mode_films(input_dir, out)
    manifest_dir = out / 'film_manifest'
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


def mode_backgrounds(input_dir: Path, out: Path, scenes: List[str], max_images: int,
                     max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    sys.path.insert(0, str(ROOT))
    from tinsel1_visual_asset_exporter import safe_name

    def size_class(width, height):
        try:
            width = int(width)
            height = int(height)
        except Exception:
            return ''
        return f'{width}x{height}'

    def layout_class(width, height):
        try:
            width = int(width)
            height = int(height)
        except Exception:
            return ''
        if width <= 320 and height <= 200:
            return 'standard'
        if width > 320 and height <= 200:
            return 'panoramic'
        if width <= 320 and height > 200:
            return 'tall'
        return 'panoramic_tall'

    timeline_dir = out / 'scene_timeline'
    if not timeline_dir.exists():
        mode_timelines(input_dir, out, max_scripts_per_file, max_steps, max_paths)

    visual_dir = out / 'visual_asset_export'
    if not visual_dir.exists():
        mode_visual(input_dir, out, scenes, max_images)

    out_root = out / 'background_export'
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for scene in scenes:
        scene = scene.upper() if scene.upper().endswith('.SCN') else scene.upper() + '.SCN'
        stem = safe_name(scene)
        timeline_path = timeline_dir / f'{stem}.json'
        visual_manifest_path = visual_dir / stem / 'manifest.json'

        row = {'scene': scene, 'scene_kind': 'scene', 'timeline': str(timeline_path), 'visual_manifest': str(visual_manifest_path)}
        if not timeline_path.exists():
            row['error'] = 'missing scene timeline'
            results.append(row)
            continue

        timeline = json.loads(timeline_path.read_text(encoding='utf-8'))
        events = timeline.get('events', [])
        bg_event = next((event for event in events if event.get('libcall') == 'BACKGROUND'), None)
        if bg_event is None:
            if scene == 'OBJECTS.SCN' or any(str(event.get('source', '')).startswith('inventory.') for event in events):
                row['scene_kind'] = 'container'
                row['note'] = 'no BACKGROUND event; inventory/object resource container'
            else:
                row['error'] = 'missing BACKGROUND event'
            results.append(row)
            continue

        if not visual_manifest_path.exists():
            row['error'] = 'missing visual manifest'
            results.append(row)
            continue

        bg_film = bg_event.get('film_args') or ''
        if not bg_film and bg_event.get('args'):
            first = bg_event['args'][0]
            if first.get('type') == 'film':
                bg_film = first.get('value', '')
        row['background_film'] = bg_film

        visual = json.loads(visual_manifest_path.read_text(encoding='utf-8'))
        image_by_handle = {
            image.get('image_handle'): image
            for image in visual.get('images', [])
            if image.get('image_handle')
        }
        resolved = None
        for film in visual.get('film_graph', []):
            if film.get('film_handle') != bg_film:
                continue
            for reel in film.get('reels', []):
                for frame in reel.get('frames', []):
                    for image in frame.get('images', []):
                        png = image.get('png')
                        if not png:
                            continue
                        candidate = visual_manifest_path.parent / png
                        if candidate.exists():
                            resolved = {
                                'film_handle': bg_film,
                                'image_handle': image.get('image_handle'),
                                'png': png,
                                'source_path': str(candidate)
                            }
                            break
                    if resolved:
                        break
                if resolved:
                    break
            if resolved:
                break

        if resolved is None:
            for image in visual.get('images', []):
                try:
                    width = int(image.get('width', 0))
                    height = int(image.get('height', 0))
                except Exception:
                    continue
                png = image.get('png')
                if width < 600 or height < 180 or not png:
                    continue
                candidate = visual_manifest_path.parent / png
                if candidate.exists():
                    resolved = {
                        'film_handle': bg_film,
                        'image_handle': image.get('image_handle'),
                        'png': png,
                        'source_path': str(candidate),
                        'fallback': 'largest-scene-like-image'
                    }
                    break

        if resolved is None:
            row['error'] = 'unable to resolve background png'
            results.append(row)
            continue

        scene_dir = out_root / stem
        scene_dir.mkdir(parents=True, exist_ok=True)
        src = Path(resolved['source_path'])
        dst = scene_dir / src.name
        shutil.copy2(src, dst)
        image_meta = image_by_handle.get(resolved.get('image_handle'), {})
        row.update({
            'image_handle': resolved.get('image_handle'),
            'source_file': image_meta.get('source_file', ''),
            'width': image_meta.get('width', ''),
            'height': image_meta.get('height', ''),
            'anim_offset_x': image_meta.get('anim_offset_x', ''),
            'anim_offset_y': image_meta.get('anim_offset_y', ''),
            'bitmap_handle': image_meta.get('bitmap_handle', ''),
            'palette_handle': image_meta.get('palette_handle', ''),
            'relative_png': resolved.get('png'),
            'copied_png': str(dst),
            'fallback': resolved.get('fallback', '')
        })
        row['scene_size_class'] = size_class(row.get('width'), row.get('height'))
        row['scene_layout_class'] = layout_class(row.get('width'), row.get('height'))
        results.append(row)

    import collections
    index = {row['scene']: dict(row) for row in results}
    film_index = collections.OrderedDict()
    for row in results:
        film_handle = row.get('background_film')
        if not film_handle:
            continue
        film_index.setdefault(film_handle, []).append(row['scene'])
    size_histogram = dict(collections.Counter(
        row.get('scene_size_class') for row in results
        if row.get('scene_kind') == 'scene' and row.get('scene_size_class')
    ))
    layout_histogram = dict(collections.Counter(
        row.get('scene_layout_class') for row in results
        if row.get('scene_kind') == 'scene' and row.get('scene_layout_class')
    ))
    report = {
        'mode': 'backgrounds',
        'scenes': results,
        'resolved_count': sum(1 for row in results if row.get('copied_png')),
        'scene_count': sum(1 for row in results if row.get('scene_kind') == 'scene'),
        'container_count': sum(1 for row in results if row.get('scene_kind') == 'container'),
        'resolved_scene_count': sum(1 for row in results if row.get('scene_kind') == 'scene' and row.get('copied_png')),
        'unresolved_scene_count': sum(1 for row in results if row.get('scene_kind') == 'scene' and row.get('error')),
        'error_count': sum(1 for row in results if row.get('scene_kind') != 'container' and row.get('error')),
        'scene_size_class_histogram': size_histogram,
        'scene_layout_class_histogram': layout_histogram,
        'background_film_count': len(film_index)
    }
    (out_root / 'background_export_report.json').write_text(json.dumps(report, indent=2))
    (out_root / 'background_export_index.json').write_text(json.dumps(index, indent=2))
    (out_root / 'background_export_film_index.json').write_text(json.dumps(film_index, indent=2))
    with (out_root / 'background_export_summary.csv').open('w', newline='') as f:
        fieldnames = ['scene', 'scene_kind', 'scene_size_class', 'scene_layout_class', 'background_film', 'image_handle', 'source_file', 'width', 'height', 'anim_offset_x', 'anim_offset_y', 'bitmap_handle', 'palette_handle', 'relative_png', 'copied_png', 'timeline', 'visual_manifest', 'fallback', 'note', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    return out_root / 'background_export_report.json'


def mode_playfirst(input_dir: Path, out: Path, scenes: List[str], max_images: int,
                   max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    sys.path.insert(0, str(ROOT))
    from tinsel1_visual_asset_exporter import safe_name

    timeline_dir = out / 'scene_timeline'
    if not timeline_dir.exists():
        mode_timelines(input_dir, out, max_scripts_per_file, max_steps, max_paths)

    mode_visual(input_dir, out, scenes, 0)
    visual_dir = out / 'visual_asset_export'

    out_root = out / 'play_first_export'
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    import collections

    def extract_film(event: dict) -> str:
        for arg in event.get('args', []) or []:
            if arg.get('type') == 'film':
                return arg.get('value', '')
        return event.get('film_args') or ''

    def extract_int_arg(event: dict, name: str):
        for arg_name, value in zip(['film', 'x', 'y', 'z_or_layer', 'flags_or_hold', 'esc'], event.get('args', []) or []):
            if arg_name != name:
                continue
            if value.get('type') == 'imm':
                return value.get('value')
            return None
        return None

    def is_hidden_stub_film(film_detail: dict) -> bool:
        reels = film_detail.get('reels', []) or []
        if not reels:
            return False
        saw_hide = False
        for reel in reels:
            multi_init = reel.get('multi_init') or {}
            if multi_init.get('hMulFrame') not in {'0x00000000', '', None}:
                return False
            ani_entries = (reel.get('ani_script') or {}).get('entries', []) or []
            ops = {entry.get('op') for entry in ani_entries if entry.get('op')}
            if not ops or not ops.issubset({'ANI_HIDE', 'ANI_END'}):
                return False
            if 'ANI_HIDE' in ops:
                saw_hide = True
            frames = reel.get('frames', []) or []
            if any((frame.get('handle') or '') not in {'', '0x00000000'} for frame in frames):
                return False
        return saw_hide

    results = []
    all_event_rows = []
    for scene in scenes:
        scene = scene.upper() if scene.upper().endswith('.SCN') else scene.upper() + '.SCN'
        stem = safe_name(scene)
        timeline_path = timeline_dir / f'{stem}.json'
        visual_manifest_path = visual_dir / stem / 'manifest.json'
        scene_dir = out_root / stem
        scene_dir.mkdir(parents=True, exist_ok=True)

        row = {'scene': scene, 'timeline': str(timeline_path), 'visual_manifest': str(visual_manifest_path)}
        if not timeline_path.exists():
            row['error'] = 'missing scene timeline'
            results.append(row)
            continue
        if not visual_manifest_path.exists():
            row['error'] = 'missing visual manifest'
            results.append(row)
            continue

        timeline = json.loads(timeline_path.read_text(encoding='utf-8'))
        visual = json.loads(visual_manifest_path.read_text(encoding='utf-8'))
        source_film_detail = {}
        source_manifest_path = visual.get('source_manifest')
        if source_manifest_path and Path(source_manifest_path).exists():
            source_manifest = json.loads(Path(source_manifest_path).read_text(encoding='utf-8'))
            for film_ref in source_manifest.get('film_refs', []) or []:
                film_handle = film_ref.get('film_handle')
                film_detail = film_ref.get('film')
                if film_handle and film_detail:
                    source_film_detail.setdefault(film_handle, film_detail)

        film_to_first = {}
        image_by_handle = {
            image.get('image_handle'): image
            for image in visual.get('images', [])
            if image.get('image_handle')
        }
        film_handles_in_graph = set()
        film_to_count = {}
        for film in visual.get('film_graph', []):
            film_handle = film.get('film_handle')
            frame_count = 0
            images = []
            for reel in film.get('reels', []):
                for frame in reel.get('frames', []):
                    frame_count += 1
                    for image in frame.get('images', []):
                        if image.get('png'):
                            images.append(image)
            if film_handle:
                film_handles_in_graph.add(film_handle)
                film_to_count[film_handle] = {'frames': frame_count, 'images': len(images)}
                if images:
                    film_to_first[film_handle] = images[0]

        event_rows = []
        for event in timeline.get('events', []):
            libcall = event.get('libcall')
            if libcall != 'PLAY':
                continue
            film_handle = extract_film(event)
            if not film_handle:
                continue
            event_row = {
                'scene': scene,
                'seq': event.get('seq'),
                'libcall': libcall,
                'category': event.get('category'),
                'source': event.get('source'),
                'script_handle': event.get('script_handle'),
                'ip': event.get('ip'),
                'film_handle': film_handle,
                'x': extract_int_arg(event, 'x'),
                'y': extract_int_arg(event, 'y'),
                'film_frame_count': film_to_count.get(film_handle, {}).get('frames', ''),
                'film_image_count': film_to_count.get(film_handle, {}).get('images', ''),
                'args_display': event.get('args_display', ''),
            }
            first_image = film_to_first.get(film_handle)
            if first_image:
                src = visual_manifest_path.parent / first_image['png']
                if src.exists():
                    filename = f"event_{int(event.get('seq') or 0):03d}_{film_handle.replace('0x', '').upper()}_{Path(first_image['png']).name}"
                    dst = scene_dir / filename
                    shutil.copy2(src, dst)
                    image_meta = image_by_handle.get(first_image.get('image_handle'), {})
                    event_row.update({
                        'preview_png': str(dst),
                        'relative_preview_png': str(Path(stem) / filename),
                        'image_handle': first_image.get('image_handle', ''),
                        'width': image_meta.get('width', ''),
                        'height': image_meta.get('height', ''),
                        'anim_offset_x': image_meta.get('anim_offset_x', ''),
                        'anim_offset_y': image_meta.get('anim_offset_y', ''),
                        'bitmap_handle': image_meta.get('bitmap_handle', ''),
                        'palette_handle': image_meta.get('palette_handle', ''),
                    })
                else:
                    event_row['unresolved_reason'] = 'preview_png_missing_on_disk'
            elif film_handle not in film_handles_in_graph:
                event_row['unresolved_reason'] = 'film_missing_from_visual_graph'
            elif is_hidden_stub_film(source_film_detail.get(film_handle, {})):
                event_row['unresolved_reason'] = 'film_hidden_stub'
            else:
                event_row['unresolved_reason'] = 'film_has_no_png_backed_frames'
            event_rows.append(event_row)

        scene_manifest = {
            'scene': scene,
            'event_count': len(event_rows),
            'resolved_preview_count': sum(1 for event_row in event_rows if event_row.get('preview_png')),
            'unresolved_preview_count': sum(1 for event_row in event_rows if not event_row.get('preview_png')),
            'unresolved_reason_histogram': dict(collections.Counter(
                event_row.get('unresolved_reason') for event_row in event_rows if event_row.get('unresolved_reason')
            )),
            'events': event_rows,
        }
        (scene_dir / 'manifest.json').write_text(json.dumps(scene_manifest, indent=2))

        row.update({
            'play_event_count': len(event_rows),
            'resolved_preview_count': sum(1 for event_row in event_rows if event_row.get('preview_png')),
            'unresolved_preview_count': sum(1 for event_row in event_rows if not event_row.get('preview_png')),
            'manifest': str(scene_dir / 'manifest.json'),
        })
        if not event_rows:
            row['note'] = 'no PLAY events'
        results.append(row)
        all_event_rows.extend(event_rows)

    scene_index = collections.OrderedDict()
    for row in results:
        scene_index[row['scene']] = dict(row)

    film_index = collections.OrderedDict()
    for event_row in all_event_rows:
        film_handle = event_row.get('film_handle')
        if not film_handle:
            continue
        film_index.setdefault(film_handle, []).append({
            'scene': event_row['scene'],
            'seq': event_row.get('seq'),
            'ip': event_row.get('ip'),
            'preview_png': event_row.get('preview_png', ''),
        })

    report = {
        'mode': 'playfirst',
        'scenes': results,
        'scene_count': len(results),
        'play_event_count': len(all_event_rows),
        'resolved_preview_count': sum(1 for event_row in all_event_rows if event_row.get('preview_png')),
        'unresolved_preview_count': sum(1 for event_row in all_event_rows if not event_row.get('preview_png')),
        'unresolved_reason_histogram': dict(collections.Counter(
            event_row.get('unresolved_reason') for event_row in all_event_rows if event_row.get('unresolved_reason')
        )),
        'scene_with_play_count': sum(1 for row in results if row.get('play_event_count')),
        'film_handle_count': len(film_index),
    }
    (out_root / 'play_first_export_report.json').write_text(json.dumps(report, indent=2))
    (out_root / 'play_first_export_index.json').write_text(json.dumps(scene_index, indent=2))
    (out_root / 'play_first_film_index.json').write_text(json.dumps(film_index, indent=2))
    with (out_root / 'play_first_export_summary.csv').open('w', newline='') as f:
        fieldnames = ['scene', 'play_event_count', 'resolved_preview_count', 'unresolved_preview_count', 'timeline', 'visual_manifest', 'manifest', 'note', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    with (out_root / 'play_first_event_summary.csv').open('w', newline='') as f:
        fieldnames = ['scene', 'seq', 'libcall', 'category', 'source', 'script_handle', 'ip', 'film_handle', 'x', 'y', 'image_handle', 'width', 'height', 'anim_offset_x', 'anim_offset_y', 'bitmap_handle', 'palette_handle', 'film_frame_count', 'film_image_count', 'relative_preview_png', 'preview_png', 'unresolved_reason', 'args_display']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event_row in all_event_rows:
            writer.writerow({key: event_row.get(key, '') for key in fieldnames})
    return out_root / 'play_first_export_report.json'


def mode_playcomposite(input_dir: Path, out: Path, scenes: List[str], max_images: int,
                       max_scripts_per_file: int, max_steps: int, max_paths: int) -> Path:
    sys.path.insert(0, str(ROOT))
    from PIL import Image, ImageDraw, ImageFont
    from tinsel1_visual_asset_exporter import safe_name
    import collections

    mode_backgrounds(input_dir, out, scenes, max_images, max_scripts_per_file, max_steps, max_paths)
    mode_playfirst(input_dir, out, scenes, max_images, max_scripts_per_file, max_steps, max_paths)

    background_index_path = out / 'background_export' / 'background_export_index.json'
    background_index = {}
    if background_index_path.exists():
        background_index = json.loads(background_index_path.read_text(encoding='utf-8'))
    generated_timeline_root = input_dir.parent.parent / 'discworld_all_generated_csvs'
    generated_timeline_out_root = out / 'scene_space_placement'
    if generated_timeline_out_root.exists():
        shutil.rmtree(generated_timeline_out_root)
    generated_timeline_out_root.mkdir(parents=True, exist_ok=True)
    fully_trusted_generated_scenes = {'BAR.SCN', 'FINALE.SCN'}
    trusted_auto_position_sources = {
        'placement_snapshot',
        'timeline_actor_state',
        'timeline_args',
        'timeline_film_replay',
        'timeline_motion',
        'timeline_neighbor_carry',
        'timeline_offset',
        'timeline_prefix_known_non_tiny',
        'timeline_scroll_prefix',
        'timeline_overedge_cluster_carry',
        'timeline_bootstrap_carry',
        'timeline_talk_family_carry',
        'timeline_waittime_family_carry',
        'timeline_waitframe_prefix',
        'timeline_talk_anchor',
        'timeline_talkat_anchor',
        'trace_stack_top',
    }
    placement_builder = None

    play_root = out / 'play_first_export'
    out_root = out / 'play_composite_export'
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    def load_font(size: int = 12):
        try:
            return ImageFont.truetype('DejaVuSans.ttf', size)
        except Exception:
            return ImageFont.load_default()

    def parse_int(value: Any, default: int = 0) -> int:
        if value in ('', None):
            return default
        try:
            return int(value)
        except Exception:
            return default

    def sprite_position(event_row: dict, sprite: Image.Image) -> tuple[int, int]:
        x = parse_int(event_row.get('x'), 0)
        y = parse_int(event_row.get('y'), 0)
        if event_row.get('anim_offset_x') not in ('', None) and event_row.get('anim_offset_y') not in ('', None):
            return x - parse_int(event_row.get('anim_offset_x'), 0), y - parse_int(event_row.get('anim_offset_y'), 0)
        return x - sprite.width // 2, y - sprite.height

    def load_placement_builder():
        nonlocal placement_builder
        if placement_builder is not None:
            return placement_builder
        builder_path = ROOT.parent / 'scripts' / 'build_bar_play_placement_timeline.py'
        spec = importlib.util.spec_from_file_location('discworld_scene_space_builder', builder_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f'Unable to load placement builder: {builder_path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        placement_builder = module
        return module

    def ensure_generated_scene_positions(scene_name: str) -> tuple[Optional[Path], str]:
        stem = safe_name(scene_name)
        curated_path = generated_timeline_root / f'{stem}_scene_space_playback_timeline_full.csv'
        if curated_path.exists():
            mode = 'curated_generated_csv' if scene_name in fully_trusted_generated_scenes else 'external_generated_trusted_sources'
            return curated_path, mode

        scene_key = Path(scene_name).stem.upper()
        scene_timeline_csv = out / 'scene_timeline' / f'{scene_key}_timeline.csv'
        vm_lite_csv = out / 'vm_lite_trace' / 'vm_lite_film_events.csv'
        scheduler_csv = out / 'scheduler' / 'scheduler_trace_events.csv'
        if not scene_timeline_csv.exists() or not vm_lite_csv.exists():
            return None, 'missing_scene_timeline_or_vm_lite'

        output_csv = generated_timeline_out_root / f'{stem}_scene_space_playback_timeline_full.csv'
        if not output_csv.exists():
            builder = load_placement_builder()
            timeline_rows, manifest = builder.build_timeline(
                vm_lite_csv,
                scene_name=scene_name,
                timeline_csv=scene_timeline_csv,
                scheduler_csv=scheduler_csv if scheduler_csv.exists() else None,
                include_motion_anchor=True,
            )
            builder.write_outputs(timeline_rows, manifest, output_csv)
        return output_csv, 'auto_generated_trusted_sources'

    def load_generated_scene_positions(timeline_path: Path, trusted_sources: Optional[set[str]] = None) -> tuple[dict[int, dict[str, Any]], list[Optional[dict[str, Any]]]]:
        positions = {}
        ordered_positions = []
        with timeline_path.open('r', encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                if (row.get('libcall') or '').upper() != 'PLAY':
                    continue
                position = {
                    'x': parse_int(row.get('x_used'), -1),
                    'y': parse_int(row.get('y_used'), -1),
                    'position_source': row.get('position_source', ''),
                }
                is_trusted = trusted_sources is None or position['position_source'] in trusted_sources
                ordered_positions.append(position if is_trusted else None)
                seq = parse_int(row.get('event_seq'), -1)
                if is_trusted and seq >= 0:
                    positions[seq] = position
        return positions, ordered_positions

    results = []
    layer_rows = []
    for scene in scenes:
        scene = scene.upper() if scene.upper().endswith('.SCN') else scene.upper() + '.SCN'
        stem = safe_name(scene)
        scene_dir = out_root / stem
        scene_dir.mkdir(parents=True, exist_ok=True)

        row = {'scene': scene}
        bg_row = background_index.get(scene, {})
        background_png = bg_row.get('copied_png') or ''
        if bg_row.get('scene_kind') == 'container':
            row['note'] = bg_row.get('note', 'container scene')
            results.append(row)
            continue
        if scene == 'DW.SCN':
            row['note'] = 'root resource bundle; no scene background'
            results.append(row)
            continue
        if not background_png or not Path(background_png).exists():
            row['error'] = 'missing background export'
            results.append(row)
            continue

        play_manifest_path = play_root / stem / 'manifest.json'
        if not play_manifest_path.exists():
            row['error'] = 'missing playfirst manifest'
            results.append(row)
            continue

        play_manifest = json.loads(play_manifest_path.read_text(encoding='utf-8'))
        scene_position_timeline, position_timeline_mode = ensure_generated_scene_positions(scene)
        if scene_position_timeline is not None:
            trusted_sources = None if position_timeline_mode == 'curated_generated_csv' else trusted_auto_position_sources
            generated_positions, ordered_generated_positions = load_generated_scene_positions(scene_position_timeline, trusted_sources=trusted_sources)
        else:
            generated_positions, ordered_generated_positions = {}, []
        canvas = Image.open(background_png).convert('RGBA')
        draw = ImageDraw.Draw(canvas)
        font = load_font(12)

        resolved_events = [event for event in play_manifest.get('events', []) if event.get('preview_png')]
        for play_index, event in enumerate(resolved_events):
            seq = parse_int(event.get('seq'), -1)
            generated = generated_positions.get(seq)
            if not generated and play_index < len(ordered_generated_positions):
                generated = ordered_generated_positions[play_index]
            if generated:
                event['x_used'] = generated.get('x', -1)
                event['y_used'] = generated.get('y', -1)
                event['position_source'] = generated.get('position_source', 'generated_scene_space_timeline')
            else:
                event['x_used'] = parse_int(event.get('x'), -1)
                event['y_used'] = parse_int(event.get('y'), -1)
                event['position_source'] = 'nominal_play_args'
        resolved_events.sort(key=lambda event: (parse_int(event.get('y_used'), 0), parse_int(event.get('seq'), 0)))

        composited_count = 0
        skipped_negative_xy_count = 0
        source_counts = collections.Counter()
        for event in resolved_events:
            x = parse_int(event.get('x_used'), -1)
            y = parse_int(event.get('y_used'), -1)
            source_counts[event.get('position_source') or 'unknown'] += 1
            if x < 0 or y < 0:
                skipped_negative_xy_count += 1
                continue
            event['x'] = x
            event['y'] = y
            preview_png = event.get('preview_png')
            if not preview_png or not Path(preview_png).exists():
                continue
            sprite = Image.open(preview_png).convert('RGBA')
            px, py = sprite_position(event, sprite)
            canvas.alpha_composite(sprite, (px, py))
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 0, 255))
            layer_rows.append({
                'scene': scene,
                'seq': event.get('seq', ''),
                'film_handle': event.get('film_handle', ''),
                'x': x,
                'y': y,
                'paste_x': px,
                'paste_y': py,
                'position_source': event.get('position_source', ''),
                'preview_png': preview_png,
            })
            composited_count += 1

        draw.rectangle([0, 0, min(canvas.width, 520), 30], fill=(0, 0, 0, 160))
        draw.text((6, 7), f'{scene} PLAY composite | placed={composited_count} skipped={skipped_negative_xy_count}', fill=(255, 255, 255, 255), font=font)

        composite_png = scene_dir / f'{stem}_play_composite.png'
        canvas.save(composite_png)

        scene_manifest = {
            'scene': scene,
            'background_png': background_png,
            'play_manifest': str(play_manifest_path),
            'composite_png': str(composite_png),
            'play_event_count': play_manifest.get('event_count', 0),
            'resolved_preview_count': play_manifest.get('resolved_preview_count', 0),
            'composited_event_count': composited_count,
            'skipped_negative_xy_count': skipped_negative_xy_count,
            'position_timeline': str(scene_position_timeline) if scene_position_timeline is not None else '',
            'position_timeline_mode': position_timeline_mode,
            'positioning_mode': 'generated_scene_space_timeline_or_nominal_play_args',
            'position_source_counts': dict(sorted(source_counts.items())),
            'limitations': [
                'Uses curated generated x_used/y_used when available; otherwise can auto-build a scene-space timeline from vm-lite plus scene_timeline and trust only recovered non-fallback sources.',
                'Uses first resolved preview frame per PLAY film; no animation playback.',
                'Sorts by used y then seq as an approximate scene-depth heuristic.',
            ],
        }
        (scene_dir / 'manifest.json').write_text(json.dumps(scene_manifest, indent=2))

        row.update({
            'background_png': background_png,
            'play_manifest': str(play_manifest_path),
            'composite_png': str(composite_png),
            'play_event_count': play_manifest.get('event_count', 0),
            'resolved_preview_count': play_manifest.get('resolved_preview_count', 0),
            'composited_event_count': composited_count,
            'skipped_negative_xy_count': skipped_negative_xy_count,
            'position_timeline': str(scene_position_timeline) if scene_position_timeline is not None else '',
            'position_timeline_mode': position_timeline_mode,
            'position_source_counts': json.dumps(dict(sorted(source_counts.items()))),
            'manifest': str(scene_dir / 'manifest.json'),
        })
        if play_manifest.get('event_count', 0) == 0:
            row['note'] = 'no PLAY events'
        results.append(row)

    report = {
        'mode': 'playcomposite',
        'scenes': results,
        'scene_count': len(results),
        'scene_with_composite_count': sum(1 for row in results if row.get('composited_event_count')),
        'composited_event_count': sum(int(row.get('composited_event_count') or 0) for row in results),
        'skipped_negative_xy_count': sum(int(row.get('skipped_negative_xy_count') or 0) for row in results),
    }
    (out_root / 'play_composite_export_report.json').write_text(json.dumps(report, indent=2))
    with (out_root / 'play_composite_export_summary.csv').open('w', newline='') as f:
        fieldnames = ['scene', 'play_event_count', 'resolved_preview_count', 'composited_event_count', 'skipped_negative_xy_count', 'position_timeline_mode', 'position_source_counts', 'position_timeline', 'background_png', 'play_manifest', 'composite_png', 'manifest', 'note', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    with (out_root / 'play_composite_layer_summary.csv').open('w', newline='') as f:
        fieldnames = ['scene', 'seq', 'film_handle', 'x', 'y', 'paste_x', 'paste_y', 'position_source', 'preview_png']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in layer_rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
    return out_root / 'play_composite_export_report.json'


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
    ap.add_argument('--mode','-m', choices=['chunks','images','scenegraph','pcode','films','visual','vm','scheduler','timelines','backgrounds','playfirst','playcomposite','all'], default='all')
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
    if args.mode in ('backgrounds','all'):
        completed.append(('backgrounds', str(mode_backgrounds(input_dir, out, args.scenes, args.max_images_per_scene, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    if args.mode in ('playfirst','all'):
        completed.append(('playfirst', str(mode_playfirst(input_dir, out, args.scenes, args.max_images_per_scene, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    if args.mode in ('playcomposite','all'):
        completed.append(('playcomposite', str(mode_playcomposite(input_dir, out, args.scenes, args.max_images_per_scene, args.max_scripts_per_file, args.max_steps, args.max_paths))))
    report={'input':str(input_dir),'output':str(out),'mode':args.mode,'completed':completed}
    (out/'discworld_extract_run_report.json').write_text(json.dumps(report, indent=2))
    if args.zip:
        zp=zip_outputs(out)
        report['zip']=str(zp)
        (out/'discworld_extract_run_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
