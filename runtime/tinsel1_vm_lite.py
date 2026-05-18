#!/usr/bin/env python3
"""Discworld / Tinsel 1 VM-lite PCODE tracer.

This is not a gameplay VM. It is a bounded, trace-oriented interpreter for the
Discworld 1/Tinsel PCODE bytecode used in SCN resources. It implements opcode
fetch, operand-size decoding, symbolic stack effects, branch exploration, film
handle tracing, and OP_LIBCALL tracing.

GPL-compatible; derived from ScummVM opcode semantics already used by the
project's extractor work and validated against uploaded resources/DWB.EXE traces.
"""
from __future__ import annotations
import argparse, csv, json, struct, collections, zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

OP_NAMES = {
0:'HALT',1:'IMM',2:'ZERO',3:'ONE',4:'MINUSONE',5:'STR',6:'FILM',7:'FONT',8:'PAL',9:'LOAD',10:'GLOAD',11:'STORE',12:'GSTORE',13:'CALL',14:'LIBCALL',15:'RET',16:'ALLOC',17:'JUMP',18:'JMPFALSE',19:'JMPTRUE',20:'EQUAL',21:'LESS',22:'LEQUAL',23:'NEQUAL',24:'GEQUAL',25:'GREAT',26:'PLUS',27:'MINUS',28:'LOR',29:'MULT',30:'DIV',31:'MOD',32:'AND',33:'OR',34:'EOR',35:'LAND',36:'NOT',37:'COMP',38:'NEG',39:'DUP',40:'ESCON',41:'ESCOFF',42:'CIMM',43:'CDFILM',63:'NOOP'
}
OPMASK=0x3F; OPSIZE8=0x40; OPSIZE16=0x80
HAS_OPERAND = {1,5,6,7,8,9,10,11,12,13,14,16,17,18,19,42,43}
HANDLE_SHIFT=23; OFFSET_MASK=0x007FFFFF
CHUNK_SCENE=0x3334000E; CHUNK_ENTRANCE=0x3334000B; CHUNK_ACTORS=0x3334000D; CHUNK_TOTAL_OBJECTS=0x33340011; CHUNK_OBJECTS=0x33340012
DW1_CODES = """ACTORATTR ACTORDIRECTION ACTORREF ACTORSCALE ACTORXPOS ACTORYPOS ADDTOPIC ADDINV1 ADDINV2 ADDOPENINV AUXSCALE BACKGROUND CAMERA CLOSEINVENTORY CONTROL CONVERSATION CONVTOPIC CURSORXPOS CURSORYPOS DECCONVW DECCURSOR DECINV1 DECINV2 DECINVW DECLEAD DECTAGFONT DECTALKFONT DELICON DELINV EFFECTACTOR ESCAPE EVENT GETINVLIMIT HELDOBJECT HIDEACTOR ININVENTORY INVDEPICT INVENTORY KILLACTOR KILLBLOCK KILLEXIT KILLTAG SCREENXPOS MOVECURSOR NEWSCENE NOSCROLL OBJECTHELD OFFSET PAUSE PLAY PLAYMIDI PLAYSAMPLE PREPARESCENE PRINT PRINTOBJ PRINTTAG RANDOM RESTORESCENE SAVESCENE SCALINGREELS SCANICON SCROLL SETACTOR SETBLOCK SETEXIT SETINVLIMIT SETPALETTE SETTAG SETTIMER SHOWPOS SHOWSTRING SPLAY STAND STANDTAG STOPWALK SWALK TAGACTOR TALK TALKATTR TIMER SCREENYPOS TOPPLAY TOPWINDOW UNTAGACTOR VIBRATE WAITKEY WAITTIME WALK WALKED WALKINGACTOR WALKPOLY WALKTAG WHICHINVENTORY ACTORSON CUTSCENE HOOKSCENE IDLETIME RESETIDLETIME TALKAT UNHOOKSCENE WAITFRAME DECCSTRINGS STOPMIDI STOPSAMPLE TALKATS DECFLAGS FADEMIDI CLEARHOOKSCENE SETINVSIZE INWHICHINV NOBLOCKING SAMPLEPLAYING TRYPLAYSAMPLE ENABLEMENU RESTARTGAME QUITGAME FRAMEGRAB PLAYRTF CDPLAY CDLOAD HASRESTARTED RESTORE_CUT RUNMODE SUBTITLES SETLANGUAGE HIGHEST_LIBCODE""".split()
LIBCALL_NAMES={i:name for i,name in enumerate(DW1_CODES)}
FILM_RELATED_LIBCALLS={'PLAY','TOPPLAY','SPLAY','STAND','STANDTAG','SWALK','WALK','WALKTAG','BACKGROUND','EFFECTACTOR','PLAYRTF'}

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i32(b,o): return struct.unpack_from('<i',b,o)[0]
def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def i16(b,o): return struct.unpack_from('<h',b,o)[0]
def s8(x): return struct.unpack('b', bytes([x]))[0]
def fmt_handle(h:int)->str: return f"0x{h&0xffffffff:08X}"
def split_handle(h:int)->Tuple[int,int]: return ((h>>HANDLE_SHIFT)&0x1ff, h&OFFSET_MASK)

