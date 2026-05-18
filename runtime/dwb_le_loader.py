#!/usr/bin/env python3
from pathlib import Path
import struct, json

SRC_BYTE=0x00; SRC_SEG=0x02; SRC_PTR32=0x03; SRC_OFF16=0x05; SRC_PTR48=0x06; SRC_OFF32=0x07; SRC_OFF32_REL=0x08
S_LIST=0x20
T_MASK=0x03; T_INTERNAL=0x00; T_EXT_ORD=0x01; T_EXT_NAME=0x02; T_INT_ENTRY=0x03
T_ADDITIVE=0x04; T_INT_CHAIN=0x08; T_OFF32=0x10; T_ADD32=0x20; T_OBJ16=0x40; T_ORD8=0x80

def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def w16(b,o,v): struct.pack_into('<H',b,o,v & 0xffff)
def w32(b,o,v): struct.pack_into('<I',b,o,v & 0xffffffff)

def parse_le(path):
    d=Path(path).read_bytes(); le=d.find(b'LE\0\0',0x20000)
    if le<0: raise SystemExit('LE header not found')
    H={k:u32(d,le+o) for k,o in {
        'flags':0x10,'numpages':0x14,'csobj':0x18,'eip':0x1c,'ssobj':0x20,'esp':0x24,'pagesize':0x28,'lastbytes':0x2c,
        'fixsize':0x30,'loadersize':0x38,'objtab':0x40,'objcnt':0x44,'pagemap':0x48,'fixpage':0x68,'fixrec':0x6c,
        'datapages':0x80,'preload':0x84,'autodata':0x94,'heapsz':0xa8,'stacksz':0xac}.items()}
    objs=[]
    for i in range(H['objcnt']):
        off=le+H['objtab']+i*24
        vs,base,flags,ptidx,ptcnt,res=struct.unpack_from('<IIIIII',d,off)
        objs.append({'index':i+1,'vsize':vs,'base':base,'flags':flags,'ptidx':ptidx,'ptcnt':ptcnt,'res':res})
    pm=[]
    for i in range(H['numpages']):
        raw=u32(d,le+H['pagemap']+i*4)
        pm.append({'raw':raw,'pageno':raw>>16,'flags':raw&0xffff})
    data_start=le+H['datapages']
    minb=min(o['base'] for o in objs); maxb=max(o['base']+o['vsize'] for o in objs)
    img=bytearray(maxb-minb); page_infos=[]
    for o in objs:
        for j in range(o['ptcnt']):
            gi=o['ptidx']-1+j; pe=pm[gi]
            file_off=data_start+(pe['pageno']-1)*H['pagesize']
            va=o['base']+j*H['pagesize']
            n=H['pagesize']
            if gi+1==H['numpages'] and H['lastbytes']: n=H['lastbytes']
            n=min(n, max(0,o['vsize']-j*H['pagesize']))
            chunk=d[file_off:min(file_off+n,len(d))]
            img[va-minb:va-minb+len(chunk)]=chunk
            page_infos.append({'global_page':gi+1,'obj':o['index'],'obj_page':j+1,'va':va,'file_off':file_off,'n':n,'present':len(chunk)})
    # fixups
    fixpage=[u32(d,le+H['fixpage']+i*4) for i in range(H['numpages']+1)]
    frec_base=le+H['fixrec']
    relocs=[]; errors=[]
    obj_by_idx={o['index']:o for o in objs}
    def read_ord(p, is16=False):
        if is16:
            return u16(d,p), p+2
        return d[p], p+1
    for pg in range(H['numpages']):
        start,end=fixpage[pg],fixpage[pg+1]
        p=frec_base+start; lim=frec_base+end
        page_va=page_infos[pg]['va'] if pg < len(page_infos) else None
        while p < lim:
            rec_start=p
            try:
                src=d[p]; targ=d[p+1]; p+=2
                src_type=src & 0x0f
                if src & S_LIST:
                    cnt=d[p]; p+=1
                    src_offsets=[u16(d,p+2*i) for i in range(cnt)]; p+=2*cnt
                else:
                    src_offsets=[u16(d,p)]; p+=2
                target_kind=targ & T_MASK
                target_obj=None; target_off=None; target_va=None; add_val=None
                if target_kind == T_INTERNAL:
                    target_obj,p=read_ord(p, bool(targ & T_OBJ16))
                    if targ & T_INT_CHAIN:
                        # not implemented; consume target offset based on flag, but don't apply
                        pass
                    if targ & T_OFF32:
                        target_off=u32(d,p); p+=4
                    else:
                        target_off=u16(d,p); p+=2
                    if target_obj in obj_by_idx:
                        target_va=obj_by_idx[target_obj]['base'] + target_off
                else:
                    # external: module ordinal + proc/name ordinal. Consume minimally.
                    mod,p=read_ord(p, bool(targ & T_OBJ16))
                    if targ & T_ORD8:
                        proc=d[p]; p+=1
                    else:
                        proc=u16(d,p); p+=2
                    target_va=None
                if targ & T_ADDITIVE:
                    if targ & T_ADD32:
                        add_val=u32(d,p); p+=4
                    else:
                        add_val=u16(d,p); p+=2
                    if target_va is not None: target_va += add_val
                for so in src_offsets:
                    if page_va is None: continue
                    loc_va=page_va+so
                    loc=loc_va-minb
                    applied=False; before=None
                    if 0 <= loc < len(img) and target_va is not None:
                        if src_type == SRC_OFF32:
                            before=u32(img,loc); w32(img,loc,target_va); applied=True
                        elif src_type == SRC_OFF32_REL:
                            before=u32(img,loc); w32(img,loc,target_va-(loc_va+4)); applied=True
                        elif src_type == SRC_OFF16:
                            before=u16(img,loc); w16(img,loc,target_va); applied=True
                        elif src_type == SRC_PTR48:
                            # LE 48-bit pointer: 32-bit offset then selector/object word. Store offset and object number.
                            before=u32(img,loc); w32(img,loc,target_va); 
                            if loc+4 < len(img): w16(img,loc+4,target_obj or 0)
                            applied=True
                        elif src_type == SRC_PTR32:
                            before=u16(img,loc); w16(img,loc,target_va); 
                            if loc+2 < len(img): w16(img,loc+2,target_obj or 0)
                            applied=True
                        elif src_type == SRC_SEG:
                            before=u16(img,loc); w16(img,loc,target_obj or 0); applied=True
                    relocs.append({'page':pg+1,'record_file_offset':rec_start,'src':src,'src_type':src_type,'target_flags':targ,'src_offsets':src_offsets,'target_obj':target_obj,'target_off':target_off,'target_va':target_va,'applied':applied,'before':before})
            except Exception as e:
                errors.append({'page':pg+1,'record_file_offset':rec_start,'error':repr(e)})
                break
    return d, le, H, objs, pm, data_start, minb, maxb, img, page_infos, relocs, errors

