#!/usr/bin/env python3
"""
GPL-3.0-or-later compatible Discworld/Tinsel 1 film-reference manifest exporter.

Consumes the uploaded Discworld PC .SCN files plus INDEX and resolves static PCODE
OP_FILM/OP_CDFILM references into the resource chain:

script -> film -> reels -> MULTI_INIT -> ANI_SCRIPT frame refs -> FRAME -> IMAGE.

Source basis follows the earlier probes, derived from ScummVM Tinsel implementation:
- scn.h/scn.cpp chunk/handle layout
- handle.cpp image/palette structures
- film/multi/animation structures as validated against uploaded samples
- pcode.cpp opcode/operand rules through tinsel1_pcode_film_refs.csv
"""
from __future__ import annotations
import argparse, csv, json, os, struct, glob, zipfile
from pathlib import Path
from collections import defaultdict, Counter

SHIFT = 23
OFFSETMASK = 0x007FFFFF
CHUNK_IMAGE = 0x33340006
CHUNK_FILM = 0x33340008
CHUNK_PCODE = 0x3334000A

V1_NAMES={
 0x33340001:'STRING',0x33340002:'BITMAP_HEADER',0x33340003:'BITMAP_DATA',0x33340004:'TERMINAL/CHARMATRIX',
 0x33340005:'PALETTE',0x33340006:'IMAGE',0x33340007:'ANI_FRAME',0x33340008:'FILM',0x33340009:'FONT',
 0x3334000A:'PCODE',0x3334000B:'ENTRANCE',0x3334000C:'POLYGONS',0x3334000D:'ACTORS',0x3334000E:'SCENE',
 0x3334000F:'TOTAL_ACTORS',0x33340010:'TOTAL_GLOBALS',0x33340011:'TOTAL_OBJECTS',0x33340012:'OBJECTS',0x33340015:'TOTAL_POLY'
}
ANI_OPS={0:'ANI_END',1:'ANI_JUMP',2:'ANI_HFLIP',3:'ANI_VFLIP',4:'ANI_HVFLIP',5:'ANI_ADJUSTX',6:'ANI_ADJUSTY',7:'ANI_ADJUSTXY',8:'ANI_NOSLEEP',9:'ANI_CALL',10:'ANI_HIDE',11:'ANI_STOP'}


def u32(b, off): return struct.unpack_from('<I', b, off)[0]
def i32(b, off): return struct.unpack_from('<i', b, off)[0]
def i16(b, off): return struct.unpack_from('<h', b, off)[0]
def u16(b, off): return struct.unpack_from('<H', b, off)[0]

