#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FROZEN_BASE = REPO_ROOT / "outputs" / "frozen_waittime_replays" / "20260522_173948_auto_frozen_replay"


@dataclass
class MatrixIteration:
    family: str
    iteration: int
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _diag_signals(base: Path) -> tuple[int, int, int]:
    summary_path = base / "play_composite_export" / "waittime_family_diagnostic_summary.json"
    if not summary_path.exists():
        return 0, 0, 0
    payload: dict[str, Any] | None = None
    for _ in range(10):
        try:
            payload = _read_json(summary_path)
            break
        except json.JSONDecodeError:
            # Diagnostic writer is occasionally observed between truncate/write.
            time.sleep(0.1)
    if payload is None:
        return 0, 0, 0
    rows = int(payload.get("rows_analyzed") or 0)
    carry = int((payload.get("carry_viability_counts") or {}).get("carry_viable") or 0)
    talk = int((payload.get("nearest_anchor_type_counts") or {}).get("TALK") or 0)
    return rows, carry, talk


def _parse_families(raw: str) -> list[str]:
    items = [part.strip() for part in raw.split(",") if part.strip()]
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _load_top_families_from_shortlist(base: Path, limit: int, family_kind: str) -> list[str]:
    if limit <= 0:
        return []

    shortlist_json = base / "play_composite_export" / "residual_signature_shortlist.json"
    if not shortlist_json.exists():
        return []

    try:
        payload = _read_json(shortlist_json)
    except Exception:
        return []

    top = payload.get("top_family_signatures") or []
    out: list[str] = []
    for row in top:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("family_kind") or "")
        sig = str(row.get("family_signature") or "").strip()
        if not sig:
            continue
        if family_kind != "any" and kind != family_kind:
            continue
        out.append(sig)
        if len(out) >= limit:
            break
    return out


def _run_one(
    python_exe: str,
    frozen_base: Path,
    family: str,
    iteration: int,
) -> MatrixIteration:
    diag_cmd = [
        python_exe,
        "scripts/analyze_waittime_family_diagnostics.py",
        "--base",
        str(frozen_base),
        "--families",
        family,
    ]
    diag_rc, _ = _run(diag_cmd, REPO_ROOT)
    rows, carry, talk = _diag_signals(frozen_base)

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
    return MatrixIteration(
        family=family,
        iteration=iteration,
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
        description="Run a multi-family gated replay matrix against a single frozen waittime snapshot base."
    )
    p.add_argument("--python", default=sys.executable, help="Python executable for subprocesses.")
    p.add_argument("--frozen-base", type=Path, default=DEFAULT_FROZEN_BASE, help="Frozen snapshot base directory.")
    p.add_argument(
        "--families",
        type=str,
        default="",
        help="Comma-separated family signatures to evaluate on the same frozen base.",
    )
    p.add_argument(
        "--auto-top-families",
        type=int,
        default=0,
        help=(
            "Opt-in: also include top family signatures from residual_signature_shortlist.json "
            "up to this count. Default 0 keeps behavior unchanged."
        ),
    )
    p.add_argument(
        "--auto-family-kind",
        choices=["any", "tail1", "tail2"],
        default="any",
        help="When --auto-top-families is used, filter imported signatures by family kind.",
    )
    p.add_argument("--iterations", type=int, default=10, help="Iterations per family.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    frozen_base = args.frozen_base.resolve()

    if not frozen_base.exists():
        print(json.dumps({"status": "missing_frozen_base", "frozen_base": str(frozen_base)}, indent=2))
        return 2

    families = _parse_families(args.families)
    auto_families = _load_top_families_from_shortlist(
        frozen_base,
        limit=max(args.auto_top_families, 0),
        family_kind=args.auto_family_kind,
    )
    for fam in auto_families:
        if fam not in families:
            families.append(fam)

    if not families:
        print(
            json.dumps(
                {
                    "status": "no_families",
                    "families": args.families,
                    "auto_top_families": int(args.auto_top_families),
                },
                indent=2,
            )
        )
        return 2

    results: list[MatrixIteration] = []
    for family in families:
        for i in range(1, max(args.iterations, 0) + 1):
            results.append(_run_one(args.python, frozen_base, family, i))

    family_summaries: list[dict[str, Any]] = []
    for family in families:
        rows = [r for r in results if r.family == family]
        if not rows:
            continue
        all_pass = all(r.all_pass for r in rows)
        all_carry = all(r.carry_viable >= 1 for r in rows)
        all_talk = all(r.talk_anchors >= 1 for r in rows)
        decision = "PROMOTION_READY" if all_pass and all_carry and all_talk else "HOLD_NO_POLICY_CHANGE"
        family_summaries.append(
            {
                "family": family,
                "iterations": len(rows),
                "all_pass": all_pass,
                "all_carry": all_carry,
                "all_talk": all_talk,
                "decision": decision,
            }
        )

    summary = {
        "status": "completed",
        "frozen_base": str(frozen_base),
        "families": families,
        "auto_families": auto_families,
        "iterations_per_family": max(args.iterations, 0),
        "family_summaries": family_summaries,
        "matrix": [asdict(r) for r in results],
    }

    out_path = frozen_base / "play_composite_export" / "frozen_waittime_family_matrix_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({"status": "completed", "summary_path": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
