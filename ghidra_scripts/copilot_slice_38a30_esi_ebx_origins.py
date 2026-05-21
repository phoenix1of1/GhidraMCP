from ghidra.program.model.block import SimpleBlockModel
from ghidra.program.model.lang import OperandType

listing = currentProgram.getListing()
bm = SimpleBlockModel(currentProgram)

WS = toAddr("0x38a13")
WE = toAddr("0x38a40")
ENTRY = toAddr("0x38a13")
ENTRY_FALLBACK = toAddr("0x38a19")
PASSES = 3

CALL_31F8C = "CALL 0x00031f8c"


def clear_range(start, end):
    cur = start
    while cur.compareTo(end) <= 0:
        cu = listing.getCodeUnitAt(cur)
        if cu is not None:
            mn = cu.getMinAddress()
            mx = cu.getMaxAddress()
            listing.clearCodeUnits(mn, mx, False)
            cur = mx.add(1)
        else:
            cur = cur.add(1)


def get_window_ins(start, end):
    out = []
    ins = listing.getInstructionAt(start)
    if ins is None:
        ins = listing.getInstructionAfter(start)
    while ins and ins.getAddress().compareTo(end) <= 0:
        out.append(ins)
        ins = ins.getNext()
    return out


def fp(lines):
    acc = 0
    for line in lines:
        for ch in line:
            acc = ((acc * 131) + ord(ch)) & 0xFFFFFFFF
        acc = ((acc * 131) + ord("\n")) & 0xFFFFFFFF
    return "%08x" % acc


def mentions_reg(ins, op_idx, reg):
    objs = ins.getOpObjects(op_idx)
    for o in objs:
        t = str(o)
        if t == reg or t.endswith(":" + reg):
            return True
    return False


def writes_reg(ins, reg):
    m = ins.getMnemonicString()
    if ins.getNumOperands() == 0:
        return False
    op0_type = ins.getOperandType(0)
    # Only count explicit register destinations, not memory forms like [ESI+off].
    if not OperandType.isRegister(op0_type):
        return False
    if m in ["MOV", "LEA", "XOR", "ADD", "SUB", "AND", "OR", "IMUL", "SHL", "SHR", "SAR", "NEG", "NOT", "INC", "DEC", "POP"]:
        return mentions_reg(ins, 0, reg)
    return False


def block_sources(addr):
    block = bm.getFirstCodeBlockContaining(addr, monitor)
    if block is None:
        return None, None, []
    out = []
    it = block.getSources(monitor)
    while it.hasNext():
        ref = it.next()
        src = ref.getSourceAddress()
        fn = getFunctionContaining(src)
        out.append((str(src), fn.getName() if fn else "<none>", str(ref.getFlowType())))
    out.sort()
    return block.getMinAddress(), block.getMaxAddress(), out


print("SLICE_38A30_ESI_EBX_ORIGINS")

pass_results = []

for p in range(1, PASSES + 1):
    clear_range(WS, WE)
    disassemble(WS)
    createFunction(ENTRY, None)

    insns = get_window_ins(WS, WE)
    if len(insns) == 0:
        disassemble(ENTRY_FALLBACK)
        createFunction(ENTRY_FALLBACK, None)
        insns = get_window_ins(WS, WE)
    sig = ["%s|%s" % (i.getAddress(), i.toString()) for i in insns]

    call_idx = -1
    for i, iobj in enumerate(insns):
        if CALL_31F8C in iobj.toString():
            call_idx = i
            break

    esi_defs = []
    ebx_defs = []
    if call_idx >= 0:
        j = call_idx - 1
        while j >= 0 and (len(esi_defs) < 6 or len(ebx_defs) < 6):
            cur = insns[j]
            fn = getFunctionContaining(cur.getAddress())
            name = fn.getName() if fn else "<none>"
            if len(esi_defs) < 6 and writes_reg(cur, "ESI"):
                esi_defs.append((str(cur.getAddress()), name, cur.toString()))
            if len(ebx_defs) < 6 and writes_reg(cur, "EBX"):
                ebx_defs.append((str(cur.getAddress()), name, cur.toString()))
            j -= 1

    bmin, bmax, bsrc = block_sources(toAddr("0x38a30"))

    pass_results.append((tuple(sig), tuple(esi_defs), tuple(ebx_defs), tuple(bsrc), str(bmin), str(bmax), call_idx))

    print("PASS", p, "INS_COUNT", len(sig), "SIG_FP", fp(sig), "CALL_IDX", call_idx)
    print("  BLOCK_38A30", bmin, bmax, "SOURCES", len(bsrc))
    for s in bsrc:
        print("    SRC", s[0], s[1], s[2])

    print("  ESI_DEFS", len(esi_defs))
    for d in esi_defs:
        print("    ESI_DEF", d[0], d[1], d[2])

    print("  EBX_DEFS", len(ebx_defs))
    for d in ebx_defs:
        print("    EBX_DEF", d[0], d[1], d[2])

stable = True
for i in range(1, len(pass_results)):
    if pass_results[i] != pass_results[0]:
        stable = False
        break

print("CROSS_PASS_STABLE", stable)
print("SLICE_38A30_ESI_EBX_ORIGINS_DONE")
