# Discworld Tinsel 1 Implementation Backlog

## Goal

Turn validated research into a maintainable reverse-engineering and decompilation-support codebase through small, testable, evidence-driven steps.

## Evidence Anchors

- Authoritative spec: specs/discworld_tinsel_master_spec_authoritative.md
- PCODE interpreter anchor: 0x33B90
- OP_LIBCALL dispatcher anchor: 0x32F54
- DW1 libcall table anchor: 0x35638
- SCNHANDLE resolver anchor: 0x24FEC
- PLAY placement helpers: 0x37298, 0x35B68, 0x35B14, 0x35938

## Confirmed Baseline

- SCN traversal, INDEX parsing, SCNHANDLE decode, image and palette decode, bitmap render, FILM graph traversal, and PCODE/libcall discovery are validated.
- Unified CLI modes and RE tooling outputs are established.
- Scheduler side effects, deterministic timing and execution, and some placement-state semantics remain provisional.

## Workstream A: Regression Tests

1. Add SCN chunk traversal golden tests.
2. Add INDEX parser fixture tests.
3. Add SCNHANDLE encode and decode tests.
4. Add palette and image decode consistency tests.
5. Add bitmap render checksum tests.
6. Add FILM graph traversal and handle resolution tests.
7. Add PCODE scan and libcall discovery tests.
8. Add scheduler-event extraction snapshot tests.

## Workstream B: Runtime Analysis Tooling

1. Emit structured scheduler traces to JSON and CSV.
2. Add VM-lite trace export with branch and stack summaries.
3. Add scene timeline generation with actor and film overlays.
4. Add placement diagnostics output for PLAY candidate selection.

## Workstream C: Decompilation Support

1. Keep Ghidra and IDA import artifacts synchronized with discovered labels.
2. Version runtime structure headers and annotate confidence by field.
3. Emit labeled CFG output suitable for diff-based review.
4. Track shared code cluster entries versus standalone functions.

## Provisional Areas To Resolve

- Exact scheduler side effects.
- Deterministic VM execution across trace runs.
- Runtime-faithful timing behavior.
- Exact PLAY placement convergence in edge cases.
- RuntimeMoverPlacementState semantic field confirmation.

## Rules Of Engagement

- Do not invent structures or semantics without evidence.
- Mark uncertain findings as provisional, working, or unresolved.
- Separate extraction logic from runtime and playback logic.
- Preserve all validated facts from the authoritative spec.
- Prefer incremental changes with accompanying tests.

## Next Recommended Step

Create a minimal test harness skeleton first, starting with SCNHANDLE encode and decode tests because they are compact, deterministic, and anchor many downstream workflows.
