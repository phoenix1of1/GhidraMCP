from ghidra.program.model.listing import CodeUnit


targets = [
    {
        "label": "0x2006f_selector_write",
        "target": toAddr("0x2006f"),
        "clear_start": toAddr("0x20030"),
        "clear_end": toAddr("0x200b0"),
        "window_before": 0x40,
        "window_after": 0x90,
    },
    {
        "label": "0x1fd75_call_1f898",
        "target": toAddr("0x1fd75"),
        "clear_start": toAddr("0x1fd40"),
        "clear_end": toAddr("0x1fe10"),
        "window_before": 0x30,
        "window_after": 0x90,
    },
    {
        "label": "0x1fdb1_call_1f898",
        "target": toAddr("0x1fdb1"),
        "clear_start": toAddr("0x1fd80"),
        "clear_end": toAddr("0x1fe40"),
        "window_before": 0x30,
        "window_after": 0x90,
    },
    {
        "label": "0x31f87_case_stub",
        "target": toAddr("0x31f87"),
        "clear_start": toAddr("0x31f70"),
        "clear_end": toAddr("0x31fc0"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x31f97_callsite_stub",
        "target": toAddr("0x31f97"),
        "clear_start": toAddr("0x31f80"),
        "clear_end": toAddr("0x31fd8"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x2e7fc_alias_probe",
        "target": toAddr("0x2e7fc"),
        "clear_start": toAddr("0x2e7d0"),
        "clear_end": toAddr("0x2e840"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x38760_to_38820_bridge",
        "target": toAddr("0x387e0"),
        "clear_start": toAddr("0x38760"),
        "clear_end": toAddr("0x38820"),
        "window_before": 0x40,
        "window_after": 0xC0,
    },
    {
        "label": "0x38820_to_38890_bridge",
        "target": toAddr("0x38840"),
        "clear_start": toAddr("0x38820"),
        "clear_end": toAddr("0x38890"),
        "window_before": 0x30,
        "window_after": 0xA0,
    },
    {
        "label": "0x38890_to_388d8_bridge",
        "target": toAddr("0x38890"),
        "clear_start": toAddr("0x38880"),
        "clear_end": toAddr("0x388e8"),
        "window_before": 0x20,
        "window_after": 0x90,
    },
    {
        "label": "0x388b8_upstream1",
        "target": toAddr("0x388b8"),
        "clear_start": toAddr("0x388a8"),
        "clear_end": toAddr("0x388e0"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x388c8_upstream2",
        "target": toAddr("0x388c8"),
        "clear_start": toAddr("0x388b8"),
        "clear_end": toAddr("0x388f0"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x388e5_upstream3",
        "target": toAddr("0x388e5"),
        "clear_start": toAddr("0x388d8"),
        "clear_end": toAddr("0x38910"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x38898_micro",
        "target": toAddr("0x38898"),
        "clear_start": toAddr("0x38890"),
        "clear_end": toAddr("0x388c8"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x388d8_micro",
        "target": toAddr("0x388d8"),
        "clear_start": toAddr("0x388c0"),
        "clear_end": toAddr("0x38908"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x389dd_to_38a13",
        "target": toAddr("0x389dd"),
        "clear_start": toAddr("0x389c8"),
        "clear_end": toAddr("0x38a24"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x38a04_branch",
        "target": toAddr("0x38a04"),
        "clear_start": toAddr("0x389f0"),
        "clear_end": toAddr("0x38a34"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x388b0_feeder_precise",
        "target": toAddr("0x388b0"),
        "clear_start": toAddr("0x38890"),
        "clear_end": toAddr("0x38910"),
        "window_before": 0x30,
        "window_after": 0x90,
    },
    {
        "label": "0x38901_feeder_entry",
        "target": toAddr("0x38901"),
        "clear_start": toAddr("0x388f0"),
        "clear_end": toAddr("0x38990"),
        "window_before": 0x30,
        "window_after": 0xA0,
    },
    {
        "label": "0x38949_pre_38a13",
        "target": toAddr("0x38949"),
        "clear_start": toAddr("0x38930"),
        "clear_end": toAddr("0x389c0"),
        "window_before": 0x30,
        "window_after": 0xA0,
    },
    {
        "label": "0x352a0_call_3b8c8_focus",
        "target": toAddr("0x352a0"),
        "clear_start": toAddr("0x35288"),
        "clear_end": toAddr("0x352c0"),
        "window_before": 0x24,
        "window_after": 0x70,
    },
    {
        "label": "0x3095e_call_3b8c8_focus",
        "target": toAddr("0x3095e"),
        "clear_start": toAddr("0x30934"),
        "clear_end": toAddr("0x309a0"),
        "window_before": 0x24,
        "window_after": 0x90,
    },
    {
        "label": "0x31067_call_3b8c8_focus",
        "target": toAddr("0x31067"),
        "clear_start": toAddr("0x31050"),
        "clear_end": toAddr("0x310c8"),
        "window_before": 0x24,
        "window_after": 0x90,
    },
    {
        "label": "0x31de6_after_38a44",
        "target": toAddr("0x31de6"),
        "clear_start": toAddr("0x31dc8"),
        "clear_end": toAddr("0x31e20"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x31dfd_after_38a44",
        "target": toAddr("0x31dfd"),
        "clear_start": toAddr("0x31de0"),
        "clear_end": toAddr("0x31e40"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x31eb7_after_38a44",
        "target": toAddr("0x31eb7"),
        "clear_start": toAddr("0x31e90"),
        "clear_end": toAddr("0x31f00"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x30572_after_38a44",
        "target": toAddr("0x30572"),
        "clear_start": toAddr("0x30540"),
        "clear_end": toAddr("0x305b8"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x305a4_after_38a44",
        "target": toAddr("0x305a4"),
        "clear_start": toAddr("0x30588"),
        "clear_end": toAddr("0x305e0"),
        "window_before": 0x20,
        "window_after": 0x70,
    },
    {
        "label": "0x305eb_after_38a44",
        "target": toAddr("0x305eb"),
        "clear_start": toAddr("0x305d0"),
        "clear_end": toAddr("0x30630"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x38a13_precise",
        "target": toAddr("0x38a13"),
        "clear_start": toAddr("0x389f0"),
        "clear_end": toAddr("0x38a40"),
        "window_before": 0x30,
        "window_after": 0x80,
    },
    {
        "label": "0x3095e_call_3b8c8",
        "target": toAddr("0x3095e"),
        "clear_start": toAddr("0x30940"),
        "clear_end": toAddr("0x30990"),
        "window_before": 0x30,
        "window_after": 0x80,
    },
    {
        "label": "0x31067_call_3b8c8",
        "target": toAddr("0x31067"),
        "clear_start": toAddr("0x31040"),
        "clear_end": toAddr("0x310b0"),
        "window_before": 0x30,
        "window_after": 0x80,
    },
    {
        "label": "0x35290_callsetup",
        "target": toAddr("0x35290"),
        "clear_start": toAddr("0x35280"),
        "clear_end": toAddr("0x352b8"),
        "window_before": 0x20,
        "window_after": 0x60,
    },
    {
        "label": "0x352ad_postcall",
        "target": toAddr("0x352ad"),
        "clear_start": toAddr("0x352a0"),
        "clear_end": toAddr("0x352e8"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x3b8c8_precise",
        "target": toAddr("0x3b8c8"),
        "clear_start": toAddr("0x3b880"),
        "clear_end": toAddr("0x3b980"),
        "window_before": 0x40,
        "window_after": 0x120,
    },
    {
        "label": "0x35104_entry",
        "target": toAddr("0x35104"),
        "clear_start": toAddr("0x350f0"),
        "clear_end": toAddr("0x35170"),
        "window_before": 0x30,
        "window_after": 0xA0,
    },
    {
        "label": "0x3526b_mid",
        "target": toAddr("0x3526b"),
        "clear_start": toAddr("0x35240"),
        "clear_end": toAddr("0x352f0"),
        "window_before": 0x40,
        "window_after": 0xA0,
    },
    {
        "label": "0x356c4_entry",
        "target": toAddr("0x356c4"),
        "clear_start": toAddr("0x35690"),
        "clear_end": toAddr("0x35740"),
        "window_before": 0x40,
        "window_after": 0xB0,
    },
    {
        "label": "0x358a7_tail",
        "target": toAddr("0x358a7"),
        "clear_start": toAddr("0x35880"),
        "clear_end": toAddr("0x35910"),
        "window_before": 0x40,
        "window_after": 0xA0,
    },
    {
        "label": "0x20acc_precise",
        "target": toAddr("0x20acc"),
        "clear_start": toAddr("0x20a90"),
        "clear_end": toAddr("0x21f70"),
        "window_before": 0x40,
        "window_after": 0x120,
    },
    {
        "label": "0x21fcc_precise",
        "target": toAddr("0x21fcc"),
        "clear_start": toAddr("0x21f90"),
        "clear_end": toAddr("0x22030"),
        "window_before": 0x40,
        "window_after": 0x90,
    },
    {
        "label": "0x31b84_precise",
        "target": toAddr("0x31b84"),
        "clear_start": toAddr("0x31b70"),
        "clear_end": toAddr("0x31bf0"),
        "window_before": 0x20,
        "window_after": 0x80,
    },
    {
        "label": "0x38b11_precise",
        "target": toAddr("0x38b11"),
        "clear_start": toAddr("0x38b11"),
        "clear_end": toAddr("0x38ba0"),
        "window_before": 0x10,
        "window_after": 0x90,
    },
    {
        "label": "0x14d6f",
        "target": toAddr("0x14d6f"),
        "clear_start": toAddr("0x14d30"),
        "clear_end": toAddr("0x14dc0"),
        "window_before": 0x40,
        "window_after": 0x60,
    },
    {
        "label": "0x31dd0",
        "target": toAddr("0x31dd0"),
        "clear_start": toAddr("0x31da0"),
        "clear_end": toAddr("0x31f20"),
        "window_before": 0x20,
        "window_after": 0x170,
    },
    {
        "label": "0x39298",
        "target": toAddr("0x39298"),
        "clear_start": toAddr("0x39280"),
        "clear_end": toAddr("0x39320"),
        "window_before": 0x18,
        "window_after": 0x90,
    },
    {
        "label": "0x39358",
        "target": toAddr("0x39358"),
        "clear_start": toAddr("0x39340"),
        "clear_end": toAddr("0x393c0"),
        "window_before": 0x18,
        "window_after": 0x80,
    },
    {
        "label": "0x39414",
        "target": toAddr("0x39414"),
        "clear_start": toAddr("0x393f0"),
        "clear_end": toAddr("0x39490"),
        "window_before": 0x20,
        "window_after": 0x90,
    },
    {
        "label": "0x395d0",
        "target": toAddr("0x395d0"),
        "clear_start": toAddr("0x395b8"),
        "clear_end": toAddr("0x39630"),
        "window_before": 0x18,
        "window_after": 0x80,
    },
    {
        "label": "0x38760",
        "target": toAddr("0x38760"),
        "clear_start": toAddr("0x38740"),
        "clear_end": toAddr("0x387f0"),
        "window_before": 0x20,
        "window_after": 0xb0,
    },
    {
        "label": "0x387fa",
        "target": toAddr("0x387fa"),
        "clear_start": toAddr("0x387e8"),
        "clear_end": toAddr("0x38910"),
        "window_before": 0x10,
        "window_after": 0x120,
    },
    {
        "label": "0x38861",
        "target": toAddr("0x38861"),
        "clear_start": toAddr("0x38860"),
        "clear_end": toAddr("0x38900"),
        "window_before": 0x01,
        "window_after": 0xa0,
    },
    {
        "label": "0x388b0",
        "target": toAddr("0x388b0"),
        "clear_start": toAddr("0x38890"),
        "clear_end": toAddr("0x38918"),
        "window_before": 0x10,
        "window_after": 0x80,
    },
    {
        "label": "0x388f0",
        "target": toAddr("0x388f0"),
        "clear_start": toAddr("0x388d8"),
        "clear_end": toAddr("0x389b8"),
        "window_before": 0x10,
        "window_after": 0xa0,
    },
    {
        "label": "0x389a5",
        "target": toAddr("0x389a5"),
        "clear_start": toAddr("0x38998"),
        "clear_end": toAddr("0x38a1c"),
        "window_before": 0x10,
        "window_after": 0x80,
    },
    {
        "label": "0x389d9",
        "target": toAddr("0x389d9"),
        "clear_start": toAddr("0x389b8"),
        "clear_end": toAddr("0x38a24"),
        "window_before": 0x10,
        "window_after": 0x70,
    },
    {
        "label": "0x31f8c",
        "target": toAddr("0x31f8c"),
        "clear_start": toAddr("0x31f84"),
        "clear_end": toAddr("0x31fd0"),
        "window_before": 0x10,
        "window_after": 0x70,
    },
    {
        "label": "0x38a32",
        "target": toAddr("0x38a32"),
        "clear_start": toAddr("0x389f0"),
        "clear_end": toAddr("0x38a50"),
        "window_before": 0x20,
        "window_after": 0x40,
    },
    {
        "label": "0x38a44_precise",
        "target": toAddr("0x38a44"),
        "clear_start": toAddr("0x38a44"),
        "clear_end": toAddr("0x38b10"),
        "window_before": 0x00,
        "window_after": 0xd0,
    },
    {
        "label": "0x30572",
        "target": toAddr("0x30572"),
        "clear_start": toAddr("0x30550"),
        "clear_end": toAddr("0x30640"),
        "window_before": 0x10,
        "window_after": 0x90,
    },
    {
        "label": "0x38b11",
        "target": toAddr("0x38b11"),
        "clear_start": toAddr("0x38b00"),
        "clear_end": toAddr("0x38b90"),
        "window_before": 0x10,
        "window_after": 0x60,
    },
    {
        "label": "0x394c0",
        "target": toAddr("0x394c0"),
        "clear_start": toAddr("0x394a8"),
        "clear_end": toAddr("0x39510"),
        "window_before": 0x10,
        "window_after": 0x50,
    },
    {
        "label": "0x39520",
        "target": toAddr("0x39520"),
        "clear_start": toAddr("0x394f8"),
        "clear_end": toAddr("0x39570"),
        "window_before": 0x20,
        "window_after": 0x60,
    },
]

listing = currentProgram.getListing()

tx = currentProgram.startTransaction("Recover tight runtime regions")
try:
    for item in targets:
        target = item["target"]
        clear_start = item["clear_start"]
        clear_end = item["clear_end"]
        println("=== %s ===" % item["label"])
        println("target=%s" % target)
        println("clear_range=%s..%s" % (clear_start, clear_end))

        before = getFunctionContaining(target)
        println(
            "before_function=%s"
            % ("<none>" if before is None else "%s @ %s" % (before.getName(), before.getEntryPoint()))
        )

        listing.clearCodeUnits(clear_start, clear_end, False)
        println("cleared_code_units")
        disassemble(target)
        println("disassemble_called")
        created = createFunction(target, None)
        println(
            "create_function=%s"
            % ("<null>" if created is None else "%s @ %s" % (created.getName(), created.getEntryPoint()))
        )

        after = getFunctionContaining(target)
        println(
            "after_function=%s"
            % ("<none>" if after is None else "%s @ %s" % (after.getName(), after.getEntryPoint()))
        )

        window_start = target.subtract(item["window_before"])
        window_end = target.add(item["window_after"])
        println("window=%s..%s" % (window_start, window_end))

        instr = listing.getInstructionAt(window_start)
        if instr is None:
            instr = listing.getInstructionAfter(window_start)

        while instr is not None and instr.getAddress().compareTo(window_end) <= 0:
            operands = []
            for index in range(instr.getNumOperands()):
                operands.append(instr.getDefaultOperandRepresentation(index))
            println("%s: %s %s" % (
                instr.getAddress(),
                instr.getMnemonicString(),
                ", ".join(operands),
            ))
            instr = listing.getInstructionAfter(instr.getAddress())

        println("")
finally:
    currentProgram.endTransaction(tx, True)