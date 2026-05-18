# 52. Project Validation Review
## Summary
Validation pass over the current uploaded Discworld PC dataset and generated tooling artifacts.
## Dataset Checks
- `.SCN` files checked: **79**
- Chunk-chain errors: **0**
- Distinct top-level chunk sequences: **6**
- `INDEX` records parsed: **149**
- Image chunks with 16-byte alignment: **79/79**
- Palette chunks cleanly parsed as count + 32-bit colors: **79/79**

## Artifact Integrity
- ZIP artifacts checked: **27**
- ZIP artifacts passing `testzip()`: **27/27**

## Validated Findings
- SCN linked chunk traversal and terminal chunk behavior
- INDEX fixed 20-byte records with 12-byte filenames
- SCNHANDLE split: `file_index = handle >> 23`, `offset = handle & 0x007FFFFF`
- Palette records: signed count plus 32-bit packed RGB values
- Image records: 16-byte Discworld/Tinsel 1 layout
- Tinsel 1 tile renderer produces PNGs with broad sample coverage
- Film/reel/frame/image graph is usable for visual exports
- PCODE interpreter and libcall dispatcher addresses are identified in `DWB.EXE`
- VM-lite/scheduler/timeline exports run and produce structured event data
- BAR character asset pack and playback prototypes produce visual outputs without reported render failures

## Provisional / Needs Re-check
- Exact scheduler libcall side effects beyond current ABI/arity model
- Exact runtime timing and branch-deterministic PCODE execution
- Runtime-faithful PLAY placement final coordinates until live state is fully reconstructed
- Names for some `RuntimeMoverPlacementState` fields before `+0x24`; roles are working labels, not final names
- Broad claims about all game scenes until remaining unuploaded resources, if any, are checked

## Corrections / Clarifications
- `0x1AE18` should be treated as the runtime polygon pointer table, not an actor/object pointer table.
- `PLAY` is a shared scheduler-cluster label, not a clean standalone function.
- `polyType == 1` in PLAY helper context is runtime `PTYPE::BLOCK`, not compiled `POLY_NPATH`.
- Current scene playback outputs are validation prototypes, not pixel-perfect runtime playback.

## Validation Status
The extraction/asset side is well validated. The runtime/playback side is usable and internally consistent, but still carries explicit provisional markers for exact side effects, timing, and final placement.

## Recommended Next Validation Step
Create a repeatable regression test suite for `discworld_extract.py` that runs chunk/image/render/pcode/timeline checks on a fixed small scene set (`BAR`, `LIBRARY`, `OBJECTS`, `DW`, `CLIMAX`) and emits pass/fail results.
