from ghidra.program.model.block import SimpleBlockModel
from ghidra.program.model.lang import OperandType

listing = currentProgram.getListing()
rm = currentProgram.getReferenceManager()
bm = SimpleBlockModel(currentProgram)

COMMON_WS = toAddr("0x38840")
COMMON_WE = toAddr("0x38910")
TARGETS = [
    toAddr("0x38840"),
    toAddr("0x38870"),
    toAddr("0x38861"),
    toAddr("0x38890"),
    toAddr("0x38898"),
    toAddr("0x388a1"),
    toAddr("0x388b0"),
    toAddr("0x388b4"),
    toAddr("0x388b8"),
    toAddr("0x388c6"),
    toAddr("0x388d8"),
    toAddr("0x388e5"),
    toAddr("0x388f0"),
    toAddr("0x388f2"),
    toAddr("0x38901"),
]

RECIPES = [
    {
        "name": "recipe_A_38870_388f0",
        "ws": "0x38870",
        "we": "0x388f0",
        "anchors": ["0x38870", "0x38898", "0x388b0", "0x388d8", "0x388e5"],
    },
    {
        "name": "recipe_B_38840_388b0",
        "ws": "0x38840",
        "we": "0x388b0",
        "anchors": ["0x38861", "0x38890", "0x38898", "0x388b0"],
    },
]

PASSES = 3


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


def common_ins_signature():
    sig = []
    ins = listing.getInstructionAt(COMMON_WS)
    if ins is None:
        ins = listing.getInstructionAfter(COMMON_WS)
    while ins and ins.getAddress().compareTo(COMMON_WE) <= 0:
        sig.append("%s|%s" % (ins.getAddress(), ins.toString()))
        ins = ins.getNext()
    return sig


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
    if ins.getNumOperands() == 0:
        return False
    if not OperandType.isRegister(ins.getOperandType(0)):
        return False
    if ins.getMnemonicString() in ["MOV", "LEA", "XOR", "ADD", "SUB", "AND", "OR", "IMUL", "SHL", "SHR", "SAR", "NEG", "NOT", "INC", "DEC", "POP"]:
        return mentions_reg(ins, 0, reg)
    return False


def gather_reg_defs(reg):
    out = set()
    ins = listing.getInstructionAt(COMMON_WS)
    if ins is None:
        ins = listing.getInstructionAfter(COMMON_WS)
    while ins and ins.getAddress().compareTo(COMMON_WE) <= 0:
        if writes_reg(ins, reg):
            fn = getFunctionContaining(ins.getAddress())
            out.add((str(ins.getAddress()), fn.getName() if fn else "<none>", ins.toString()))
        ins = ins.getNext()
    return out


def gather_edges_to_targets():
    out = set()
    for t in TARGETS:
        block = bm.getFirstCodeBlockContaining(t, monitor)
        if block is None:
            continue
        dst = "%s..%s" % (block.getMinAddress(), block.getMaxAddress())
        it = block.getSources(monitor)
        while it.hasNext():
            ref = it.next()
            src = ref.getSourceAddress()
            fn = getFunctionContaining(src)
            ins = listing.getInstructionAt(src)
            out.add((
                str(t),
                dst,
                str(src),
                fn.getName() if fn else "<none>",
                str(ref.getFlowType()),
                ins.toString() if ins else "<noins>",
            ))
    return out


def target_presence():
    out = []
    for t in TARGETS:
        ins = listing.getInstructionAt(t)
        out.append((str(t), ins.toString() if ins else "<none>"))
    return tuple(out)


def run_recipe(r):
    ws = toAddr(r["ws"])
    we = toAddr(r["we"])
    anchors = [toAddr(x) for x in r["anchors"]]

    passes = []
    for p in range(1, PASSES + 1):
        clear_range(COMMON_WS, COMMON_WE)
        clear_range(ws, we)
        disassemble(ws)
        for a in anchors:
            disassemble(a)
            createFunction(a, None)

        sig = common_ins_signature()
        defs_esi = gather_reg_defs("ESI")
        defs_edi = gather_reg_defs("EDI")
        defs_ebx = gather_reg_defs("EBX")
        defs_eax = gather_reg_defs("EAX")
        edges = gather_edges_to_targets()
        pres = target_presence()

        passes.append((tuple(sig), tuple(sorted(defs_esi)), tuple(sorted(defs_edi)), tuple(sorted(defs_ebx)), tuple(sorted(defs_eax)), tuple(sorted(edges)), pres))

        print("RECIPE", r["name"], "PASS", p, "COMMON_INS", len(sig), "FP", fp(sig), "EDGES", len(edges), "ESI", len(defs_esi), "EDI", len(defs_edi))

    stable = True
    for i in range(1, len(passes)):
        if passes[i] != passes[0]:
            stable = False
            break

    return stable, passes[0]


print("DUAL_RECIPE_INTERSECTION_38840_38910")

results = {}
for r in RECIPES:
    stable, data = run_recipe(r)
    results[r["name"]] = (stable, data)
    print("RECIPE_STABLE", r["name"], stable)

a_name = RECIPES[0]["name"]
b_name = RECIPES[1]["name"]
a_stable, a = results[a_name]
b_stable, b = results[b_name]

print("BOTH_STABLE", a_stable and b_stable)

if a_stable and b_stable:
    a_sig, a_esi, a_edi, a_ebx, a_eax, a_edges, a_pres = a
    b_sig, b_esi, b_edi, b_ebx, b_eax, b_edges, b_pres = b

    i_sig = sorted(set(a_sig).intersection(set(b_sig)))
    i_esi = sorted(set(a_esi).intersection(set(b_esi)))
    i_edi = sorted(set(a_edi).intersection(set(b_edi)))
    i_ebx = sorted(set(a_ebx).intersection(set(b_ebx)))
    i_eax = sorted(set(a_eax).intersection(set(b_eax)))
    i_edges = sorted(set(a_edges).intersection(set(b_edges)))

    print("INTERSECTION_COUNTS", "INS", len(i_sig), "EDGES", len(i_edges), "ESI", len(i_esi), "EDI", len(i_edi), "EBX", len(i_ebx), "EAX", len(i_eax))

    print("INTERSECTION_EDGES")
    for e in i_edges:
        print("  EDGE", e[0], e[1], e[2], e[3], e[4], e[5])

    print("INTERSECTION_ESI_DEFS")
    for d in i_esi:
        print("  ESI_DEF", d[0], d[1], d[2])

    print("INTERSECTION_EDI_DEFS")
    for d in i_edi:
        print("  EDI_DEF", d[0], d[1], d[2])

    print("INTERSECTION_EBX_DEFS")
    for d in i_ebx:
        print("  EBX_DEF", d[0], d[1], d[2])

    print("INTERSECTION_EAX_DEFS")
    for d in i_eax:
        print("  EAX_DEF", d[0], d[1], d[2])

    print("TARGET_PRESENCE_A")
    for t in a_pres:
        print("  TARGET", t[0], t[1])

    print("TARGET_PRESENCE_B")
    for t in b_pres:
        print("  TARGET", t[0], t[1])

print("DUAL_RECIPE_INTERSECTION_38840_38910_DONE")