def walk_chunks(data: bytes):
    out=[]; off=0; seen=set()
    while 0 <= off < len(data) and off not in seen and off+8 <= len(data):
        seen.add(off); cid=u32(data,off); nxt=u32(data,off+4)
        end=len(data) if nxt==0 else nxt
        out.append({'offset':off,'id':cid,'next':nxt,'payload_offset':off+8,'payload_size':max(0,end-(off+8))})
        if nxt==0: break
        off=nxt
    return out

def read_index(path: Path):
    data=path.read_bytes(); recs=[]
    for n,o in enumerate(range(0,len(data)//20*20,20)):
        name=data[o:o+12].split(b'\0',1)[0].decode('ascii','replace')
        if name:
            recs.append({'index':n,'filename':name,'base':n<<HANDLE_SHIFT,'size_flags':u32(data,o+12)})
    return recs

def add_script(out, h, source, file_index, extra=None):
    if h and split_handle(h)[0] == file_index:
        d={'handle':h,'source':source};
        if extra: d.update(extra)
        out.append(d)

def collect_script_handles(path: Path, idx_by_name: Dict[str,int]):
    data=path.read_bytes(); cm={c['id']:c for c in walk_chunks(data)}
    file_index=idx_by_name.get(path.name.lower(),-1)
    scripts=[]
    c=cm.get(CHUNK_SCENE)
    if c and c['payload_size']>=32:
        po=c['payload_offset']; vals=[u32(data,po+i*4) for i in range(8)]
        numEnt,numPoly,numActor,defRef,hScene,hEnt,hPoly,hActor=vals
        add_script(scripts,hScene,'scene.hSceneScript',file_index)
        # Entrances: 8-byte records.
        fi,off=split_handle(hEnt)
        if fi==file_index:
            for i in range(min(numEnt,2000)):
                if off+i*8+8<=len(data):
                    entno=u32(data,off+i*8); sh=u32(data,off+i*8+4)
                    add_script(scripts,sh,'entrance.script',file_index,{'entrance':entno})
        # Actors: 12-byte records.
        fi,off=split_handle(hActor)
        if fi==file_index:
            for i in range(min(numActor,5000)):
                if off+i*12+12<=len(data):
                    masking=i32(data,off+i*12); aid=u32(data,off+i*12+4); sh=u32(data,off+i*12+8)
                    add_script(scripts,sh,'actor.script',file_index,{'actor_id':aid,'masking':masking})
    # Inventory object registry.
    ctot=cm.get(CHUNK_TOTAL_OBJECTS); cob=cm.get(CHUNK_OBJECTS)
    if ctot and cob and ctot['payload_size']>=4:
        total=u32(data,ctot['payload_offset']); off=cob['payload_offset']
        for i in range(min(total,cob['payload_size']//16)):
            o=off+i*16; obj_id=u32(data,o); sh=u32(data,o+8)
            add_script(scripts,sh,'inventory.script',file_index,{'object_id':obj_id})
    # De-dupe.
    seen=set(); dedup=[]
    for s in scripts:
        k=(s['handle'],s['source'],tuple(sorted((k,v) for k,v in s.items() if k not in ('handle','source'))))
        if k not in seen: seen.add(k); dedup.append(s)
    return dedup

@dataclass(frozen=True)
class Sym:
    kind: str
    value: Any = None
    origin: str = ''
    def text(self):
        if isinstance(self.value,int) and (self.kind in {'film','cdfilm','str','pal','font'} or self.value>0xffff):
            return f"{self.kind}:{fmt_handle(self.value)}"
        return f"{self.kind}:{self.value}"

@dataclass
class State:
    ip: int
    stack: List[Sym] = field(default_factory=list)
    locals: Dict[int,Sym] = field(default_factory=dict)
    globals_seen: Dict[int,Sym] = field(default_factory=dict)
    path: str = 'root'
    steps: int = 0

def read_operand(data:bytes, ip:int, raw:int):
    if raw & OPSIZE8:
        if ip>=len(data): raise EOFError
        return s8(data[ip]), ip+1, 1
    if raw & OPSIZE16:
        if ip+2>len(data): raise EOFError
        return i16(data,ip), ip+2, 2
    if ip+4>len(data): raise EOFError
    return i32(data,ip), ip+4, 4

def pop(st:State)->Sym:
    return st.stack.pop() if st.stack else Sym('underflow',None)

def push(st:State, v:Sym):
    st.stack.append(v)
    if len(st.stack)>128:
        st.stack=st.stack[-128:]

def binop(st:State, name:str):
    b=pop(st); a=pop(st)
    if a.kind=='imm' and b.kind=='imm' and isinstance(a.value,int) and isinstance(b.value,int):
        try:
            if name=='PLUS': v=a.value+b.value
            elif name=='MINUS': v=a.value-b.value
            elif name=='MULT': v=a.value*b.value
            elif name=='DIV': v=0 if b.value==0 else int(a.value/b.value)
            elif name=='MOD': v=0 if b.value==0 else a.value%b.value
            elif name=='AND': v=a.value & b.value
            elif name=='OR': v=a.value | b.value
            elif name=='EOR': v=a.value ^ b.value
            elif name=='LOR': v=int(bool(a.value) or bool(b.value))
            elif name=='LAND': v=int(bool(a.value) and bool(b.value))
            elif name=='EQUAL': v=int(a.value==b.value)
            elif name=='NEQUAL': v=int(a.value!=b.value)
            elif name=='LESS': v=int(a.value<b.value)
            elif name=='LEQUAL': v=int(a.value<=b.value)
            elif name=='GREAT': v=int(a.value>b.value)
            elif name=='GEQUAL': v=int(a.value>=b.value)
            else: v=None
            push(st,Sym('imm',v,f'{name}({a.text()},{b.text()})')); return
        except Exception: pass
    push(st,Sym('expr',f'{name}({a.text()},{b.text()})'))

def unop(st:State, name:str):
    a=pop(st)
    if a.kind=='imm' and isinstance(a.value,int):
        if name=='NOT': push(st,Sym('imm',int(not a.value),name)); return
        if name=='COMP': push(st,Sym('imm',~a.value,name)); return
        if name=='NEG': push(st,Sym('imm',-a.value,name)); return
    push(st,Sym('expr',f'{name}({a.text()})'))

def branch_targets(data_len:int, after_operand_ip:int, operand:int):
    # Discworld PCODE branch operands are treated conservatively. Absolute targets
    # are preferred when valid; relative fallbacks are included only when distinct.
    out=[]
    if isinstance(operand,int):
        if 0 <= operand < data_len: out.append(('abs',operand))
        rel=after_operand_ip+operand
        if 0 <= rel < data_len and rel not in [x[1] for x in out]: out.append(('rel_after',rel))
    return out[:2]

def execute_script(data:bytes, start:int, *, max_steps:int=2000, max_paths:int=64):
    events=[]; final_states=[]; q=[State(ip=start)]; seen=set(); paths_started=1
    while q and len(final_states)<max_paths:
        st=q.pop(0)
        while st.steps < max_steps:
            key=(st.ip, tuple((v.kind, str(v.value)) for v in st.stack[-8:]), tuple(sorted((k,str(v.value)) for k,v in st.locals.items()))[:8])
            if key in seen:
                events.append({'path':st.path,'ip':st.ip,'event':'loop_cutoff','stack_depth':len(st.stack)})
                break
            seen.add(key)
            if not (0 <= st.ip < len(data)):
                events.append({'path':st.path,'ip':st.ip,'event':'ip_out_of_range'}); break
            op_ip=st.ip; raw=data[st.ip]; st.ip+=1; op=raw&OPMASK; name=OP_NAMES.get(op,f'OP_{op}')
            operand=None; operand_size=0
            if op in HAS_OPERAND:
                try: operand, st.ip, operand_size=read_operand(data,st.ip,raw)
                except EOFError:
                    events.append({'path':st.path,'ip':op_ip,'event':'truncated_operand','opcode':name}); break
            st.steps+=1
            if op==0:
                events.append({'path':st.path,'ip':op_ip,'event':'halt','opcode':name,'stack_depth':len(st.stack)}); break
            elif op==15:
                events.append({'path':st.path,'ip':op_ip,'event':'ret','opcode':name,'stack_depth':len(st.stack)}); break
            elif op==63:
                pass
            elif op in (1,42): push(st,Sym('imm',operand,f'{name}@{op_ip}'))
            elif op==2: push(st,Sym('imm',0,f'{name}@{op_ip}'))
            elif op==3: push(st,Sym('imm',1,f'{name}@{op_ip}'))
            elif op==4: push(st,Sym('imm',-1,f'{name}@{op_ip}'))
            elif op==5: push(st,Sym('str',operand,f'{name}@{op_ip}'))
            elif op==6:
                push(st,Sym('film',operand,f'{name}@{op_ip}'))
                events.append({'path':st.path,'ip':op_ip,'event':'film_push','opcode':name,'film_handle':fmt_handle(operand),'file_index':split_handle(operand)[0],'offset':split_handle(operand)[1]})
            elif op==43:
                push(st,Sym('cdfilm',operand,f'{name}@{op_ip}'))
                events.append({'path':st.path,'ip':op_ip,'event':'film_push','opcode':name,'film_handle':fmt_handle(operand),'file_index':split_handle(operand)[0],'offset':split_handle(operand)[1]})
            elif op==7: push(st,Sym('font',operand,f'{name}@{op_ip}'))
            elif op==8: push(st,Sym('pal',operand,f'{name}@{op_ip}'))
            elif op==9:
                push(st,st.locals.get(operand,Sym('local',operand,f'LOAD@{op_ip}')))
            elif op==10:
                push(st,Sym('global',operand,f'GLOAD@{op_ip}'))
            elif op==11:
                st.locals[operand]=pop(st)
            elif op==12:
                st.globals_seen[operand]=pop(st)
                events.append({'path':st.path,'ip':op_ip,'event':'global_store','global':operand,'value':st.globals_seen[operand].text()})
            elif op==13:
                events.append({'path':st.path,'ip':op_ip,'event':'call','target':operand,'target_hex':fmt_handle(operand) if isinstance(operand,int) else operand,'stack_top':[v.text() for v in st.stack[-8:]]})
            elif op==14:
                lib=operand; lname=LIBCALL_NAMES.get(lib,f'LIB_{lib}')
                top=[v.text() for v in st.stack[-10:]]
                film_args=[v for v in st.stack[-16:] if v.kind in ('film','cdfilm')]
                events.append({'path':st.path,'ip':op_ip,'event':'libcall','libcall':lib,'libcall_name':lname,'stack_depth':len(st.stack),'stack_top':top,'film_args':[fmt_handle(v.value) for v in film_args], 'film_related': lname in FILM_RELATED_LIBCALLS})
                # Arity is not solved yet. To avoid compounding stack pollution,
                # keep only a bounded recent symbolic stack.
                if len(st.stack)>32: st.stack=st.stack[-16:]
            elif op==16:
                events.append({'path':st.path,'ip':op_ip,'event':'alloc','count':operand})
                # Reserve locals symbolically.
                for i in range(max(0,min(int(operand or 0),64))):
                    st.locals.setdefault(i,Sym('local_uninit',i))
            elif op==17:
                tgts=branch_targets(len(data),st.ip,operand)
                events.append({'path':st.path,'ip':op_ip,'event':'jump','operand':operand,'targets':[{'mode':m,'ip':t} for m,t in tgts]})
                if tgts:
                    st.ip=tgts[0][1]
                    continue
                break
            elif op in (18,19):
                cond=pop(st); tgts=branch_targets(len(data),st.ip,operand)
                events.append({'path':st.path,'ip':op_ip,'event':'conditional_jump','opcode':name,'operand':operand,'condition':cond.text(),'targets':[{'mode':m,'ip':t} for m,t in tgts],'fallthrough':st.ip})
                # Constant-fold when possible, otherwise fork taken + fallthrough.
                take_unknown=True
                if cond.kind=='imm' and isinstance(cond.value,int):
                    take=(cond.value==0 and op==18) or (cond.value!=0 and op==19)
                    take_unknown=False
                    if take and tgts:
                        st.ip=tgts[0][1]; continue
                    else:
                        continue
                if tgts and paths_started<max_paths:
                    ns=State(ip=tgts[0][1],stack=list(st.stack),locals=dict(st.locals),globals_seen=dict(st.globals_seen),path=f'{st.path}.br{paths_started}',steps=st.steps)
                    q.append(ns); paths_started+=1
                # Fallthrough continues on current path.
            elif op in {20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35}:
                binop(st,name)
            elif op in {36,37,38}:
                unop(st,name)
            elif op==39:
                push(st, st.stack[-1] if st.stack else Sym('underflow',None))
            elif op in (40,41):
                events.append({'path':st.path,'ip':op_ip,'event':'escape_toggle','opcode':name})
            else:
                events.append({'path':st.path,'ip':op_ip,'event':'unsupported_opcode','opcode':name,'raw_opcode':raw,'operand':operand})
        final_states.append({'path':st.path,'ip':st.ip,'steps':st.steps,'stack_depth':len(st.stack),'stack_top':[v.text() for v in st.stack[-8:]],'locals_count':len(st.locals)})
    return {'events':events,'final_states':final_states,'paths_started':paths_started}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('directory',nargs='?',default='/mnt/data')
    ap.add_argument('--outdir',default='/mnt/data/vm_lite_trace')
    ap.add_argument('--max-scripts-per-file',type=int,default=60)
    ap.add_argument('--max-steps',type=int,default=1200)
    ap.add_argument('--max-paths',type=int,default=32)
    args=ap.parse_args()
    root=Path(args.directory); out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    idx=read_index(root/'INDEX')
    idx_by_name={r['filename'].lower():r['index'] for r in idx}
    scns=sorted(root.glob('*.SCN'))
    all_events=[]; script_rows=[]; scene_summaries=[]
    selected=[]
    # Prioritize high-value scenes while still including all files in summary.
    priority={'CLIMAX.SCN','FINALE.SCN','CITYGATE.SCN','PALENT.SCN','CUTBARN.SCN','PASTINNR.SCN','DUNNYMAN.SCN','CUTTHRON.SCN','BAR.SCN','PASTHIDE.SCN','OBJECTS.SCN','DW.SCN'}
    ordered=sorted(scns,key=lambda p:(p.name not in priority,p.name))
    for p in ordered:
        scripts=collect_script_handles(p,idx_by_name)
        scene_summaries.append({'file':p.name,'script_handles':len(scripts),'index':idx_by_name.get(p.name.lower())})
        if scripts:
            selected.append((p,scripts[:args.max_scripts_per_file]))
    for p,scripts in selected:
        data=p.read_bytes()
        for s in scripts:
            h=s['handle']; fi,off=split_handle(h)
            if off>=len(data): continue
            tr=execute_script(data,off,max_steps=args.max_steps,max_paths=args.max_paths)
            evs=tr['events']
            counts=collections.Counter(e['event'] for e in evs)
            libcounts=collections.Counter(e.get('libcall_name') for e in evs if e.get('event')=='libcall')
            film_sched=[e for e in evs if e.get('event')=='libcall' and e.get('film_related') and e.get('film_args')]
            row={'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],'start_offset':off,'events':len(evs),'paths_started':tr['paths_started'],'film_pushes':counts.get('film_push',0),'libcalls':counts.get('libcall',0),'branches':counts.get('conditional_jump',0)+counts.get('jump',0),'film_related_libcalls_with_film_args':len(film_sched),'top_libcalls':';'.join(f'{k}:{v}' for k,v in libcounts.most_common(8) if k)}
            for k,v in s.items():
                if k not in ('handle','source'): row[k]=v
            script_rows.append(row)
            for e in evs:
                rec={'file':p.name,'script_handle':fmt_handle(h),'source':s['source'],**e}
                # Flatten bulky stack fields for CSV.
                if isinstance(rec.get('stack_top'),list): rec['stack_top']=' | '.join(map(str,rec['stack_top']))
                if isinstance(rec.get('film_args'),list): rec['film_args']=' | '.join(map(str,rec['film_args']))
                if isinstance(rec.get('targets'),list): rec['targets']=json.dumps(rec['targets'])
                all_events.append(rec)
    # Focus tables.
    lib_events=[e for e in all_events if e.get('event')=='libcall']
    film_events=[e for e in all_events if e.get('event') in ('film_push','libcall') and (e.get('film_handle') or e.get('film_args'))]
    branch_events=[e for e in all_events if e.get('event') in ('jump','conditional_jump')]
    def write_csv(path:Path, rows:List[Dict[str,Any]]):
        keys=[]
        for r in rows:
            for k in r.keys():
                if k not in keys: keys.append(k)
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    write_csv(out/'vm_lite_script_summary.csv',script_rows)
    write_csv(out/'vm_lite_events.csv',all_events)
    write_csv(out/'vm_lite_libcalls.csv',lib_events)
    write_csv(out/'vm_lite_film_events.csv',film_events)
    write_csv(out/'vm_lite_branches.csv',branch_events)
    write_csv(out/'vm_lite_scene_script_counts.csv',scene_summaries)
    lib_counter=collections.Counter(e.get('libcall_name') for e in lib_events)
    file_counter=collections.Counter(e.get('file') for e in film_events)
    report={
        'scope':'bounded symbolic VM-lite trace, not full gameplay emulation',
        'scn_files_seen':len(scns),
        'scripts_executed':len(script_rows),
        'events_total':len(all_events),
        'libcall_events':len(lib_events),
        'film_related_events':len(film_events),
        'branch_events':len(branch_events),
        'scripts_with_film_related_libcalls_with_film_args':sum(1 for r in script_rows if r.get('film_related_libcalls_with_film_args',0)),
        'top_libcalls':lib_counter.most_common(40),
        'top_files_by_film_events':file_counter.most_common(30),
        'limits':{'max_scripts_per_file':args.max_scripts_per_file,'max_steps':args.max_steps,'max_paths':args.max_paths},
        'notes':['JUMP/JMPTRUE/JMPFALSE target interpretation is conservative: absolute target preferred, relative fallback used only as alternate branch candidate.','OP_LIBCALL arity is not solved; stack contents are logged around the call instead of consumed.','Unsupported/unknown runtime side effects are logged rather than guessed.']
    }
    (out/'vm_lite_report.json').write_text(json.dumps(report,indent=2))
    md=['# Tinsel 1 VM-lite Trace Findings\n\n']
    md.append(f"Scripts executed: {len(script_rows)}\n\nEvents: {len(all_events)}\n\nLibcalls: {len(lib_events)}\n\nFilm-related events: {len(film_events)}\n\nBranches: {len(branch_events)}\n\n")
    md.append('## Top libcalls\n')
    for k,v in lib_counter.most_common(25): md.append(f'- {k}: {v}\n')
    md.append('\n## Top files by film-related events\n')
    for k,v in file_counter.most_common(20): md.append(f'- {k}: {v}\n')
    md.append('\n## Interpretation\n')
    md.append('This is a VM-lite trace: it executes opcode fetch, symbolic stack effects, branches, OP_FILM/OP_CDFILM, and OP_LIBCALL logging. It does not implement complete runtime globals, actor systems, scheduler, or library-call arities yet.\n')
    (out/'vm_lite_findings.md').write_text(''.join(md))
    # Copy script into output dir.
    import shutil
    shutil.copy2(Path(__file__), out/'tinsel1_vm_lite.py')
    zip_path=Path('/mnt/data/tinsel1_vm_lite_outputs.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for fp in out.rglob('*'):
            if fp.is_file(): z.write(fp, fp.relative_to(out.parent))
    # Also place key outputs at /mnt/data.
    for name in ['vm_lite_report.json','vm_lite_findings.md','vm_lite_script_summary.csv','vm_lite_libcalls.csv','vm_lite_film_events.csv','vm_lite_branches.csv']:
        (Path('/mnt/data')/name).write_bytes((out/name).read_bytes())
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
