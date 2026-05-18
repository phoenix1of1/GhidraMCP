#!/usr/bin/env python3
"""
GPL-3.0-or-later compatible Discworld/Tinsel 1 visual asset exporter.

This script consumes the static film-reference manifests and exports rendered PNGs
for image handles reachable through PCODE film references. It uses the previously
ported Tinsel 1 PC WrtNonZero renderer.

Default behavior exports a bounded visual-validation set for the highest-value
scenes, while preserving per-scene JSON manifests. Use --max-images-per-scene 0
for an unbounded export.
"""
from __future__ import annotations
import argparse, json, os, shutil, zipfile, csv
from pathlib import Path
from collections import defaultdict, Counter

from PIL import Image, ImageDraw

# Reuse the validated renderer module.
import sys
sys.path.insert(0, '/mnt/data')
from tinsel1_renderer import Tinsel1Scene

TOP_SCENES = ['CLIMAX.SCN','FINALE.SCN','CITYGATE.SCN','PALENT.SCN','CUTBARN.SCN','PASTINNR.SCN','DUNNYMAN.SCN','CUTTHRON.SCN','BAR.SCN','PASTHIDE.SCN']


def collect_images_from_manifest(manifest: dict):
    """Return ordered unique image refs plus a film/frame relationship graph."""
    seen = set()
    images = []
    graph = []
    for film_ref_idx, ref in enumerate(manifest.get('film_refs', [])):
        film = ref.get('film', {})
        film_node = {
            'film_ref_index': film_ref_idx,
            'script_handle': ref.get('script_handle'),
            'script_source': ref.get('script_source'),
            'script_ip': ref.get('script_ip'),
            'op': ref.get('op'),
            'film_handle': ref.get('film_handle'),
            'film_resolved': film.get('resolved'),
            'frate': film.get('frate'),
            'numreels': film.get('numreels'),
            'reels': []
        }
        for reel in film.get('reels', []):
            reel_node = {
                'reel_index': reel.get('reel_index'),
                'mobj_handle': reel.get('mobj_handle'),
                'ani_script_handle': reel.get('ani_script_handle'),
                'multi_init': reel.get('multi_init'),
                'frames': []
            }
            for frame in reel.get('frames', []):
                frame_node = {'frame_handle': frame.get('handle'), 'images': []}
                for ent in frame.get('entries', []):
                    img = ent.get('image')
                    rec = img.get('image_record') if img else None
                    if not rec:
                        continue
                    key = img['handle']
                    item = {
                        'image_handle': key,
                        'source_file': img['resolved']['file'],
                        'record_offset': rec['record_offset'],
                        'image_index': rec['image_index'],
                        'width': rec['width'],
                        'height': rec['height'],
                        'anim_offset_x': rec['anim_offset_x'],
                        'anim_offset_y': rec['anim_offset_y'],
                        'bitmap_handle': rec['bitmap_handle'],
                        'palette_handle': rec['palette_handle'],
                    }
                    if key not in seen:
                        seen.add(key); images.append(item)
                    frame_node['images'].append({'image_handle': key})
                reel_node['frames'].append(frame_node)
            film_node['reels'].append(reel_node)
        graph.append(film_node)
    return images, graph


def safe_name(s: str) -> str:
    return s.lower().replace('.scn','').replace('/','_')


