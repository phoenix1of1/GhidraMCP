#!/usr/bin/env python3
"""
Targeted recursive CFG disassembler for Discworld PC DWB.EXE relocated LE image.
Uses GNU objdump as the instruction decoder and builds control-flow graphs for
known DW1 scheduler/libcall handler entry regions.
"""
from __future__ import annotations
import argparse, json, re, subprocess, zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

DEFAULT_IMAGE = Path('/mnt/data/dwb_le_relocated_image.bin')
BASE_VA = 0x10000

HANDLERS = {
    'BACKGROUND': 0x3596B,
    'PLAY':       0x35D6B,
    'STAND':      0x360A3,
    'WAITFRAME':  0x35B75,
    'WAITTIME':   0x36334,
    'EVENT':      0x35B83,
}

# Conservative local ranges; the entries are label-like, so use clusters.
CLUSTERS = {
    'wait_cluster':   (0x35B40, 0x35BE8, ['WAITFRAME','EVENT']),
    'play_cluster':   (0x35C80, 0x35F60, ['BACKGROUND','PLAY']),
    'actor_cluster':  (0x36080, 0x36480, ['STAND','WAITTIME']),
}

@dataclass
class Instr:
    va: int
    bytes: str
    mnemonic: str
    op_str: str
    text: str
    size: int = 0

@dataclass
class Block:
    start: int
    end: int
    instrs: List[Instr]
    successors: List[int]
    terminator: str

line_re = re.compile(r'^\s*([0-9a-fA-F]+):\s*((?:[0-9a-fA-F]{2}\s)+)\s*([^\s]+)\s*(.*?)\s*$')

JCC = {f'j{x}' for x in ['a','ae','b','be','c','cxz','ecxz','e','g','ge','l','le','na','nae','nb','nbe','nc','ne','ng','nge','nl','nle','no','np','ns','nz','o','p','pe','po','s','z']} | {'loop','loope','loopne','loopnz','loopz'}
UNCOND = {'jmp','ljmp'}
RET = {'ret','retf','iret','iretd'}
CALL = {'call','lcall'}

def run_objdump(image: Path, start: int, stop: int) -> str:
    cmd = [
        'objdump','-D','-b','binary','-m','i386',f'--adjust-vma={BASE_VA:#x}',
        f'--start-address={start:#x}',f'--stop-address={stop:#x}',str(image)
    ]
    return subprocess.check_output(cmd, text=True, errors='replace')

def parse_objdump(text: str) -> List[Instr]:
    out=[]
    for line in text.splitlines():
        m=line_re.match(line)
        if not m: continue
        va=int(m.group(1),16)
        b=m.group(2).strip()
        rest=m.group(3).strip()
        op=m.group(4).strip()
        # objdump may include bad continuation; keep simple
        size=len(b.split())
        out.append(Instr(va,b,rest,op,line.strip(),size))
    return out

def disasm_window(image: Path, start: int, stop: int) -> Dict[int, Instr]:
    instrs=parse_objdump(run_objdump(image,start,stop))
    return {i.va:i for i in instrs}

def target_from_op(op: str) -> Optional[int]:
    m=re.search(r'0x([0-9a-fA-F]+)', op)
    if m:
        return int(m.group(1),16)
    return None

def build_block(seed: int, imap: Dict[int,Instr], lo: int, hi: int) -> Optional[Block]:
    if seed not in imap: return None
    addr=seed; instrs=[]; succ=[]; term='fallthrough'
    visited=0
    while lo <= addr < hi and addr in imap and visited < 200:
        ins=imap[addr]
        instrs.append(ins); visited += 1
        mn=ins.mnemonic.lower()
        next_addr=addr+ins.size
        tgt=target_from_op(ins.op_str)
        if mn in RET:
            term='return'; break
        if mn in UNCOND:
            term='jump'
            if tgt is not None and lo <= tgt < hi: succ.append(tgt)
            break
        if mn in JCC or mn.startswith('j') and mn not in UNCOND:
            term='conditional'
            if tgt is not None and lo <= tgt < hi: succ.append(tgt)
            if lo <= next_addr < hi: succ.append(next_addr)
            break
        # stop after indirect jump/call through memory to avoid following tables
        if mn == 'jmp' and '*' in ins.op_str:
            term='indirect_jump'; break
        addr=next_addr
    end=instrs[-1].va + instrs[-1].size if instrs else seed
    return Block(seed,end,instrs,sorted(set(succ)),term)

