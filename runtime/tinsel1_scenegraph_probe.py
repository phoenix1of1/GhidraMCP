#!/usr/bin/env python3
import os, glob, struct, json, argparse
from collections import defaultdict, Counter

SHIFT=23
OFFSETMASK=0x007FFFFF

V1_NAMES={
 0x33340001:'STRING',0x33340002:'BITMAP_HEADER',0x33340003:'BITMAP_DATA',0x33340004:'TERMINAL/CHARMATRIX',
 0x33340005:'PALETTE',0x33340006:'IMAGE',0x33340007:'ANI_FRAME',0x33340008:'FILM',0x33340009:'FONT',
 0x3334000A:'PCODE',0x3334000B:'ENTRANCE',0x3334000C:'POLYGONS',0x3334000D:'ACTORS',0x3334000E:'SCENE',
 0x3334000F:'TOTAL_ACTORS',0x33340010:'TOTAL_GLOBALS',0x33340011:'TOTAL_OBJECTS',0x33340012:'OBJECTS',0x33340015:'TOTAL_POLY'
}

class TinselSet:
    def __init__(self, root):
        self.root=root
        self.index=self.read_index(os.path.join(root,'INDEX'))
        self.by_name={r['name'].lower(): r for r in self.index}
        self.files={}
        for p in glob.glob(os.path.join(root,'*.SCN')):
            name=os.path.basename(p).lower()
            self.files[name]=open(p,'rb').read()
        self.chunk_maps={name:self.walk_chunks(data) for name,data in self.files.items()}
    def read_index(self,path):
        b=open(path,'rb').read(); out=[]
        for i in range(0,len(b),20):
            name=b[i:i+12].split(b'\0')[0].decode('latin1').lower()
            fs=struct.unpack_from('<I',b,i+12)[0]
            out.append({'index':i//20,'name':name,'size':fs&0x00ffffff,'flags':fs>>24,'raw_size_flags':fs})
        return out
    def walk_chunks(self,b):
        out=[]; off=0; seen=set()
        while off+8 <= len(b) and off not in seen:
            seen.add(off)
            cid,nxt=struct.unpack_from('<II',b,off)
            end=nxt if nxt else len(b)
            out.append({'offset':off,'id':cid,'name':V1_NAMES.get(cid,hex(cid)),'next':nxt,'payload_offset':off+8,'payload_size':max(0,end-off-8)})
            if nxt==0: break
            if nxt<=off or nxt>len(b): break
            off=nxt
        return out
    def handle_parts(self,h):
        return h>>SHIFT, h&OFFSETMASK
    def file_for_index(self,i):
        if 0<=i<len(self.index): return self.index[i]['name']
    def chunk_at(self,filename,off):
        for ch in self.chunk_maps.get(filename.lower(),[]):
            po=ch['payload_offset']; pe=po+ch['payload_size']
            if po <= off < pe: return ch
        # allow chunk header exact offset
        for ch in self.chunk_maps.get(filename.lower(),[]):
            if ch['offset']==off: return ch
        return None
    def resolve(self,h):
        i,off=self.handle_parts(h); name=self.file_for_index(i); ch=self.chunk_at(name,off) if name else None
        return {'handle':h,'hex':f'0x{h:08x}','index':i,'file':name,'offset':off,'chunk':None if not ch else {'id':f'0x{ch["id"]:08x}','name':ch['name'],'chunk_offset':ch['offset']}}
    def u32(self,name,off): return struct.unpack_from('<I',self.files[name],off)[0]
    def i32(self,name,off): return struct.unpack_from('<i',self.files[name],off)[0]
    def parse_scene(self,name):
        ch=next((c for c in self.chunk_maps[name] if c['id']==0x3334000E),None)
        if not ch or ch['payload_size']<32: return None
        p=ch['payload_offset']; vals=struct.unpack_from('<IIIIIIII',self.files[name],p)
        keys=['numEntrance','numPoly','numTaggedActor','defRefer','hSceneScript','hEntrance','hPoly','hTaggedActor']
        d=dict(zip(keys,vals))
        for k in ['hSceneScript','hEntrance','hPoly','hTaggedActor']:
            d[k+'_resolved']=self.resolve(d[k]) if d[k] else None
        return d
    def parse_actor_data(self,name,scene):
        if not scene or not scene.get('hTaggedActor'): return []
        off=scene['hTaggedActor']&OFFSETMASK; n=scene['numTaggedActor']; data=self.files[name]; out=[]
        for j in range(n):
            p=off+j*12
            if p+12>len(data): break
            masking,actor_id,code=struct.unpack_from('<III',data,p)
            out.append({'masking':masking,'actor_id':actor_id,'actor_code':f'0x{code:08x}','actor_code_resolved':self.resolve(code) if code else None})
        return out
    def parse_entrances(self,name,scene):
        if not scene or not scene.get('hEntrance'): return []
        off=scene['hEntrance']&OFFSETMASK; n=scene['numEntrance']; data=self.files[name]; out=[]
        for j in range(n):
            p=off+j*8
            if p+8>len(data): break
            enum,script=struct.unpack_from('<II',data,p)
            out.append({'eNumber':enum,'hScript':f'0x{script:08x}','script_resolved':self.resolve(script) if script else None})
        return out
    def parse_inventory_objects(self):
        name='objects.scn'
        if name not in self.files: return None
        count_ch=next((c for c in self.chunk_maps[name] if c['id']==0x33340011),None)
        obj_ch=next((c for c in self.chunk_maps[name] if c['id']==0x33340012),None)
        if not count_ch or not obj_ch: return None
        n=self.u32(name,count_ch['payload_offset'])
        out=[]
        for j in range(n):
            p=obj_ch['payload_offset']+j*16
            oid,film,script,attr=struct.unpack_from('<IIII',self.files[name],p)
            out.append({'id':oid,'iconFilm':f'0x{film:08x}','iconFilm_resolved':self.resolve(film),'script':f'0x{script:08x}','script_resolved':self.resolve(script) if script else None,'attributes':attr})
        return {'count':n,'record_size':16,'objects':out}
    def parse_film_at(self,h):
        res=self.resolve(h); name=res['file']; off=res['offset']
        if not name or name not in self.files or off+8>len(self.files[name]): return None
        data=self.files[name]
        frate,num=struct.unpack_from('<ii',data,off)
        if not (0<=num<=32 and 0<frate<=120 and off+8+num*8<=len(data)): return None
        reels=[]
        for j in range(num):
            mobj,script=struct.unpack_from('<II',data,off+8+j*8)
            reels.append({'mobj':f'0x{mobj:08x}','mobj_resolved':self.resolve(mobj),'script':f'0x{script:08x}','script_resolved':self.resolve(script)})
        return {'handle':f'0x{h:08x}','frate':frate,'numreels':num,'reels':reels,'resolved':res}
    def parse_multi_init(self,h):
        res=self.resolve(h); name=res['file']; off=res['offset']
        if not name or name not in self.files or off+24>len(self.files[name]): return None
        fields=struct.unpack_from('<IIIIII',self.files[name],off)
        keys=['hMulFrame','mulFlags','mulID','mulX','mulY','mulZ']
        d=dict(zip(keys,fields)); d['resolved']=res
        d['hMulFrame_hex']=f'0x{d["hMulFrame"]:08x}'; d['hMulFrame_resolved']=self.resolve(d['hMulFrame']) if d['hMulFrame'] else None
        return d
    def parse_frame(self,h,limit=20):
        res=self.resolve(h); name=res['file']; off=res['offset']
        if not name or name not in self.files: return None
        data=self.files[name]; vals=[]
        for k in range(limit):
            if off+4*k+4>len(data): break
            v=struct.unpack_from('<I',data,off+4*k)[0]
            vals.append({'value':f'0x{v:08x}','resolved':self.resolve(v) if v else None})
            if v==0: break
        return {'handle':f'0x{h:08x}','resolved':res,'entries':vals}
    def parse_anim_script(self,h,limit=40):
        res=self.resolve(h); name=res['file']; off=res['offset']
        if not name or name not in self.files: return None
        data=self.files[name]; out=[]; pos=0
        for k in range(limit):
            if off+4*pos+4>len(data): break
            raw=struct.unpack_from('<I',data,off+4*pos)[0]
            entry={'index':pos,'raw':f'0x{raw:08x}'}
            if raw==0: entry['op']='ANI_END'; out.append(entry); break
            elif raw==1:
                entry['op']='ANI_JUMP'
                if off+4*(pos+1)+4<=len(data):
                    operand=struct.unpack_from('<i',data,off+4*(pos+1))[0]
                    entry['operand']=operand; out.append(entry); pos+=2; continue
            elif raw in [2,3,4,8,10,11]: entry['op']={2:'ANI_HFLIP',3:'ANI_VFLIP',4:'ANI_HVFLIP',8:'ANI_NOSLEEP',10:'ANI_HIDE',11:'ANI_STOP'}[raw]
            elif raw in [5,6]:
                entry['op']={5:'ANI_ADJUSTX',6:'ANI_ADJUSTY'}[raw]
                if off+4*(pos+1)+4<=len(data): entry['operand']=struct.unpack_from('<i',data,off+4*(pos+1))[0]; out.append(entry); pos+=2; continue
            elif raw==7:
                entry['op']='ANI_ADJUSTXY'
                if off+4*(pos+2)+4<=len(data): entry['x']=struct.unpack_from('<i',data,off+4*(pos+1))[0]; entry['y']=struct.unpack_from('<i',data,off+4*(pos+2))[0]; out.append(entry); pos+=3; continue
            elif raw==9: entry['op']='ANI_CALL'
            else:
                entry['op']='FRAME_HANDLE'; entry['resolved']=self.resolve(raw)
            out.append(entry); pos+=1
        return {'handle':f'0x{h:08x}','resolved':res,'entries':out}
    def scan_pcode_film_handles(self,name):
        data=self.files[name]; films=set()
        for ch in self.chunk_maps[name]:
            if ch['id']!=0x3334000A: continue
            start=ch['payload_offset']; end=start+ch['payload_size']
            for off in range(start,end-3):
                v=struct.unpack_from('<I',data,off)[0]
                r=self.resolve(v)
                if r['file']==name and r['chunk'] and r['chunk']['id']=='0x33340008':
                    pf=self.parse_film_at(v)
                    if pf: films.add(v)
        return sorted(films)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/mnt/data')
    ap.add_argument('--out',default='/mnt/data/tinsel1_scenegraph_report.json')
    args=ap.parse_args()
    ts=TinselSet(args.root)
    chunk_sequences=Counter(tuple(c['id'] for c in cm) for cm in ts.chunk_maps.values())
    scenes={}
    for name in sorted(ts.files):
        ss=ts.parse_scene(name)
        if ss:
            actors=ts.parse_actor_data(name,ss)
            entrances=ts.parse_entrances(name,ss)
            scenes[name]={'scene':ss,'actor_count':len(actors),'actors_sample':actors[:12],'entrance_count':len(entrances),'entrances':entrances[:20],'pcode_film_handles':[f'0x{x:08x}' for x in ts.scan_pcode_film_handles(name)[:50]]}
    inv=ts.parse_inventory_objects()
    inv_sample=[]
    if inv:
        for obj in inv['objects'][:20]:
            h=int(obj['iconFilm'],16)
            film=ts.parse_film_at(h)
            if film:
                for reel in film['reels'][:1]:
                    mi=ts.parse_multi_init(int(reel['mobj'],16))
                    an=ts.parse_anim_script(int(reel['script'],16),limit=8)
                    fr=ts.parse_frame(mi['hMulFrame'],limit=8) if mi else None
                    reel['multi_init']=mi; reel['anim_script_sample']=an; reel['frame_sample']=fr
            obj2=dict(obj); obj2['film_decode']=film; inv_sample.append(obj2)
    dw={}
    if 'dw.scn' in ts.files:
        for cid in [0x3334000F,0x33340010,0x33340015]:
            ch=next((c for c in ts.chunk_maps['dw.scn'] if c['id']==cid),None)
            if ch: dw[V1_NAMES[cid]]=ts.u32('dw.scn',ch['payload_offset'])
    summary={
        'index_count':len(ts.index),
        'uploaded_scn_count':len(ts.files),
        'chunk_sequences': [{'sequence':[V1_NAMES.get(x,hex(x)) for x in seq],'count':cnt} for seq,cnt in chunk_sequences.most_common()],
        'dw_counts':dw,
        'objects_inventory': None if not inv else {'count':inv['count'],'record_size':inv['record_size'],'sample':inv_sample},
        'scenes':scenes,
        'files_chunk_table': {name:[{**c,'id':f'0x{c["id"]:08x}'} for c in cm] for name,cm in sorted(ts.chunk_maps.items())}
    }
    open(args.out,'w').write(json.dumps(summary,indent=2))
    print(args.out)

if __name__=='__main__': main()
