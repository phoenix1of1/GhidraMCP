# Discworld PC / Tinsel 1 Reverse Engineering Repository

This repository contains generated tooling, specifications, and validation artifacts
for reverse engineering the Discworld DOS game using the Tinsel 1 engine.

## Naming Convention

- Directory names use lowercase snake_case.
- Script filenames use lowercase snake_case.
- The canonical repository root name is `discworld_full_repo_package`.

## Primary Reference

See:

`specs/discworld_tinsel_master_spec_authoritative.md`

Operational process reference:

`docs/reverse_engineering_operational_framework.md`

Planning and agent-context docs:

- `docs/planning/implementation_backlog.md`
- `docs/agent/craft_prompt.md`
- `docs/planning/subsystem_contract_work_item_template.md`

## Main Components

- `extractor/` — asset extraction and rendering
- `runtime/` — VM, PCODE, scheduler, and runtime analysis
- `validation/` — placement/playback validation harnesses
- `assets/` — animation and character asset compilers
- `ghidra/` — labeled CFGs and decompiler-support artifacts
- `reports/` — runtime analysis reports

## Current Status

- Extraction pipeline: highly validated
- Runtime/playback pipeline: partially reconstructed
- Placement/runtime timing: still provisional

## Suggested Workflow

1. Read the authoritative spec.
2. Run the one-command entrypoint from the repository root:

   `pwsh -File scripts/run_discworld_extract.ps1`

   Optional examples:

   `pwsh -File scripts/run_discworld_extract.ps1 --mode chunks --clean-output`

   `pwsh -File scripts/run_discworld_extract.ps1 --mode visual --scenes BAR.SCN CLIMAX.SCN`

   This wrapper auto-detects input from `../clean-game/DISCWLD` (or `../clean-game`) and writes to `outputs/latest_run`.

3. Import `DWB.EXE` into Ghidra/IDA using the generated labels/structs.
4. Use validation overlays and playback viewers to refine runtime semantics.

## Script Entrypoints

- `scripts/run_discworld_extract.ps1` - PowerShell runner for one-command execution.
- `scripts/run_discworld_extract.py` - Python runner used by the PowerShell wrapper.
- `scripts/run_regression_tests.ps1` - PowerShell runner for deterministic regression tests.
- `scripts/run_regression_tests.py` - Python regression test runner.
- `scripts/refresh_snapshot_baselines.ps1` - PowerShell runner to regenerate snapshot baselines.
- `scripts/refresh_snapshot_baselines.py` - Python utility to refresh snapshot JSON files.
- `scripts/run_ci_verify.ps1` - CI-style verify: dry-check snapshot drift, then run regression tests.
- `extractor/discworld_extract.py` - Core unified extractor and analysis CLI.

## One-Command Regression Test Run

From repository root:

`pwsh -File scripts/run_regression_tests.ps1`

Optional explicit dataset path:

`pwsh -File scripts/run_regression_tests.ps1 --input ..\clean-game\DISCWLD`

Current regression coverage includes:

- SCNHANDLE encode/decode roundtrip and range validation.
- INDEX parser stability and core scene presence checks.
- SCN chunk traversal snapshots for `BAR.SCN`, `LIBRARY.SCN`, `OBJECTS.SCN`, `DW.SCN`, and `CLIMAX.SCN`.
- PCODE and LIBCALL discovery snapshots (script counts and opcode/libcall histograms) for `BAR.SCN`, `LIBRARY.SCN`, `OBJECTS.SCN`, `DW.SCN`, and `CLIMAX.SCN`.
- Bitmap render checksum snapshots (indexed and RGBA SHA-256) for a fixed image subset from `BAR.SCN`, `LIBRARY.SCN`, `OBJECTS.SCN`, `DW.SCN`, and `CLIMAX.SCN`.
- Scheduler-event extraction snapshots (VM-lite libcall-derived scheduler histograms) for `BAR.SCN`, `LIBRARY.SCN`, `OBJECTS.SCN`, `DW.SCN`, and `CLIMAX.SCN`.
- PLAY placement convergence snapshots (selected polygon, adjusted coordinates, candidate counts, Manhattan choice metric) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Scheduler side-effects contract snapshots (stack-depth ranges, film-arg incidence, and transition fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Branch convergence contract snapshots (fan-out ceilings, path-depth ceilings, truncation counters, and branch opcode profiles) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Inventory interaction contract snapshots (inventory libcall histograms, source/transition fingerprints, and stack/path ranges) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Hotspot interaction contract snapshots (TAG/EXIT polygon invariants plus conversation/talk dispatch fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Dialogue/topic routing contract snapshots (dialogue sequence, hotspot/inventory-to-dialogue transitions, and dialogue-to-action fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- Timing/wait semantics contract snapshots (WAITFRAME/WAITTIME/EVENT density and transition fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE CFG invariant snapshots (entry/reachability/dead-end characteristics and edge fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE libcall signature contract snapshots (argument-shape and arity profiles with stack-depth ranges) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE IR lift snapshots (node-kind/opcode/block-shape histograms and terminator fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE structuring snapshots (region terminator/loop/conditional metrics and structural fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE semantic annotation snapshots (libcall behavior tags, argument labels, region semantics, and pseudocode summary fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE symbol recovery snapshots (local/global symbol names, role/type hints, and symbol-transition fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.
- PCODE symbol canonicalization snapshots (cross-scene canonical aliases, cluster registry, and alias-transition fingerprints) for `BAR.SCN`, `CLIMAX.SCN`, and `FINALE.SCN`.

## Snapshot Refresh Utility

Regenerate all committed snapshot baselines after intentional and validated tool/runtime changes:

`pwsh -File scripts/refresh_snapshot_baselines.ps1`

Refresh only one snapshot group:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only scheduler`

Refresh only placement convergence snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only placement`

Refresh only scheduler side-effects contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only contracts`

Refresh only branch convergence contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only branch`

Refresh only inventory interaction contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only inventory`

Refresh only hotspot interaction contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only hotspot`

Refresh only dialogue/topic routing contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only dialogue`

Refresh only timing/wait semantics contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only timing`

Refresh only PCODE CFG invariant snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only cfg`

Refresh only PCODE libcall signature contracts:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only libsig`

Refresh only PCODE IR lift snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only ir`

Refresh only PCODE structuring snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only struct`

Refresh only PCODE semantic annotation snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only semantic`

Refresh only PCODE symbol recovery snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only symbols`

Refresh only PCODE symbol canonicalization snapshots:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --only canon`

Refresh from an explicit dataset path:

`pwsh -File scripts/refresh_snapshot_baselines.ps1 --input ..\clean-game\DISCWLD`

## CI-Style Verify

Run a no-write verification pass that checks snapshot drift first and then runs tests:

`pwsh -File scripts/run_ci_verify.ps1`

With explicit dataset path:

`pwsh -File scripts/run_ci_verify.ps1 -DatasetPath ..\clean-game\DISCWLD`

Behavior:

- Default verify never rewrites baselines.
- Baseline updates are explicit follow-up actions via `refresh_snapshot_baselines.ps1`.

## Operationalizing New Reverse Engineering Work

Before implementing a new subsystem slice:

1. Start from `docs/planning/subsystem_contract_work_item_template.md`.
2. Define deterministic contracts and target snapshot group.
3. Implement builder + test + baseline.
4. Run `pwsh -File scripts/run_ci_verify.ps1` and keep verify no-write.

This repository's standard operating framework is documented in
`docs/reverse_engineering_operational_framework.md`.