class TinselSet:
    def __init__(self, root: Path):
        self.root=Path(root)
        self.index=self.read_index(self.root/'INDEX')
        self.files={p.name.lower(): p.read_bytes() for p in self.root.glob('*.SCN')}
        self.chunk_maps={n:self.walk_chunks(b) for n,b in self.files.items()}
        self._image_cache={}
    def read_index(self,path):
        b=path.read_bytes(); out=[]
        for i in range(0,len(b),20):
            name=b[i:i+12].split(b'\0')[0].decode('latin1').lower()
            fs=u32(b,i+12)
            out.append({'index':i//20,'name':name,'size':fs&0x00ffffff,'flags':fs>>24,'raw_size_flags':fs})
        return out
    def walk_chunks(self,b):
        out=[]; off=0; seen=set()
        while off+8<=len(b) and off not in seen:
            seen.add(off); cid=u32(b,off); nxt=u32(b,off+4); end=len(b) if nxt==0 else nxt
            out.append({'offset':off,'id':cid,'name':V1_NAMES.get(cid,hex(cid)),'next':nxt,'payload_offset':off+8,'payload_size':max(0,end-off-8)})
            if nxt==0 or nxt<=off or nxt>len(b): break
            off=nxt
        return out
    def file_for_index(self,i): return self.index[i]['name'] if 0<=i<len(self.index) else None
    def handle_parts(self,h): return h>>SHIFT, h&OFFSETMASK
    def chunk_at(self,name,off):
        if not name: return None
        for ch in self.chunk_maps.get(name.lower(),[]):
            if ch['payload_offset'] <= off < ch['payload_offset']+ch['payload_size']:
                return ch
        for ch in self.chunk_maps.get(name.lower(),[]):
            if ch['offset']==off: return ch
        return None
    def resolve(self,h):
        idx,off=self.handle_parts(h); name=self.file_for_index(idx); ch=self.chunk_at(name,off) if name else None
        return {'handle':f'0x{h:08X}','file_index':idx,'file':name.upper() if name else None,'offset':off,'chunk_id':None if not ch else f'0x{ch["id"]:08X}','chunk_name':None if not ch else ch['name']}
    def image_records(self,name):
        key=name.lower()
        if key in self._image_cache: return self._image_cache[key]
        b=self.files.get(key); out_by_offset={}; out=[]
        if not b:
            return {'list': [], 'by_offset': {}}
        ch=next((c for c in self.chunk_maps[key] if c['id']==CHUNK_IMAGE),None)
        if not ch or ch['payload_size']%16:
            return {'list': [], 'by_offset': {}}
        for n,off in enumerate(range(ch['payload_offset'], ch['payload_offset']+ch['payload_size'], 16)):
            rec={
                'image_index': n,
                'record_offset': off,
                'width': i16(b,off),
                'height': u16(b,off+2),
                'anim_offset_x': i16(b,off+4),
                'anim_offset_y': i16(b,off+6),
                'bitmap_handle': f'0x{u32(b,off+8):08X}',
                'bitmap_offset': u32(b,off+8)&OFFSETMASK,
                'palette_handle': f'0x{u32(b,off+12):08X}',
                'palette_offset': u32(b,off+12)&OFFSETMASK,
            }
            out.append(rec); out_by_offset[off]=rec
        self._image_cache[key]={'list':out,'by_offset':out_by_offset}
        return self._image_cache[key]
    def parse_image_handle(self,h):
        res=self.resolve(h)
        if res['file'] and res['chunk_id']=='0x33340006':
            rec=self.image_records(res['file'])['by_offset'].get(res['offset'])
            return {'handle':f'0x{h:08X}', 'resolved':res, 'image_record':rec}
        return {'handle':f'0x{h:08X}', 'resolved':res, 'image_record':None}
    def parse_film(self,h):
        res=self.resolve(h); name=(res['file'] or '').lower(); off=res['offset']; b=self.files.get(name)
        if not b or off+8>len(b) or res['chunk_id']!='0x33340008':
            return {'handle':f'0x{h:08X}','resolved':res,'error':'not a FILM handle'}
        frate,num=struct.unpack_from('<ii',b,off)
        if not (0 <= num <= 64 and -10000 < frate < 10000 and off+8+num*8 <= len(b)):
            return {'handle':f'0x{h:08X}','resolved':res,'error':f'invalid FILM header frate={frate} numreels={num}'}
        reels=[]
        for r in range(num):
            mobj=u32(b,off+8+r*8); script=u32(b,off+12+r*8)
            reels.append({'reel_index':r,'mobj_handle':f'0x{mobj:08X}','mobj_resolved':self.resolve(mobj),'ani_script_handle':f'0x{script:08X}','ani_script_resolved':self.resolve(script)})
        return {'handle':f'0x{h:08X}','resolved':res,'frate':frate,'numreels':num,'reels':reels}
    def parse_multi_init(self,h):
        res=self.resolve(h); name=(res['file'] or '').lower(); off=res['offset']; b=self.files.get(name)
        if not b or off+24>len(b): return None
        vals=struct.unpack_from('<IIIIII',b,off)
        hframe, flags, mid, mx, my, mz=vals
        return {'handle':f'0x{h:08X}','resolved':res,'hMulFrame':f'0x{hframe:08X}','hMulFrame_resolved':self.resolve(hframe),'mulFlags':flags,'mulID':mid,'mulX':mx,'mulY':my,'mulZ':mz}
    def parse_frame(self,h,limit=200):
        res=self.resolve(h); name=(res['file'] or '').lower(); off=res['offset']; b=self.files.get(name)
        if not b: return None
        entries=[]; images=[]
        for k in range(limit):
            if off+4*k+4>len(b): break
            v=u32(b,off+4*k)
            ent={'entry_index':k,'value':f'0x{v:08X}'}
            if v==0:
                ent['terminator']=True; entries.append(ent); break
            ent['resolved']=self.resolve(v)
            if ent['resolved']['chunk_id']=='0x33340006':
                img=self.parse_image_handle(v)
                ent['image']=img
                if img.get('image_record'): images.append(img['image_record'])
            entries.append(ent)
        return {'handle':f'0x{h:08X}','resolved':res,'entries':entries,'image_count':len(images),'images':images}
    def parse_anim_script(self,h,limit=500):
        res=self.resolve(h); name=(res['file'] or '').lower(); off=res['offset']; b=self.files.get(name)
        if not b: return None
        entries=[]; frame_handles=[]; pos=0
        while len(entries)<limit and off+4*pos+4<=len(b):
            raw=u32(b,off+4*pos); e={'word_index':pos,'raw':f'0x{raw:08X}'}
            if raw in ANI_OPS:
                e['op']=ANI_OPS[raw]
                if raw==0:
                    entries.append(e); break
                elif raw==1:
                    e['operand']=i32(b,off+4*(pos+1)) if off+4*(pos+1)+4<=len(b) else None; entries.append(e); pos+=2; continue
                elif raw in (5,6):
                    e['operand']=i32(b,off+4*(pos+1)) if off+4*(pos+1)+4<=len(b) else None; entries.append(e); pos+=2; continue
                elif raw==7:
                    e['x']=i32(b,off+4*(pos+1)) if off+4*(pos+1)+4<=len(b) else None
                    e['y']=i32(b,off+4*(pos+2)) if off+4*(pos+2)+4<=len(b) else None
                    entries.append(e); pos+=3; continue
            else:
                e['op']='FRAME_HANDLE'; e['resolved']=self.resolve(raw); frame_handles.append(raw)
            entries.append(e); pos+=1
        return {'handle':f'0x{h:08X}','resolved':res,'entries':entries,'frame_handles':[f'0x{x:08X}' for x in frame_handles]}
    def resolve_film_chain(self,h,deep=True):
        film=self.parse_film(h)
        if film.get('error') or not deep: return film
        for reel in film.get('reels',[]):
            mobj=int(reel['mobj_handle'],16); scr=int(reel['ani_script_handle'],16)
            mi=self.parse_multi_init(mobj)
            reel['multi_init']=mi
            anim=self.parse_anim_script(scr)
            reel['ani_script']=anim
            frames=[]
            # Prefer explicit frame refs in ani_script; also include hMulFrame as base/default.
            candidates=[]
            if mi and mi.get('hMulFrame'): candidates.append(int(mi['hMulFrame'],16))
            if anim:
                for fh in anim.get('frame_handles',[]):
                    v=int(fh,16)
                    if v not in candidates: candidates.append(v)
            for fh in candidates[:100]:
                fr=self.parse_frame(fh)
                if fr: frames.append(fr)
            reel['frames']=frames
            reel['resolved_image_count']=sum(fr.get('image_count',0) for fr in frames)
        film['resolved_image_count']=sum(r.get('resolved_image_count',0) for r in film.get('reels',[]))
        film['frame_count']=sum(len(r.get('frames',[])) for r in film.get('reels',[]))
        return film

def read_film_refs(path):
    rows=[]
    with open(path,newline='') as f:
        for row in csv.DictReader(f):
            row['film_handle_int']=int(row['film_handle'])
            rows.append(row)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/mnt/data')
    ap.add_argument('--film-refs',default='/mnt/data/tinsel1_pcode_film_refs.csv')
    ap.add_argument('--outdir',default='/mnt/data/film_manifest')
    args=ap.parse_args()
    root=Path(args.root); outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
    ts=TinselSet(root)
    refs=read_film_refs(args.film_refs)
    by_scene=defaultdict(list)
    for r in refs:
        by_scene[r['file'].upper()].append(r)
    film_cache={}
    def get_film(h):
        if h not in film_cache: film_cache[h]=ts.resolve_film_chain(h)
        return film_cache[h]
    scene_manifests={}
    summary_rows=[]
    for scene, rows in sorted(by_scene.items()):
        refs_out=[]; unique_films=set(); image_refs=0; frame_refs=0; unresolved=0
        for r in rows:
            h=r['film_handle_int']; unique_films.add(h)
            film=get_film(h)
            if film.get('error'): unresolved+=1
            image_refs += film.get('resolved_image_count',0) or 0
            frame_refs += film.get('frame_count',0) or 0
            refs_out.append({
                'script_handle': r['script_handle'],
                'script_source': r['source'],
                'script_ip': int(r['script_ip']),
                'op': r['op'],
                'film_handle': r['film_handle_hex'],
                'film': film
            })
        sm={'scene':scene,'film_ref_count':len(rows),'unique_film_count':len(unique_films),'resolved_image_ref_count':image_refs,'resolved_frame_ref_count':frame_refs,'unresolved_film_refs':unresolved,'film_refs':refs_out}
        scene_manifests[scene]=sm
        (outdir/f'{scene.lower().replace(".scn","")}_film_manifest.json').write_text(json.dumps(sm,indent=2))
        summary_rows.append({'scene':scene,'film_ref_count':len(rows),'unique_film_count':len(unique_films),'frame_ref_count':frame_refs,'image_ref_count':image_refs,'unresolved_film_refs':unresolved})
    global_report={
        'scn_files_loaded': len(ts.files),
        'indexed_files': len(ts.index),
        'scenes_with_pcode_film_refs': len(scene_manifests),
        'total_pcode_film_refs': len(refs),
        'unique_film_handles': len(film_cache),
        'total_resolved_frame_refs': sum(r['frame_ref_count'] for r in summary_rows),
        'total_resolved_image_refs': sum(r['image_ref_count'] for r in summary_rows),
        'unresolved_film_ref_occurrences': sum(r['unresolved_film_refs'] for r in summary_rows),
        'top_scenes_by_image_refs': sorted(summary_rows,key=lambda x:x['image_ref_count'],reverse=True)[:20],
        'top_scenes_by_film_refs': sorted(summary_rows,key=lambda x:x['film_ref_count'],reverse=True)[:20],
        'unique_films': {f'0x{h:08X}':film_cache[h] for h in sorted(film_cache)},
        'scene_manifest_files': {scene: f'film_manifest/{scene.lower().replace(".scn","")}_film_manifest.json' for scene in scene_manifests}
    }
    (outdir/'tinsel1_film_manifest_report.json').write_text(json.dumps(global_report,indent=2))
    with open(outdir/'tinsel1_film_manifest_summary.csv','w',newline='') as f:
        fieldnames=['scene','film_ref_count','unique_film_count','frame_ref_count','image_ref_count','unresolved_film_refs']
        w=csv.DictWriter(f,fieldnames=fieldnames); w.writeheader(); w.writerows(summary_rows)
    with open(outdir/'tinsel1_unique_films.csv','w',newline='') as f:
        fieldnames=['film_handle','file','offset','frate','numreels','frame_count','image_count','error']
        w=csv.DictWriter(f,fieldnames=fieldnames); w.writeheader()
        for h,film in sorted(film_cache.items()):
            res=film.get('resolved',{})
            w.writerow({'film_handle':f'0x{h:08X}','file':res.get('file'),'offset':res.get('offset'),'frate':film.get('frate'),'numreels':film.get('numreels'),'frame_count':film.get('frame_count',0),'image_count':film.get('resolved_image_count',0),'error':film.get('error','')})
    findings=[]
    findings.append('# Tinsel 1 Film Manifest Findings\n')
    findings.append(f'- Loaded {len(ts.files)} `.SCN` files and {len(ts.index)} `INDEX` records.\n')
    findings.append(f'- Resolved {len(refs)} static PCODE film-reference occurrences.\n')
    findings.append(f'- Unique film handles: {len(film_cache)}.\n')
    findings.append(f'- Resolved frame references: {global_report["total_resolved_frame_refs"]}.\n')
    findings.append(f'- Resolved image references: {global_report["total_resolved_image_refs"]}.\n')
    findings.append(f'- Unresolved film-reference occurrences: {global_report["unresolved_film_ref_occurrences"]}.\n')
    findings.append('\n## Top scenes by resolved image references\n')
    for row in global_report['top_scenes_by_image_refs'][:10]:
        findings.append(f'- {row["scene"]}: {row["image_ref_count"]} image refs via {row["film_ref_count"]} PCODE film refs.\n')
    findings.append('\n## Output\n')
    findings.append('Per-scene manifests are written under `film_manifest/*.json`.\n')
    (outdir/'tinsel1_film_manifest_findings.md').write_text(''.join(findings))
    zip_path=root/'tinsel1_film_manifest_outputs.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(Path(__file__), arcname='tinsel1_film_manifest_exporter.py')
        for p in outdir.glob('*'):
            if p.is_file(): z.write(p, arcname=f'film_manifest/{p.name}')
    # copy top report files to /mnt/data too
    for name in ['tinsel1_film_manifest_report.json','tinsel1_film_manifest_summary.csv','tinsel1_unique_films.csv','tinsel1_film_manifest_findings.md']:
        (root/name).write_bytes((outdir/name).read_bytes())
    print(json.dumps({'zip':str(zip_path),'report':str(root/'tinsel1_film_manifest_report.json'),'summary':str(root/'tinsel1_film_manifest_summary.csv'),'unique_films':str(root/'tinsel1_unique_films.csv')},indent=2))

if __name__=='__main__': main()
