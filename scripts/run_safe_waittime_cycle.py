from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "full_playcomposite_pipeline"


def _parse_csv(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one safety-first waittime cycle: triage candidates first, then run at most "
            "one family diagnostic if a candidate exists."
        )
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="Python executable used to invoke helper scripts.",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_BASE,
        help="Pipeline base directory.",
    )
    parser.add_argument(
        "--max-scene-count",
        type=int,
        default=2,
        help="Maximum scene_count allowed by triage.",
    )
    parser.add_argument(
        "--require-tokens",
        type=str,
        default="TALK,TALKAT",
        help="Comma-separated required signature tokens.",
    )
    parser.add_argument(
        "--exclude-families",
        type=str,
        default=(
            "tail2=WAITFRAME>TALK|stack_prefix_imm=2,"
            "tail1=TALK|stack_prefix_imm=0,"
            "tail2=TALK>TALK|stack_prefix_imm=0,"
            "tail2=PLAY>TALK|stack_prefix_imm=2"
        ),
        help="Comma-separated family signatures to skip as already tested.",
    )
    parser.add_argument(
        "--select",
        choices=("smallest", "largest"),
        default="smallest",
        help="Candidate selection strategy after triage.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    base = args.base.resolve()
    require_tokens = _parse_csv(args.require_tokens)
    exclude_families = _parse_csv(args.exclude_families)

    triage_cmd = [
        args.python,
        "scripts/triage_waittime_family_frontier.py",
        "--base",
        str(base),
        "--max-scene-count",
        str(args.max_scene_count),
        "--require-tokens",
        ",".join(require_tokens),
        "--exclude-families",
        ",".join(exclude_families),
    ]
    triage_rc, triage_output = _run(triage_cmd, REPO_ROOT)
    if triage_rc != 0:
        print(
            json.dumps(
                {
                    "status": "triage_failed",
                    "exit_code": triage_rc,
                    "output": triage_output,
                },
                indent=2,
            )
        )
        return triage_rc

    summary_path = base / "play_composite_export" / "waittime_frontier_candidate_summary.json"
    if not summary_path.exists():
        print(
            json.dumps(
                {
                    "status": "triage_summary_missing",
                    "summary": str(summary_path),
                },
                indent=2,
            )
        )
        return 2

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    candidates = summary.get("top_candidates", [])
    if not candidates:
        print(
            json.dumps(
                {
                    "status": "no_safe_candidate",
                    "triage_summary": str(summary_path),
                    "candidate_count": int(summary.get("candidate_count", 0)),
                    "rejected_counts": summary.get("rejected_counts", {}),
                    "rejected_examples": summary.get("rejected_examples", {}),
                    "action": "diagnostics_skipped",
                },
                indent=2,
            )
        )
        return 0

    if args.select == "largest":
        candidates = sorted(candidates, key=lambda c: (c.get("scene_count", 0), c.get("count", 0)), reverse=True)
    else:
        candidates = sorted(candidates, key=lambda c: (c.get("scene_count", 0), c.get("count", 0)))

    selected = candidates[0]
    family = selected["family_signature"]

    diag_cmd = [
        args.python,
        "scripts/analyze_waittime_family_diagnostics.py",
        "--base",
        str(base),
        "--families",
        family,
    ]
    diag_rc, diag_output = _run(diag_cmd, REPO_ROOT)

    result = {
        "status": "diagnostic_ran" if diag_rc == 0 else "diagnostic_failed",
        "selected_family": family,
        "selected_family_kind": selected.get("family_kind", ""),
        "selected_scene_count": selected.get("scene_count", 0),
        "selected_count": selected.get("count", 0),
        "triage_summary": str(summary_path),
        "diagnostic_exit_code": diag_rc,
    }

    diag_summary = base / "play_composite_export" / "waittime_family_diagnostic_summary.json"
    if diag_summary.exists():
        result["diagnostic_summary"] = str(diag_summary)
        try:
            diag_json = json.loads(diag_summary.read_text(encoding="utf-8"))
            result["carry_viability_counts"] = diag_json.get("carry_viability_counts", {})
            result["nearest_anchor_type_counts"] = diag_json.get("nearest_anchor_type_counts", {})
            result["rows_analyzed"] = diag_json.get("rows_analyzed", 0)
        except Exception:
            result["diagnostic_parse_error"] = "failed_to_parse_diagnostic_summary"

    if diag_output:
        result["diagnostic_output_tail"] = "\n".join(diag_output.splitlines()[-20:])

    print(json.dumps(result, indent=2))
    return 0 if diag_rc == 0 else diag_rc


if __name__ == "__main__":
    raise SystemExit(main())
