#!/usr/bin/env python3
"""Discworld/Tinsel 1 PC SCN PCODE scanner/disassembler.
GPL-compatible derived from observed Discworld SCN samples and ScummVM opcode docs.

Inputs: directory containing INDEX and *.SCN files.
Outputs: JSON/CSV/Markdown summaries of script handles, OP_FILM/OP_CDFILM references,
and LIBCALL use.
"""
from __future__ import annotations
import argparse, csv, json, struct, os, glob, collections, math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set

OP_NAMES = {
0:'HALT',1:'IMM',2:'ZERO',3:'ONE',4:'MINUSONE',5:'STR',6:'FILM',7:'FONT',8:'PAL',9:'LOAD',10:'GLOAD',11:'STORE',12:'GSTORE',13:'CALL',14:'LIBCALL',15:'RET',16:'ALLOC',17:'JUMP',18:'JMPFALSE',19:'JMPTRUE',20:'EQUAL',21:'LESS',22:'LEQUAL',23:'NEQUAL',24:'GEQUAL',25:'GREAT',26:'PLUS',27:'MINUS',28:'LOR',29:'MULT',30:'DIV',31:'MOD',32:'AND',33:'OR',34:'EOR',35:'LAND',36:'NOT',37:'COMP',38:'NEG',39:'DUP',40:'ESCON',41:'ESCOFF',42:'CIMM',43:'CDFILM',63:'NOOP'
}
OPMASK=0x3F; OPSIZE8=0x40; OPSIZE16=0x80
HAS_OPERAND = {1,5,6,7,8,9,10,11,12,13,14,16,17,18,19,42,43}
HANDLE_MASK=0xFF800000; OFFSET_MASK=0x007FFFFF; HANDLE_SHIFT=23
CHUNK_PCODE=0x3334000A; CHUNK_FILM=0x33340008; CHUNK_SCENE=0x3334000E; CHUNK_ENTRANCE=0x3334000B; CHUNK_ACTORS=0x3334000D; CHUNK_TOTAL_OBJECTS=0x33340011; CHUNK_OBJECTS=0x33340012
DW1_CODES = """ACTORATTR ACTORDIRECTION ACTORREF ACTORSCALE ACTORXPOS ACTORYPOS ADDTOPIC ADDINV1 ADDINV2 ADDOPENINV AUXSCALE BACKGROUND CAMERA CLOSEINVENTORY CONTROL CONVERSATION CONVTOPIC CURSORXPOS CURSORYPOS DECCONVW DECCURSOR DECINV1 DECINV2 DECINVW DECLEAD DECTAGFONT DECTALKFONT DELICON DELINV EFFECTACTOR ESCAPE EVENT GETINVLIMIT HELDOBJECT HIDEACTOR ININVENTORY INVDEPICT INVENTORY KILLACTOR KILLBLOCK KILLEXIT KILLTAG SCREENXPOS MOVECURSOR NEWSCENE NOSCROLL OBJECTHELD OFFSET PAUSE PLAY PLAYMIDI PLAYSAMPLE PREPARESCENE PRINT PRINTOBJ PRINTTAG RANDOM RESTORESCENE SAVESCENE SCALINGREELS SCANICON SCROLL SETACTOR SETBLOCK SETEXIT SETINVLIMIT SETPALETTE SETTAG SETTIMER SHOWPOS SHOWSTRING SPLAY STAND STANDTAG STOPWALK SWALK TAGACTOR TALK TALKATTR TIMER SCREENYPOS TOPPLAY TOPWINDOW UNTAGACTOR VIBRATE WAITKEY WAITTIME WALK WALKED WALKINGACTOR WALKPOLY WALKTAG WHICHINVENTORY ACTORSON CUTSCENE HOOKSCENE IDLETIME RESETIDLETIME TALKAT UNHOOKSCENE WAITFRAME DECCSTRINGS STOPMIDI STOPSAMPLE TALKATS DECFLAGS FADEMIDI CLEARHOOKSCENE SETINVSIZE INWHICHINV NOBLOCKING SAMPLEPLAYING TRYPLAYSAMPLE ENABLEMENU RESTARTGAME QUITGAME FRAMEGRAB PLAYRTF CDPLAY CDLOAD HASRESTARTED RESTORE_CUT RUNMODE SUBTITLES SETLANGUAGE HIGHEST_LIBCODE""".split()
LIBCALL_NAMES={i:name for i,name in enumerate(DW1_CODES)}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i32(b,o): return struct.unpack_from('<i',b,o)[0]
def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def s8(x): return struct.unpack('b', bytes([x]))[0]