def make_contact_sheet(scene_dir: Path, scene_name: str, images_meta: list, max_thumbs=96):
    thumbs = []
    for item in images_meta[:max_thumbs]:
        rel = item.get('png')
        if not rel:
            continue
        p = scene_dir / rel
        if not p.exists():
            continue
        im = Image.open(p).convert('RGBA')
        # Keep aspect, max box 120x80.
        im.thumbnail((120,80), Image.Resampling.LANCZOS)
        thumbs.append((item, im.copy()))
    if not thumbs:
        return None
    cell_w, cell_h = 160, 115
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols*cell_w, rows*cell_h + 30), (255,255,255,255))
    draw = ImageDraw.Draw(sheet)
    draw.text((8,8), f'{scene_name}: first {len(thumbs)} rendered film-referenced images', fill=(0,0,0,255))
    for idx, (item, im) in enumerate(thumbs):
        x = (idx % cols) * cell_w
        y = 30 + (idx // cols) * cell_h
        sheet.alpha_composite(im, (x + (cell_w-im.width)//2, y + 4))
        label = f"#{item['image_index']} {item['width']}x{item['height']}"
        draw.text((x+4, y+88), label, fill=(0,0,0,255))
    out = scene_dir / 'contact_sheet.png'
    sheet.convert('RGB').save(out)
    return 'contact_sheet.png'


def export_scene(root: Path, out_root: Path, scene: str, max_images: int):
    manifest_path = root / 'film_manifest' / f'{safe_name(scene)}_film_manifest.json'
    if not manifest_path.exists():
        return {'scene': scene, 'error': 'missing film manifest'}
    manifest = json.loads(manifest_path.read_text())
    images, graph = collect_images_from_manifest(manifest)
    selected = images if max_images == 0 else images[:max_images]
    scene_dir = out_root / safe_name(scene)
    img_dir = scene_dir / 'images'
    img_dir.mkdir(parents=True, exist_ok=True)

    renderers = {}
    exported = []
    errors = []
    for item in selected:
        source = item['source_file']
        try:
            if source not in renderers:
                renderers[source] = Tinsel1Scene(root / source)
            r = renderers[source]
            recs = r.image_records()
            rec = recs[item['image_index']]
            filename = f"{item['image_handle'].replace('0x','')}_img{item['image_index']:04d}_{item['width']}x{item['height']}.png"
            rel = f'images/{filename}'
            stats = r.save_png(rec, scene_dir / rel)
            item = dict(item)
            item['png'] = rel
            item['render_stats'] = stats.__dict__
            exported.append(item)
        except Exception as e:
            err = dict(item); err['error'] = str(e); errors.append(err)

    # Attach png paths to graph references where available.
    by_handle = {x['image_handle']: x for x in exported}
    for film in graph:
        for reel in film['reels']:
            for frame in reel['frames']:
                for img_ref in frame['images']:
                    meta = by_handle.get(img_ref['image_handle'])
                    if meta:
                        img_ref.update({'png': meta['png'], 'image_index': meta['image_index'], 'size': [meta['width'], meta['height']]})

    contact = make_contact_sheet(scene_dir, scene, exported)
    scene_export_manifest = {
        'scene': scene,
        'source_manifest': str(manifest_path.relative_to(root)),
        'film_ref_count': manifest.get('film_ref_count'),
        'unique_film_count': manifest.get('unique_film_count'),
        'unique_images_available': len(images),
        'unique_images_exported': len(exported),
        'export_limited': max_images != 0 and len(images) > max_images,
        'max_images_per_scene': max_images,
        'contact_sheet': contact,
        'images': exported,
        'render_errors': errors,
        'film_graph': graph,
    }
    (scene_dir / 'manifest.json').write_text(json.dumps(scene_export_manifest, indent=2))
    return {
        'scene': scene,
        'unique_images_available': len(images),
        'unique_images_exported': len(exported),
        'render_errors': len(errors),
        'contact_sheet': str((scene_dir / contact).relative_to(out_root)) if contact else None,
        'manifest': str((scene_dir / 'manifest.json').relative_to(out_root))
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='/mnt/data')
    ap.add_argument('--outdir', default='/mnt/data/visual_asset_export')
    ap.add_argument('--scenes', nargs='*', default=TOP_SCENES)
    ap.add_argument('--max-images-per-scene', type=int, default=250, help='0 means no limit')
    ap.add_argument('--zip', default='/mnt/data/tinsel1_visual_asset_export_outputs.zip')
    args = ap.parse_args()

    root = Path(args.root); out_root = Path(args.outdir)
    if out_root.exists(): shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for scene in args.scenes:
        if not scene.upper().endswith('.SCN'):
            scene = scene.upper() + '.SCN'
        results.append(export_scene(root, out_root, scene.upper(), args.max_images_per_scene))

    report = {
        'description': 'Visual-validation export of PNG assets reachable through static PCODE film references.',
        'scenes_requested': args.scenes,
        'max_images_per_scene': args.max_images_per_scene,
        'scene_results': results,
        'total_unique_images_available': sum(r.get('unique_images_available',0) for r in results),
        'total_pngs_exported': sum(r.get('unique_images_exported',0) for r in results),
        'total_render_errors': sum(r.get('render_errors',0) for r in results),
        'note': 'Default run is intentionally bounded for artifact size. Re-run with --max-images-per-scene 0 for a complete unbounded export.'
    }
    (out_root / 'visual_asset_export_report.json').write_text(json.dumps(report, indent=2))
    with open(out_root / 'visual_asset_export_summary.csv', 'w', newline='') as f:
        fields = ['scene','unique_images_available','unique_images_exported','render_errors','contact_sheet','manifest']
        w = csv.DictWriter(f, fields); w.writeheader(); w.writerows([{k:r.get(k) for k in fields} for r in results])
    findings = ['# Tinsel 1 Visual Asset Export Findings\n\n']
    findings.append(f'- Scenes exported: {len(results)}\n')
    findings.append(f'- PNGs exported: {report["total_pngs_exported"]}\n')
    findings.append(f'- Render errors: {report["total_render_errors"]}\n')
    findings.append(f'- Export limit: {args.max_images_per_scene} images per scene (`0` means unlimited).\n')
    findings.append('\n## Scene summary\n')
    for r in results:
        findings.append(f'- {r.get("scene")}: {r.get("unique_images_exported")}/{r.get("unique_images_available")} unique film-referenced images exported; errors={r.get("render_errors")}\n')
    (out_root / 'visual_asset_export_findings.md').write_text(''.join(findings))

    # Copy key report files to /mnt/data root.
    for name in ['visual_asset_export_report.json','visual_asset_export_summary.csv','visual_asset_export_findings.md']:
        (root / name).write_bytes((out_root / name).read_bytes())

    zpath = Path(args.zip)
    if zpath.exists(): zpath.unlink()
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(Path(__file__), arcname='tinsel1_visual_asset_exporter.py')
        for p in out_root.rglob('*'):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(out_root)))
    print(json.dumps({'zip': str(zpath), 'report': str(root/'visual_asset_export_report.json'), 'summary': str(root/'visual_asset_export_summary.csv'), 'outdir': str(out_root)}, indent=2))

if __name__ == '__main__':
    main()
