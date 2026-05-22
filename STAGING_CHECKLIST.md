# Staging Checklist

Purpose: keep commits reviewable, reproducible, and safe.

Use this checklist before every commit.

## Always Committable

Commit these when intentionally changed:

- Source code and scripts under:
  - `scripts/`
  - `runtime/`
  - `validation/`
  - `extractor/` (except local logs/cache)
- Tests and stable snapshots under:
  - `tests/test_*.py`
  - `tests/snapshots/*.json`
- Ghidra automation scripts under:
  - `ghidra_scripts/`
- Process/state documentation:
  - `GHIDRA_MCP_TARGET_QUEUE.md`
  - `STAGING_CHECKLIST.md`
- CI and gating entrypoints:
  - `scripts/run_ci_verify.ps1`
  - `scripts/validate_static_progress_baseline.py`
  - `scripts/run_safe_waittime_cycle.py`
  - `scripts/triage_waittime_family_frontier.py`

## Always Ignored

Never stage these generated or local-only artifacts:

- `outputs/`
- `*_character_asset_pack/`
- `*_composited_sprite_preview_outputs/`
- `*_composited_sprite_preview_outputs.zip`
- `extractor/discworld_extract_last_helper.log`
- `__pycache__/` and `*.pyc`

If one appears in staged changes, unstage it before committing.

## Commit Hygiene Rules

- One objective per commit.
- Keep snapshot updates separate from logic changes when possible.
- Do not include unrelated workspace noise in functional commits.
- Do not commit exploratory artifacts unless they are promoted to maintained tooling.

## Pre-Commit Validation

Run:

- `pwsh -File scripts/run_ci_verify.ps1`

If the environment does not have live Ghidra endpoint support, use:

- `pwsh -File scripts/run_ci_verify.ps1 --skip-static-baseline`

## Final Gate

Before commit, confirm:

- `git status --short` only lists files intended for this objective.
- No generated artifacts from the Always Ignored section are staged.
- CI verify is green for the selected mode.