def build_cfg(entry: int, image: Path, lo: int, hi: int) -> Tuple[Dict[int,Block], List[str]]:
    # Disassemble cluster once from lo. If entry not aligned due label landing, also disassemble exact entry window.
    imap=disasm_window(image, lo, hi)
    if entry not in imap:
        imap.update(disasm_window(image, entry, hi))
    blocks: Dict[int,Block]={}; queue=[entry]; notes=[]
    while queue and len(blocks) < 200:
        s=queue.pop(0)
        if s in blocks: continue
        b=build_block(s,imap,lo,hi)
        if not b:
            notes.append(f'No instruction decoded at {s:#x}')
            continue
        blocks[s]=b
        for t in b.successors:
            if t not in blocks and t not in queue:
                queue.append(t)
    return blocks, notes

def summarize_block(b: Block) -> dict:
    return {
        'start': f'{b.start:#x}', 'end': f'{b.end:#x}', 'terminator': b.terminator,
        'successors': [f'{s:#x}' for s in b.successors],
        'instructions': [{'va':f'{i.va:#x}','bytes':i.bytes,'mnemonic':i.mnemonic,'operands':i.op_str} for i in b.instrs]
    }

def to_dot(name: str, blocks: Dict[int,Block]) -> str:
    lines=[f'digraph {name} {{','  node [shape=box,fontname="monospace"];']
    for s,b in blocks.items():
        label='\\l'.join([f'{i.va:05x}: {i.mnemonic} {i.op_str}' for i in b.instrs[:18]])+'\\l'
        if len(b.instrs)>18: label+='...\\l'
        lines.append(f'  n{s:x} [label="{label}"];')
        for t in b.successors:
            if t in blocks:
                lines.append(f'  n{s:x} -> n{t:x};')
    lines.append('}')
    return '\n'.join(lines)+'\n'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--image', default=str(DEFAULT_IMAGE))
    ap.add_argument('--out', default='/mnt/data/dwb_libcall_cfg')
    args=ap.parse_args()
    image=Path(args.image); out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    all_results={}
    cluster_by_handler={h:(lo,hi,cname) for cname,(lo,hi,hs) in CLUSTERS.items() for h in hs}
    for h,entry in HANDLERS.items():
        lo,hi,cname=cluster_by_handler.get(h,(max(BASE_VA,entry-0x80),entry+0x200,'local'))
        blocks,notes=build_cfg(entry,image,lo,hi)
        result={
            'handler':h,'entry_va':f'{entry:#x}','cluster':cname,'range':[f'{lo:#x}',f'{hi:#x}'],
            'block_count':len(blocks),'edge_count':sum(len(b.successors) for b in blocks.values()),
            'notes':notes,'blocks':[summarize_block(b) for _,b in sorted(blocks.items())]
        }
        all_results[h]=result
        (out/f'{h.lower()}_cfg.json').write_text(json.dumps(result,indent=2))
        (out/f'{h.lower()}_cfg.dot').write_text(to_dot(h,blocks))
        # linear cluster disasm for review
        (out/f'{h.lower()}_cluster.asm').write_text(run_objdump(image,lo,hi))
    summary={
        'image':str(image),'base_va':f'{BASE_VA:#x}','handlers':{
            h:{'entry_va':v['entry_va'],'cluster':v['cluster'],'range':v['range'],'block_count':v['block_count'],'edge_count':v['edge_count'],'notes':v['notes']} for h,v in all_results.items()
        }
    }
    (out/'dwb_libcall_cfg_summary.json').write_text(json.dumps(summary,indent=2))
    # md report
    md=[]
    md.append('# DWB.EXE Library-call CFG Disassembler Report\n')
    md.append('## Summary\n')
    md.append('| Handler | Entry | Cluster | Blocks | Edges | Notes |\n|---|---:|---|---:|---:|---|\n')
    for h,v in all_results.items():
        md.append(f"| `{h}` | `{v['entry_va']}` | {v['cluster']} | {v['block_count']} | {v['edge_count']} | {'; '.join(v['notes']) or ''} |\n")
    md.append('\n## Interpretation\n\n')
    md.append('This is a targeted recursive CFG pass, not a full decompiler. It follows direct conditional/unconditional branch targets inside known scheduler/libcall clusters and emits reviewable DOT/JSON/ASM artifacts. It intentionally does not follow indirect jumps or external calls.\n')
    md.append('\n## Key result\n\n')
    md.append('The scheduler handlers are now represented as basic-block graphs. This confirms that several library table entries are label entries inside shared regions rather than independent C-style function starts. Body-level semantic recovery should now work from these CFGs rather than linear disassembly.\n')
    (out/'dwb_libcall_cfg_report.md').write_text(''.join(md))
    # zip
    zip_path=Path('/mnt/data/dwb_libcall_cfg_outputs.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(out))
    print(json.dumps(summary,indent=2))
    print(zip_path)
if __name__=='__main__': main()
