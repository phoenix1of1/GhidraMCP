from pathlib import Path
import re

EXE = Path('/mnt/data/DWB.EXE')
b = EXE.read_bytes()

# MZ size calculation
cblp = int.from_bytes(b[2:4], 'little')
cp = int.from_bytes(b[4:6], 'little')
stub_size = (cp - 1) * 512 + cblp if cblp else cp * 512

print(f'DWB.EXE size: {len(b)}')
print(f'MZ-reported first image/stub size: {stub_size} / 0x{stub_size:08X}')
print(f'Bytes at stub end: {b[stub_size:stub_size+16].hex(" ")}')

patterns = {
    'and al,0x3f': b'\x24\x3f',
    'and eax,0x3f': b'\x25\x3f\x00\x00\x00',
    'and ecx,0x3f': b'\x83\xe1\x3f',
    'cmp eax,0x2b': b'\x83\xf8\x2b',
    'cmp ecx,0x2b': b'\x83\xf9\x2b',
    'cmp eax,0x2a': b'\x83\xf8\x2a',
    'cmp ecx,0x2a': b'\x83\xf9\x2a',
    'jmp [eax*4+imm]': b'\xff\x24\x85',
    'jmp [ecx*4+imm]': b'\xff\x24\x8d',
}

for name, pat in patterns.items():
    hits = []
    start = stub_size
    while True:
        i = b.find(pat, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    print(f'{name}: {len(hits)} hits -> {[hex(x) for x in hits[:30]]}')

print('\nKnown anchors:')
print('  animation-script interpreter candidate: 0x489B0, dispatch at 0x489D3')
print('  resource/chunk loader anchor: 0x633DC, chunk compare at 0x63451')
