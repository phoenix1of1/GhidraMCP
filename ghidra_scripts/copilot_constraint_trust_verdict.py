listing = currentProgram.getListing()
rm = currentProgram.getReferenceManager()

# Candidate lanes to evaluate under a strict two-pass micro-refresh policy.
CANDIDATES = [
    {
        "name": "update_consumer",
        "addr": "0x31b84",
        "window_start": "0x31b84",
        "window_end": "0x31c90",
        "required_tokens": ["+ 0x284", "+ 0x280", "+ 0x27c"],
    },
    {
        "name": "case_stub",
        "addr": "0x31f97",
        "window_start": "0x31f90",
        "window_end": "0x31fd8",
        "required_tokens": ["CALL 0x00031b84"],
    },
    {
        "name": "dispatcher_jump",
        "addr": "0x1f6c8",
        "window_start": "0x1f6be",
        "window_end": "0x1f6cf",
        "required_tokens": ["JMP dword ptr [EAX*0x4 + 0x11f30]"],
    },
    {
        "name": "38a32_wait_lane",
        "addr": "0x38a32",
        "window_start": "0x38a20",
        "window_end": "0x38a38",
        "required_tokens": ["CALL 0x00031f8c"],
    },
]

PASSES = 2


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


def window_ins_signature(start, end):
    sig = []
    ins = listing.getInstructionAt(start)
    if ins is None:
        ins = listing.getInstructionAfter(start)
    while ins and ins.getAddress().compareTo(end) <= 0:
        sig.append("%s|%s" % (ins.getAddress(), ins.toString()))
        ins = ins.getNext()
    return sig


def signature_fingerprint(lines):
    # Deterministic compact checksum for cross-run comparison in logs.
    joined = "\n".join(lines)
    acc = 0
    for ch in joined:
        acc = ((acc * 131) + ord(ch)) & 0xFFFFFFFF
    return "%08x" % acc


def ref_signature(addr):
    to_refs = []
    from_refs = []
    for r in rm.getReferencesTo(addr):
        frm = r.getFromAddress()
        to_refs.append("%s|%s" % (frm, r.getReferenceType()))
    for r in rm.getReferencesFrom(addr):
        to = r.getToAddress()
        from_refs.append("%s|%s" % (to, r.getReferenceType()))
    to_refs.sort()
    from_refs.sort()
    return to_refs, from_refs


def print_ref_block(label, refs):
    print("   ", label, "COUNT", len(refs))
    for r in refs:
        print("     ", r)


def has_required_tokens(sig, required_tokens):
    if not required_tokens:
        return True
    joined = "\n".join(sig)
    for tok in required_tokens:
        if tok not in joined:
            return False
    return True


print("CONSTRAINT_TRUST_VERDICT")

results = []

for c in CANDIDATES:
    addr = toAddr(c["addr"])
    ws = toAddr(c["window_start"])
    we = toAddr(c["window_end"])

    pass_sigs = []
    pass_to_refs = []
    pass_from_refs = []

    print("CANDIDATE", c["name"], addr, "WINDOW", ws, we)

    for p in range(1, PASSES + 1):
        clear_range(ws, we)
        disassemble(ws)
        createFunction(addr, None)

        sig = window_ins_signature(ws, we)
        to_refs, from_refs = ref_signature(addr)

        pass_sigs.append(sig)
        pass_to_refs.append(to_refs)
        pass_from_refs.append(from_refs)

        print("  PASS", p, "INS_COUNT", len(sig), "SIG_FP", signature_fingerprint(sig), "TO_REFS", len(to_refs), "FROM_REFS", len(from_refs))
        print_ref_block("TO_REFS", to_refs)
        print_ref_block("FROM_REFS", from_refs)

    l1_stable_decode = len(pass_sigs[0]) > 0 and pass_sigs[0] == pass_sigs[1]
    l2_stable_refs = pass_to_refs[0] == pass_to_refs[1] and pass_from_refs[0] == pass_from_refs[1]
    l3_semantic_anchor = has_required_tokens(pass_sigs[0], c["required_tokens"]) and has_required_tokens(pass_sigs[1], c["required_tokens"])

    stable_ref_count = len(pass_to_refs[0]) + len(pass_from_refs[0])
    overall = l1_stable_decode and l2_stable_refs and l3_semantic_anchor and (stable_ref_count > 0 or c["name"] == "update_consumer")

    print("  L1_STABLE_DECODE", l1_stable_decode)
    print("  L2_STABLE_REFS", l2_stable_refs)
    print("  L3_SEMANTIC_ANCHOR", l3_semantic_anchor)
    print("  STABLE_REF_COUNT", stable_ref_count)
    if len(pass_sigs[0]) > 0 and len(pass_sigs[1]) > 0:
        print("  SIG_FP_PASS1", signature_fingerprint(pass_sigs[0]))
        print("  SIG_FP_PASS2", signature_fingerprint(pass_sigs[1]))
    print("  VERDICT", "TRUSTED" if overall else "UNSTABLE")

    results.append((c["name"], overall, l1_stable_decode, l2_stable_refs, l3_semantic_anchor, stable_ref_count))

print("SUMMARY")
for name, overall, l1, l2, l3, rc in results:
    print("  %s => %s (L1=%s L2=%s L3=%s refs=%d)" % (name, "TRUSTED" if overall else "UNSTABLE", l1, l2, l3, rc))

print("CONSTRAINT_TRUST_VERDICT_DONE")