def read_index(path: Path):
    data=path.read_bytes(); recs=[]
    for n,o in enumerate(range(0,len(data)//20*20,20)):
        name=data[o:o+12].split(b'\0',1)[0].decode('ascii','replace')
        if not name: continue
        recs.append({'index':n,'filename':name,'raw_size_flags':u32(data,o+12),'ignored':u32(data,o+16),'base':n<<HANDLE_SHIFT})
    return recs

def walk_chunks(data: bytes):
    out=[]; off=0; seen=set()
    while 0<=off<len(data) and off not in seen and off+8<=len(data):
        seen.add(off); cid=u32(data,off); nxt=u32(data,off+4)
        end = len(data) if nxt==0 else nxt
        out.append({'offset':off,'id':cid,'next':nxt,'payload_offset':off+8,'payload_size':max(0,end-(off+8))})
        if nxt==0: break
        off=nxt
    return out

def chunk_map(data): return {c['id']:c for c in walk_chunks(data)}

def handle_to_file_offset(h:int): return h>>HANDLE_SHIFT, h&OFFSET_MASK

def fmt_handle(h): return f"0x{h:08X}"

def fetch(data, ip, opcode):
    if opcode & OPSIZE8:
        if ip>=len(data): raise EOFError
        return s8(data[ip]), ip+1, 1
    if opcode & OPSIZE16:
        if ip+2>len(data): raise EOFError
        return i16(data,ip), ip+2, 2
    if ip+4>len(data): raise EOFError
    return i32(data,ip), ip+4, 4

def disassemble(data: bytes, start:int, max_ins=600, stop_at_halt=True):
    ip=start; rows=[]; stack=[]; films=[]; libcalls=[]; branches=[]
    for _ in range(max_ins):
        if ip<0 or ip>=len(data): break
        op_ip=ip; raw=data[ip]; ip+=1; op=raw&OPMASK; name=OP_NAMES.get(op,f'OP_{op}')
        operand=None; operand_size=0
        if op in HAS_OPERAND:
            try: operand, ip, operand_size = fetch(data, ip, raw)
            except EOFError: break
        row={'ip':op_ip,'raw_opcode':raw,'opcode':op,'name':name,'operand':operand,'size':1+operand_size,'stack_before':len(stack)}
        # Tiny symbolic stack for film/libcall adjacency.
        if op in (1,5,6,7,8,42,43):
            kind={1:'imm',5:'str',6:'film',7:'font',8:'pal',42:'cimm',43:'cdfilm'}[op]
            val={'kind':kind,'value':operand,'ip':op_ip}
            stack.append(val)
            if op in (6,43):
                f={'script_ip':op_ip,'op':name,'film_handle':operand,'file_index':(operand>>HANDLE_SHIFT)&0x1FF,'offset':operand&OFFSET_MASK}
                films.append(f); row['film_ref']=f
        elif op==2: stack.append({'kind':'imm','value':0,'ip':op_ip})
        elif op==3: stack.append({'kind':'imm','value':1,'ip':op_ip})
        elif op==4: stack.append({'kind':'imm','value':-1,'ip':op_ip})
        elif op==14:
            args_snapshot=stack[-8:]
            call={'script_ip':op_ip,'libcall':operand,'libcall_name':LIBCALL_NAMES.get(operand,f'LIB_{operand}'),'near_stack':args_snapshot}
            libcalls.append(call); row['libcall_detail']=call
            # Can't know arity statically. Keep stack but avoid unbounded growth.
            if len(stack)>32: stack=stack[-16:]
        elif op in (17,18,19):
            branches.append({'script_ip':op_ip,'op':name,'target':operand}); row['branch_target']=operand
            if op==17 and operand is not None and 0 <= operand < len(data) and operand != ip:
                # continue linear for scanning; exact execution is not attempted
                pass
        elif op==0:
            rows.append(row); break
        rows.append(row)
    return {'instructions':rows,'films':films,'libcalls':libcalls,'branches':branches,'end_ip':ip}

def safe_get_chunk_payload(data,cid):
    cm=chunk_map(data); c=cm.get(cid)
    if not c: return b'',0
    return data[c['payload_offset']:c['payload_offset']+c['payload_size']], c['payload_offset']

def collect_script_handles(path: Path, idx_by_name: Dict[str,int]):
    data=path.read_bytes(); cm=chunk_map(data); base=(idx_by_name.get(path.name.lower(),-1)<<HANDLE_SHIFT)
    scripts=[]; films=[]
    def add(h,source,extra=None):
        if h and ((h>>HANDLE_SHIFT) == idx_by_name.get(path.name.lower(),-999)):
            scripts.append({'handle':h,'source':source, **(extra or {})})
    # scene chunk
    c=cm.get(CHUNK_SCENE)
    if c and c['payload_size']>=32:
        po=c['payload_offset']; vals=[u32(data,po+i*4) for i in range(8)]
        numEnt,numPoly,numActor,defRef,hScene,hEnt,hPoly,hActor=vals
        add(hScene,'scene.hSceneScript')
        # entrances: 8 bytes: number, script
        if hEnt:
            fi,off=handle_to_file_offset(hEnt)
            if fi==idx_by_name.get(path.name.lower(),-1):
                for i in range(min(numEnt,1000)):
                    if off+i*8+8<=len(data):
                        entno=u32(data,off+i*8); sh=u32(data,off+i*8+4); add(sh,'entrance.script',{'entrance':entno})
        # actors: 12 bytes masking, actor_id, script
        if hActor:
            fi,off=handle_to_file_offset(hActor)
            if fi==idx_by_name.get(path.name.lower(),-1):
                for i in range(min(numActor,5000)):
                    if off+i*12+12<=len(data):
                        masking=i32(data,off+i*12); aid=u32(data,off+i*12+4); sh=u32(data,off+i*12+8); add(sh,'actor.script',{'actor_id':aid,'masking':masking})
    # OBJECTS registry scripts and icon film refs
    ctot=cm.get(CHUNK_TOTAL_OBJECTS); cob=cm.get(CHUNK_OBJECTS)
    if ctot and cob and ctot['payload_size']>=4:
        total=u32(data,ctot['payload_offset'])
        off=cob['payload_offset']
        for i in range(min(total, cob['payload_size']//16)):
            o=off+i*16; obj_id=u32(data,o); icon=u32(data,o+4); sh=u32(data,o+8); attr=u32(data,o+12)
            add(sh,'inventory.script',{'object_id':obj_id})
            if icon: films.append({'handle':icon,'source':'inventory.iconFilm','object_id':obj_id})
    # For all film handles in this file, collect reel scripts.
    for f in list(films):
        h=f['handle']; fi,off=handle_to_file_offset(h)
        if fi!=idx_by_name.get(path.name.lower(),-1) or off+8>len(data): continue
        try:
            frate=i32(data,off); num=i32(data,off+4)
            if 0<num<1000:
                for r in range(num):
                    ro=off+8+r*8
                    if ro+8<=len(data):
                        mobj=u32(data,ro); script=u32(data,ro+4); add(script,'film.reel.ani_script',{'film_handle':h,'reel':r})
        except Exception: pass
    # de-dupe
    seen=set(); out=[]
    for s in scripts:
        k=(s['handle'],s['source'],tuple(sorted((k,v) for k,v in s.items() if k not in ('handle','source'))))
        if k not in seen: seen.add(k); out.append(s)
    return out, films

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('directory', nargs='?', default='/mnt/data'); ap.add_argument('--outdir', default='/mnt/data')
    args=ap.parse_args(); d=Path(args.directory); out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    idx=read_index(d/'INDEX') if (d/'INDEX').exists() else []
    idx_by_name={r['filename'].lower():r['index'] for r in idx}
    all_files=sorted(d.glob('*.SCN'))
    script_sources=[]; disasm_index=[]; film_refs=[]; libcall_rows=[]; branch_rows=[]
    per_file=[]
    for p in all_files:
        data=p.read_bytes(); cm=chunk_map(data); pcode_payload,pcode_start=safe_get_chunk_payload(data,CHUNK_PCODE)
        scripts, films=collect_script_handles(p, idx_by_name)
        per_file.append({'file':p.name,'index':idx_by_name.get(p.name.lower()),'scripts_found':len(scripts),'icon_films':len(films),'pcode_payload_size':len(pcode_payload),'chunks':[f"0x{c['id']:08X}" for c in walk_chunks(data)]})
        for s in scripts:
            h=s['handle']; fi,off=handle_to_file_offset(h)
            if fi!=idx_by_name.get(p.name.lower(),-1) or off>=len(data):
                continue
            res=disassemble(data,off, max_ins=800)
            script_sources.append({**s,'file':p.name,'start_offset':off,'instruction_count':len(res['instructions']),'film_ref_count':len(res['films']),'libcall_count':len(res['libcalls']),'branch_count':len(res['branches'])})
            for ins in res['instructions'][:250]:
                disasm_index.append({'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],'ip':ins['ip'],'opcode':ins['name'],'operand':ins['operand'],'raw_opcode':ins['raw_opcode']})
            for fr in res['films']:
                film_refs.append({'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],**fr,'film_handle_hex':fmt_handle(fr['film_handle'])})
            for lc in res['libcalls']:
                top=[]
                for a in lc['near_stack']:
                    val=a.get('value')
                    top.append(f"{a.get('kind')}:{fmt_handle(val) if isinstance(val,int) and val>0x100000 else val}")
                libcall_rows.append({'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],'ip':lc['script_ip'],'libcall':lc['libcall'],'libcall_name':lc['libcall_name'],'near_stack':' | '.join(top[-8:])})
            for br in res['branches']:
                branch_rows.append({'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],**br})
    # summaries
    cnt_lib=collections.Counter(r['libcall_name'] for r in libcall_rows)
    cnt_source=collections.Counter(r['source'] for r in script_sources)
    cnt_films_by_file=collections.Counter(r['file'] for r in film_refs)
    report={'files':per_file,'script_source_count':dict(cnt_source),'total_scripts_scanned':len(script_sources),'total_film_refs':len(film_refs),'total_libcalls':len(libcall_rows),'top_libcalls':cnt_lib.most_common(40),'film_refs_by_file':dict(cnt_films_by_file)}
    def write_csv(name, rows, fields=None):
        if not fields:
            keys=[]
            for r in rows:
                for k in r.keys():
                    if k not in keys: keys.append(k)
            fields=keys
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    (out/'tinsel1_pcode_report.json').write_text(json.dumps(report,indent=2))
    write_csv(Path('tinsel1_script_sources.csv'), script_sources)
    write_csv(Path('tinsel1_pcode_film_refs.csv'), film_refs)
    write_csv(Path('tinsel1_pcode_libcalls.csv'), libcall_rows)
    write_csv(Path('tinsel1_pcode_disasm_sample.csv'), disasm_index)
    md=[]
    md.append('# Tinsel 1 PCODE Scanner Findings\n')
    md.append(f"Files scanned: {len(all_files)}\n\nScripts scanned: {len(script_sources)}\n\nFilm refs: {len(film_refs)}\n\nLibrary calls: {len(libcall_rows)}\n")
    md.append('\n## Script sources\n')
    for k,v in cnt_source.most_common(): md.append(f'- {k}: {v}\n')
    md.append('\n## Top library calls\n')
    for k,v in cnt_lib.most_common(30): md.append(f'- {k}: {v}\n')
    md.append('\n## Files with most PCODE film references\n')
    for k,v in cnt_films_by_file.most_common(30): md.append(f'- {k}: {v}\n')
    md.append('\n## Notes\n')
    md.append('- This is a static scanner, not a PCODE emulator. Branches are not followed as control flow; disassembly is linear from known script handles.\n')
    md.append('- OP_FILM and OP_CDFILM references are extracted exactly as typed handle operands.\n')
    md.append('- LIBCALL names use ScummVM DW1_CODES ordering.\n')
    (out/'tinsel1_pcode_findings.md').write_text(''.join(md))
    print(json.dumps(report,indent=2)[:4000])
if __name__=='__main__': main()
