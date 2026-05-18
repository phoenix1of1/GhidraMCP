# Subsystem Contract Work Item Template

Use this template before implementing any new reverse-engineering harness.

## 1) Subsystem Definition

- Name:
- Owner:
- Date:
- Scope type: extraction | runtime | rendering | interaction | audio
- Target scenes/files:
- Excluded scenes/files:

## 2) Problem Statement

- What behavior are we trying to preserve?
- What regressions have occurred or are likely?
- Why this slice now?

## 3) Evidence Plan

Static signals:

- Structures/chunks/opcodes expected:
- Relevant module(s):

Runtime signals:

- VM events/libcalls/opcodes to capture:
- Path/branch/stack indicators to capture:

## 4) Contract Schema (Deterministic)

Snapshot group name:

- Group id for --only:
- Snapshot output path:
- Test file path:

Fields to lock:

- Count contracts:
- Histogram contracts:
- Range contracts:
- Sequence prefixes + digest:
- Any tie-break or selection metrics:

Determinism controls:

- Scene list fixed:
- Script ordering strategy:
- Max scripts/steps/paths:
- Key sorting strategy:

## 5) Implementation Plan

- Refresh utility changes:
- Test harness changes:
- README changes:

## 6) Validation Plan

Commands:

```powershell
pwsh -File scripts/refresh_snapshot_baselines.ps1 --only <group>
pwsh -File scripts/run_ci_verify.ps1
```

Pass criteria:

- Dry-check has no drift
- Full tests pass
- Snapshot structure is stable and reviewable

## 7) Risks and Mitigations

- Risk 1:
  - Mitigation:
- Risk 2:
  - Mitigation:

## 8) Done Criteria

- [ ] Snapshot builder added
- [ ] Test added
- [ ] Baseline committed
- [ ] README updated
- [ ] CI verify pass captured

## 9) Post-Merge Notes

- Follow-up slices:
- Known blind spots:
- Suggested next contract:
