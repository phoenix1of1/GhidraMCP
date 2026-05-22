#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_BASE = REPO_ROOT / "outputs" / "full_playcomposite_pipeline"
DEFAULT_FROZEN_ROOT = REPO_ROOT / "outputs" / "frozen_waittime_replays"
DEFAULT_TARGET_FAMILY = "tail2=KILLTAG>PLAY|stack_prefix_imm=0"


@dataclass
class IterationResult:
    iteration: int
    family: str
    diagnostic_rc: int
    rows_analyzed: int
    carry_viable: int
    talk_anchors: int
    baseline_rc: int
    tests_rc: int
    all_pass: bool


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out


def _snapshot_copy(source_base: Path, frozen_root: Path, label: str) -> Path:
    frozen_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = frozen_root / f"{ts}_{label}"
    shutil.copytree(source_base, dest)
    return dest


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_discovery(python_exe: str, frozen_base: Path) -> dict[str, Any]:
    cmd = [
        python_exe,
        "scripts/run_safe_waittime_cycle.py",
        "--python",
        python_exe,
        "--base",
        str(frozen_base),
        "--allow-one-off-probe",
    ]
    rc, out = _run(cmd, REPO_ROOT)
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(out)
    except Exception:
        parsed = {
            "status": "parse_failed",
            "raw_output_tail": "\n".join(out.splitlines()[-40:]),
            "diagnostic_exit_code": rc,
        }
    return parsed


def _extract_diag_signals(summary_path: Path) -> tuple[int, int, int]:
    rows = 0
    carry = 0
    talk = 0
    if not summary_path.exists():
        return rows, carry, talk
    payload = _read_json(summary_path)
    rows = int(payload.get("rows_analyzed") or 0)
    carry = int((payload.get("carry_viability_counts") or {}).get("carry_viable") or 0)
    talk = int((payload.get("nearest_anchor_type_counts") or {}).get("TALK") or 0)
    return rows, carry, talk


def _run_iteration(
    i: int,
    python_exe: str,
    frozen_base: Path,
    family: str,
) -> IterationResult:
    diag_cmd = [
        python_exe,
        "scripts/analyze_waittime_family_diagnostics.py",
        "--base",
        str(frozen_base),
        "--families",
        family,
    ]
    diag_rc, _ = _run(diag_cmd, REPO_ROOT)

    diag_summary = frozen_base / "play_composite_export" / "waittime_family_diagnostic_summary.json"
    rows, carry, talk = _extract_diag_signals(diag_summary)

    baseline_cmd = [
        python_exe,
        "scripts/validate_static_progress_baseline.py",
        "--python",
        python_exe,
        "--pipeline-base",
        str(frozen_base),
    ]
    baseline_rc, _ = _run(baseline_cmd, REPO_ROOT)

    tests_cmd = [python_exe, "scripts/run_regression_tests.py"]
    tests_rc, _ = _run(tests_cmd, REPO_ROOT)

    all_pass = (diag_rc == 0) and (baseline_rc == 0) and (tests_rc == 0)
    return IterationResult(
        iteration=i,
        family=family,
        diagnostic_rc=diag_rc,
        rows_analyzed=rows,
        carry_viable=carry,
        talk_anchors=talk,
        baseline_rc=baseline_rc,
        tests_rc=tests_rc,
        all_pass=all_pass,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Create a frozen pipeline snapshot, run waittime discovery on that snapshot, "
            "and run gated replay iterations on the discovered (or forced) family."
        )
    )
    p.add_argument("--python", default=sys.executable, help="Python executable for subprocesses.")
    p.add_argument("--source-base", type=Path, default=DEFAULT_SOURCE_BASE, help="Pipeline base to snapshot.")
    p.add_argument("--frozen-root", type=Path, default=DEFAULT_FROZEN_ROOT, help="Root folder for frozen snapshots.")
    p.add_argument("--snapshot-label", type=str, default="waittime_protocol", help="Suffix label for snapshot folder.")
    p.add_argument("--iterations", type=int, default=10, help="Replay iterations to execute.")
    p.add_argument(
        "--family",
        type=str,
        default="",
        help="Override family for iterations. If omitted, discovery-selected family is used.",
    )
    p.add_argument(
        "--fallback-family",
        type=str,
        default=DEFAULT_TARGET_FAMILY,
        help="Family to use when discovery returns no selected family.",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    source_base = args.source_base.resolve()
    frozen_root = args.frozen_root.resolve()

    if not source_base.exists():
        print(json.dumps({"status": "missing_source_base", "source_base": str(source_base)}, indent=2))
        return 2

    frozen_base = _snapshot_copy(source_base, frozen_root, args.snapshot_label)

    shortlist_cmd = [
        args.python,
        "scripts/analyze_residual_signature_shortlist.py",
        "--base",
        str(frozen_base),
    ]
    shortlist_rc, shortlist_out = _run(shortlist_cmd, REPO_ROOT)

    discovery = _run_discovery(args.python, frozen_base)
    selected_family = str(discovery.get("selected_family") or "")
    if selected_family in {"", "none"}:
        selected_family = ""

    replay_family = args.family.strip() or selected_family or args.fallback_family

    iterations: list[IterationResult] = []
    for i in range(1, max(args.iterations, 0) + 1):
        iterations.append(_run_iteration(i, args.python, frozen_base, replay_family))

    all_stable = len(iterations) > 0 and all(item.all_pass for item in iterations)
    all_carry = len(iterations) > 0 and all(item.carry_viable >= 1 for item in iterations)
    all_talk = len(iterations) > 0 and all(item.talk_anchors >= 1 for item in iterations)
    decision = "PROMOTION_READY" if all_stable and all_carry and all_talk else "HOLD_NO_POLICY_CHANGE"

    summary = {
        "status": "completed",
        "source_base": str(source_base),
        "frozen_base": str(frozen_base),
        "shortlist_refresh": {
            "rc": shortlist_rc,
            "output_tail": "\n".join(shortlist_out.splitlines()[-20:]),
        },
        "discovery": discovery,
        "replay_family": replay_family,
        "iterations": [asdict(item) for item in iterations],
        "all_stable": all_stable,
        "all_carry": all_carry,
        "all_talk": all_talk,
        "decision": decision,
    }

    out_path = frozen_base / "play_composite_export" / "frozen_waittime_protocol_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({"summary_path": str(out_path), "decision": decision, "frozen_base": str(frozen_base)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
