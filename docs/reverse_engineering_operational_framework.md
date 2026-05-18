# Reverse Engineering Operational Framework

This framework converts exploratory reverse engineering into
deterministic, CI-verifiable progress for this repository.

## Goal

Use a repeatable loop:

1. Observe original behavior
2. Form a testable hypothesis
3. Implement extraction/runtime logic
4. Lock behavior with snapshots/contracts
5. Verify in no-write CI mode

## Scope Model

Work is planned and delivered in subsystem slices.

Examples:

- Resource/index decoding
- Script execution and scheduler behavior
- Placement/pathfinding behaviors
- Render decoding and checksums
- Interaction contracts (inventory/hotspots/dialog)

Each slice must define objective evidence before implementation starts.

## Standard Execution Loop

### Phase 1: Define Slice and Evidence

Create a work item using the template in docs/planning/subsystem_contract_work_item_template.md.

Required outputs:

- Subsystem boundary and scene/file scope
- Runtime observation points (trace events, counters, or structure fields)
- Deterministic contract schema to lock
- Exit criteria for merge readiness

### Phase 2: Collect Signals

Gather evidence from static + runtime sources.

Recommended sources:

- Static structure hints from disassembly and scene/resource layout
- VM-lite event traces and script handle coverage
- Existing snapshots in tests/snapshots for drift context

Output:

- Explicit list of candidate invariants that should not regress

### Phase 3: Implement Contracts

Add deterministic contract generation in
scripts/refresh_snapshot_baselines.py and add a matching unittest in tests.

Rules:

- Keep scene set fixed and explicit
- Keep script ordering deterministic
- Use stable histograms/fingerprints where sequence size is large
- Avoid non-deterministic fields (timestamps, host-specific paths)

### Phase 4: Baseline and Verify

Generate or refresh only the target group, then run CI-style verification.

Commands:

```powershell
pwsh -File scripts/refresh_snapshot_baselines.ps1 --only <group>
pwsh -File scripts/run_ci_verify.ps1
```

Quality gate:

- Snapshot dry-check passes with no drift
- Full regression suite passes
- README coverage updated for the new harness

### Phase 5: Document and Hand Off

Update README and work item status so future contributors can extend
from a stable point.

Minimum documentation:

- What behavior is locked
- Which scenes/files are covered
- Which command refreshes the baseline

## Determinism Rules

All new harnesses must satisfy the following:

- Fixed scene list and script cap
- Stable sort order for scripts and emitted keys
- Numeric/string-only stable fields in snapshots
- Hash long sequences when needed and keep a small readable prefix
- No implicit writes during verification

## Recommended Contract Shapes

Pick one or combine several shapes per subsystem:

- Count contracts: event totals, scripts traced, coverage counts
- Histogram contracts: opcode/libcall/transition distributions
- Range contracts: min/max stack depth, fan-out, path depth
- Sequence fingerprint contracts: stable prefix plus SHA-256
  digest
- Resolution contracts: selected target/polygon/resource and tie-break metrics

## Merge Readiness Checklist

A subsystem slice is merge-ready when all are true:

- Work item filled with scope, invariants, and risks
- Snapshot builder added to refresh script
- Matching unittest added in tests
- Baseline snapshot committed in tests/snapshots
- README updated with harness coverage and --only command
- pwsh -File scripts/run_ci_verify.ps1 passes

## Active Mapping to Current Repository

The repository already uses this model for:

- SCN chunk snapshots
- PCODE/LIBCALL snapshots
- Bitmap checksum snapshots
- Scheduler event snapshots
- Placement convergence snapshots
- Scheduler side-effects contracts
- Branch convergence contracts

Use the same pattern for the next runtime slices (inventory semantics,
dialogue sequencing, hotspot interaction contracts, audio command contracts).
