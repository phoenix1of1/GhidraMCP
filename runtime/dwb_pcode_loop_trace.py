#!/usr/bin/env python3
"""Locate Discworld PC DWB.EXE PCODE interpreter loop and OP_LIBCALL path.

This script assumes /mnt/data/dwb_le_loader.py is available. It reconstructs the
LE memory image, validates byte-pattern anchors, finds callers, and emits a
small evidence report. Addresses are reconstructed LE virtual addresses.
"""
from pathlib import Path
import json, struct, subprocess, zipfile, sys

ROOT = Path('/mnt/data')
EXE = ROOT/'DWB.EXE'
LOADER = ROOT/'dwb_le_loader.py'

sys.path.insert(0, str(ROOT))
from dwb_le_loader import parse_le

BASE = 0x10000
OUTDIR = ROOT/'dwb_pcode_loop_trace'
OUTDIR.mkdir(exist_ok=True)

def u32(b,o): return struct.unpack_from('<I', b, o)[0]
def va_to_off(va): return va - BASE
def hexbytes(img, va, n): return img[va_to_off(va):va_to_off(va)+n].hex(' ')

def find_rel32(img, target, opcode=0xE8):
    out=[]
    for i in range(0, len(img)-5):
        if img[i] == opcode:
            rel = struct.unpack_from('<i', img, i+1)[0]
            va = BASE + i
            tgt = (va + 5 + rel) & 0xffffffff
            if tgt == target:
                out.append(va)
    return out

def objdump_snip(img_path, start, stop, out_path):
    cmd = [
        'objdump','-D','-b','binary','-m','i386','-M','intel',
        f'--adjust-vma=0x{BASE:x}', str(img_path),
        f'--start-address=0x{start:x}', f'--stop-address=0x{stop:x}'
    ]
    txt = subprocess.check_output(cmd, text=True, errors='replace')
    out_path.write_text(txt)
    return txt

# Load relocated image
d, le, H, objs, pm, data_start, minb, maxb, img, page_infos, relocs, errors = parse_le(EXE)
img_path = OUTDIR/'dwb_le_relocated_image.bin'
img_path.write_bytes(img)

anchors = {
    'scn_handle_resolver': 0x24FEC,
    'script_attach': 0x32AB8,  # actual code starts at 32AB8; 32AB7 is a padding 00 before prologue in linear disasm
    'libcall_dispatcher': 0x32F54,
    'pcode_interpreter': 0x33B90,
    'pcode_fetch': 0x33BB3,
    'pcode_loop_continue': 0x33C34,
    'libcall_table_A_raw': 0x32D80,
    'libcall_table_B_effective': 0x35638,
}

# Validate key byte evidence
checks = [
    {
        'name':'pcode_interpreter_prologue',
        'va':0x33B90,
        'expected':'53 51 56 57 55 83 ec 10',
        'meaning':'function prologue for bytecode interpreter; saves regs, allocates locals',
    },
    {
        'name':'script_code_pointer_fetch',
        'va':0x33BC2,
        'expected':'8b 56 0c 8a 14 02',
        'meaning':'loads context+0x0C code pointer, then fetches opcode byte at code_ptr + ip',
    },
    {
        'name':'ip_increment_before_dispatch',
        'va':0x33BB3,
        'expected':'8b 86 28 02 00 00 8d 50 01 89 96 28 02 00 00',
        'meaning':'loads instruction pointer/context+0x228, increments it before opcode dispatch',
    },
    {
        'name':'loop_termination_test',
        'va':0x33C34,
        'expected':'83 be 2c 02 00 00 00 0f 84 72 ff ff ff',
        'meaning':'tests context+0x22C stop flag and loops back to opcode fetch if clear',
    },
    {
        'name':'libcall_dispatcher_prologue',
        'va':0x32F54,
        'expected':'56 57 55 83 ec 0c 89 d6 89 0c 24 89 da 89 c1',
        'meaning':'library-call dispatcher setup; receives libcall index in EAX and stack/context registers',
    },
    {
        'name':'libcall_bounds_and_indirect_jump',
        'va':0x32F82,
        'expected':'83 f9 74 0f 87 0e fc ff ff 2e ff a3 38 56 02 00',
        'meaning':'bounds-checks library routine index <= 0x74, then jumps through 117-entry table',
    },
    {
        'name':'script_attach_chunk_pcode',
        'va':0x32ABC,
        'expected':'80 78 04 02 75 0e ba 0a 00 34 33',
        'meaning':'script attach path: type==2 resolves CHUNK_PCODE 0x3334000A',
    },
]
for c in checks:
    b = bytes.fromhex(c['expected'])
    actual = img[va_to_off(c['va']):va_to_off(c['va'])+len(b)]
    c['actual'] = actual.hex(' ')
    c['matched'] = actual == b

callers = {
    'pcode_interpreter': [hex(x) for x in find_rel32(img, anchors['pcode_interpreter'], 0xE8)],
    'libcall_dispatcher_exact': [hex(x) for x in find_rel32(img, anchors['libcall_dispatcher'], 0xE8)],
    'libcall_dispatcher_minus0': [hex(x) for x in find_rel32(img, 0x32F54, 0xE8)],
    'script_attach': [hex(x) for x in find_rel32(img, anchors['script_attach'], 0xE8)],
}