if __name__ == '__main__':
    d,le,H,objs,pm,data_start,minb,maxb,img,page_infos,relocs,errors=parse_le('/mnt/data/DWB.EXE')
    out=Path('/mnt/data')
    (out/'dwb_le_relocated_image.bin').write_bytes(img)
    for o in objs:
        (out/f'dwb_le_relocated_object{o["index"]}.bin').write_bytes(img[o['base']-minb:o['base']-minb+o['vsize']])
    report={'input':'/mnt/data/DWB.EXE','le_offset':le,'header':H,'objects':objs,'data_start':data_start,'min_base':minb,'max_base':maxb,'entry_va':objs[H['csobj']-1]['base']+H['eip'],'stack_va':objs[H['ssobj']-1]['base']+H['esp'],'page_infos':page_infos,'reloc_count':len(relocs),'reloc_errors':errors[:20],'reloc_type_counts':{},'applied_count':sum(1 for r in relocs if r['applied'])}
    from collections import Counter
    report['reloc_type_counts']={str(k):v for k,v in Counter(r['src_type'] for r in relocs).items()}
    report['reloc_flag_counts']={str(k):v for k,v in Counter(r['target_flags'] for r in relocs).items()}
    # include interesting records near animation jump table page 16/17
    report['sample_relocs']=relocs[:20]
    Path('/mnt/data/dwb_le_relocation_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ['le_offset','header','objects','entry_va','reloc_count','applied_count','reloc_type_counts','reloc_flag_counts','reloc_errors']},indent=2))
