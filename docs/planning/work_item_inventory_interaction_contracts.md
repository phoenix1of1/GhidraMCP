# Inventory Interaction Contracts Work Item

## 1) Subsystem Definition

- Name: Inventory Interaction Contracts
- Owner: Repo maintainers
- Date: 2026-05-18
- Scope type: interaction
- Target scenes/files: BAR.SCN, CLIMAX.SCN, FINALE.SCN
- Excluded scenes/files: all non-target scenes for first harness pass

## 2) Problem Statement

- What behavior are we trying to preserve?
  - Stable inventory-related script behavior surfaced through VM-lite
    libcalls and object script handles.
  - Stable sequencing and relative frequency of inventory interactions
    across fixed scene/script samples.
- What regressions have occurred or are likely?
  - Silent drift in inventory libcall discovery after parser/runtime
    changes.
  - Changes in script-path exploration that alter inventory interaction
    sequences.
  - Loss of inventory-object script coverage when chunk parsing changes.
- Why this slice now?
  - Current harness coverage already locks scheduler, placement, and
    branch behavior.
  - Inventory interaction is a high-value gameplay semantic surface and
    is the next natural contract family.

## 3) Evidence Plan

Static signals:

- Structures/chunks/opcodes expected:
  - CHUNK_TOTAL_OBJECTS and CHUNK_OBJECTS parsing should continue to
    surface inventory.script handles.
  - LIBCALL opcode events should preserve inventory-relevant names from
    the known libcall table.
- Relevant module(s):
  - runtime/tinsel1_vm_lite.py
  - scripts/refresh_snapshot_baselines.py

Runtime signals:

- VM events/libcalls/opcodes to capture:
  - event == libcall
  - libcall_name in inventory call set:
    INVENTORY, ININVENTORY, INWHICHINV, WHICHINVENTORY, ADDINV1,
    ADDINV2, ADDOPENINV, DELINV, SETINVLIMIT, GETINVLIMIT,
    SETINVSIZE, HELDOBJECT, OBJECTHELD, SCANICON
  - source == inventory.script for handle-origin coverage metrics
- Path/branch/stack indicators to capture:
  - stack_depth min and max for inventory libcalls
  - paths_started aggregate for scripts with inventory activity
  - event-path depth max where inventory libcalls are observed

## 4) Contract Schema (Deterministic)

Snapshot group name:

- Group id for --only: inventory
- Snapshot output path: tests/snapshots/inventory_interaction_contracts.json
- Test file path: tests/test_inventory_interaction_contracts.py

Fields to lock:

- Count contracts:
  - scripts_traced
  - scripts_with_inventory_events
  - inventory_event_count
  - inventory_script_handles_found
- Histogram contracts:
  - inventory_libcall_histogram
  - inventory_source_histogram (scene.hSceneScript, actor.script,
    entrance.script, inventory.script)
  - inventory_transition_histogram (A->B for consecutive inventory
    libcalls)
- Range contracts:
  - stack_depth_min and stack_depth_max for inventory libcalls
  - max_path_depth_at_inventory_event
  - max_paths_started_for_inventory_scripts
- Sequence prefixes + digest:
  - inventory_sequence_head (first 30 inventory libcalls)
  - inventory_sequence_head_sha256 (pipe-joined sequence)
- Any tie-break or selection metrics:
  - deterministic script ordering by source then handle
  - cap to first 60 scripts per scene

Determinism controls:

- Scene list fixed: BAR.SCN, CLIMAX.SCN, FINALE.SCN
- Script ordering strategy: sort by source then handle; take first 60
- Max scripts/steps/paths: 60 scripts, max_steps=1200, max_paths=16
- Key sorting strategy:
  - sort snapshot top-level keys by scene name
  - sort histogram keys lexicographically before write

## 5) Implementation Plan

- Refresh utility changes:
  - Add INVENTORY_CONTRACT_SCENES and INVENTORY_LIBCALLS constants.
  - Add _build_inventory_interaction_contract_snapshots.
  - Wire inventory into --only choices, all-group set, and target map.
- Test harness changes:
  - Add tests/test_inventory_interaction_contracts.py
  - Recompute contracts deterministically and compare exact JSON payload
    per scene.
- README changes:
  - Add coverage bullet for inventory interaction contracts.
  - Add refresh command example for --only inventory.

## 6) Validation Plan

Commands:

```powershell
pwsh -File scripts/refresh_snapshot_baselines.ps1 --only inventory
pwsh -File scripts/run_ci_verify.ps1
```

Pass criteria:

- Dry-check has no drift
- Full tests pass
- Snapshot structure is stable and reviewable

## 7) Risks and Mitigations

- Risk 1:
  - Inventory libcalls may be sparse in the selected scenes, reducing
    contract strength.
  - Mitigation:
    - If sparsity is confirmed, expand deterministic scene set with one
      additional high-interaction scene from clean-game while keeping
      list fixed afterward.
- Risk 2:
  - Sequence contracts may become noisy if branch exploration limits are
    changed globally.
  - Mitigation:
    - Lock max_steps and max_paths inside this harness and include these
      limits in schema docs.

## 8) Done Criteria

- [x] Snapshot builder added
- [x] Test added
- [x] Baseline committed
- [x] README updated
- [x] CI verify pass captured (2026-05-18)

## 9) Post-Merge Notes

- Follow-up slices:
  - Hotspot interaction contracts
  - Dialogue/talk routing contracts
  - Script command semantic contracts for item combination paths
- Known blind spots:
  - No direct user input timing emulation; this harness is VM-lite trace
    based.
  - No full inventory UI render semantics in this slice.
- Suggested next contract:
  - Inventory-to-dialog bridge contracts (inventory call followed by
    TALK/TALKAT transition patterns).