# Identify direct call sites to libcall dispatcher and classify immediate operand size from adjacent code.
libcall_cases = [
    {
        'call_va':0x34162,
        'case_start':0x34107,
        'operand':'32-bit signed immediate library-call number',
        'evidence':'reads four bytes from code_ptr+ip, assembles little-endian dword into EAX, calls 0x32F54, then adds 4 to ip',
    },
    {
        'call_va':0x341A1,
        'case_start':0x34184,
        'operand':'8-bit signed immediate library-call number',
        'evidence':'movsx eax, byte [code_ptr+ip], calls 0x32F54, adds return delta to stack top, then increments ip by 1',
    },
    {
        'call_va':0x341F8,
        'case_start':0x341CD,
        'operand':'16-bit signed immediate library-call number',
        'evidence':'reads two bytes from code_ptr+ip, sign-extends AX into EAX, calls 0x32F54, then adds 2 to ip',
    },
]
for lc in libcall_cases:
    lc['call_bytes'] = hexbytes(img, lc['call_va'], 5)

# Dump a few disassembly ranges for human review
snips = {
    'pcode_interpreter_main': (0x33B90, 0x33C50),
    'pcode_libcall_cases': (0x34100, 0x34220),
    'libcall_dispatcher': (0x32F54, 0x33020),
    'script_attach_and_context_alloc': (0x32A9C, 0x32C10),
}
for name,(start,stop) in snips.items():
    objdump_snip(img_path, start, stop, OUTDIR/f'{name}.asm')

# Read first few libcall table entries, interpreting displacement as linear in object1 (table B effective = 0x35638)
def read_table(va, n=117):
    vals=[]
    off=va_to_off(va)
    for i in range(n):
        vals.append(u32(img, off+i*4))
    return vals

table_A = read_table(0x32D80)
table_B = read_table(0x35638)
summary = {
    'input': str(EXE),
    'le_offset': le,
    'entry_va': objs[H['csobj']-1]['base'] + H['eip'],
    'objects': objs,
    'relocation_count': len(relocs),
    'relocation_errors': errors,
    'anchors': {k:hex(v) for k,v in anchors.items()},
    'checks': checks,
    'callers': callers,
    'libcall_cases': libcall_cases,
    'library_table': {
        'table_A_va': '0x32D80',
        'table_B_effective_va': '0x35638',
        'entry_count': 117,
        'first_8_A': [hex(x) for x in table_A[:8]],
        'first_8_B': [hex(x) for x in table_B[:8]],
        'max_index_checked': '0x74',
    },
    'context_offsets': {
        '+0x0C':'PCODE/code pointer, initialized by script attach and read by interpreter fetch',
        '+0x20':'start of 32-bit operand stack / local frame area',
        '+0x220':'stack top index',
        '+0x224':'base/frame index',
        '+0x228':'instruction pointer offset into code_ptr',
        '+0x22C':'stop/yield flag checked by interpreter loop',
        '+0x230': 'runtime field used by some wait/call paths',
        '+0x234': 'runtime field used by some wait/call paths',
    }
}
(OUTDIR/'dwb_pcode_loop_trace_report.json').write_text(json.dumps(summary, indent=2))

md = []
md.append('# DWB.EXE PCODE Loop Trace Report\n')
md.append('## Result\n')
md.append('The PCODE byte interpreter loop is now located with high confidence at `0x33B90`. The original DW1 library-call dispatcher used by `OP_LIBCALL` is located at `0x32F54`.\n')
md.append('## Main anchors\n')
for k,v in anchors.items(): md.append(f'- `{k}`: `0x{v:X}`')
md.append('\n## Evidence checks\n')
for c in checks:
    md.append(f'- `{c["name"]}` at `0x{c["va"]:X}`: {"MATCH" if c["matched"] else "NO MATCH"}')
    md.append(f'  - {c["meaning"]}')
    md.append(f'  - bytes: `{c["actual"]}`')
md.append('\n## PCODE interpreter structure\n')
md.append('- `0x33BB3` loads `context+0x228`, increments it, then `0x33BC2` fetches one opcode byte from `*(context+0x0C) + old_ip`.')
md.append('- The dispatch tree compares the raw opcode byte and routes to handlers for literal pushes, jumps, arithmetic, globals/locals, and library calls.')
md.append('- `0x33C34` checks `context+0x22C`; if clear it jumps back to `0x33BB3`, forming the interpreter loop.')
md.append('\n## OP_LIBCALL path\n')
md.append('- `0x34162`: 32-bit immediate library-call number -> `call 0x32F54`.')
md.append('- `0x341A1`: 8-bit immediate library-call number -> `call 0x32F54`.')
md.append('- `0x341F8`: 16-bit immediate library-call number -> `call 0x32F54`.')
md.append('- `0x32F54` bounds-checks the library routine index against `0x74` and dispatches through a 117-entry table.')
md.append('\n## Script context offsets inferred from code\n')
for k,v in summary['context_offsets'].items(): md.append(f'- `{k}`: {v}')
md.append('\n## Callers\n')
for k,v in callers.items(): md.append(f'- `{k}`: {", ".join(v) if v else "none"}')
md.append('\n## Generated disassembly snippets\n')
for name in snips: md.append(f'- `{name}.asm`')
(OUTDIR/'dwb_pcode_loop_trace_report.md').write_text('\n'.join(md)+'\n')

zip_path = ROOT/'dwb_pcode_loop_trace_outputs.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in OUTDIR.iterdir():
        if p.is_file():
            z.write(p, p.name)

# Also copy primary report/script to /mnt/data
(ROOT/'dwb_pcode_loop_trace_report.md').write_text((OUTDIR/'dwb_pcode_loop_trace_report.md').read_text())
(ROOT/'dwb_pcode_loop_trace_report.json').write_text((OUTDIR/'dwb_pcode_loop_trace_report.json').read_text())
Path(__file__).chmod(0o755)
print(json.dumps({
    'pcode_interpreter':'0x33B90',
    'libcall_dispatcher':'0x32F54',
    'checks_matched':sum(1 for c in checks if c['matched']),
    'checks_total':len(checks),
    'pcode_interpreter_callers':callers['pcode_interpreter'],
    'zip':str(zip_path),
}, indent=2))
