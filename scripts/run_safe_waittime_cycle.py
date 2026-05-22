from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "full_playcomposite_pipeline"
DEFAULT_PROBE_REGISTRY = REPO_ROOT / "scripts" / "waittime_probe_registry.json"


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


def _load_probe_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "one_off_probes": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "one_off_probes": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "one_off_probes": {}}
    probes = payload.get("one_off_probes", {})
    if not isinstance(probes, dict):
        probes = {}
    return {
        "version": int(payload.get("version", 1)),
        "one_off_probes": probes,
    }


def _save_probe_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def _was_one_off_probed(registry: dict[str, Any], family: str) -> bool:
    probes = registry.get("one_off_probes", {})
    if not isinstance(probes, dict):
        return False
    entry = probes.get(family)
    return isinstance(entry, dict) and int(entry.get("attempts", 0)) > 0


def _record_one_off_probe_result(registry: dict[str, Any], family: str, result: dict[str, Any]) -> None:
    probes = registry.setdefault("one_off_probes", {})
    if not isinstance(probes, dict):
        probes = {}
        registry["one_off_probes"] = probes

    prev = probes.get(family, {}) if isinstance(probes.get(family), dict) else {}
    attempts = int(prev.get("attempts", 0)) + 1
    probes[family] = {
        "attempts": attempts,
        "last_status": result.get("status", ""),
        "last_exit_code": int(result.get("diagnostic_exit_code", 0)),
        "last_rows_analyzed": int(result.get("rows_analyzed", 0)),
        "last_carry_viability_counts": result.get("carry_viability_counts", {}),
        "last_nearest_anchor_type_counts": result.get("nearest_anchor_type_counts", {}),
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
    }


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
    parser.add_argument(
        "--allow-one-off-probe",
        action="store_true",
        help=(
            "When no safe candidate exists, allow one bounded probe from "
            "recommended_one_off_probes."
        ),
    )
    parser.add_argument(
        "--probe-force-retry",
        action="store_true",
        help="Allow retrying one-off probe families that were already attempted.",
    )
    parser.add_argument(
        "--probe-registry",
        type=Path,
        default=DEFAULT_PROBE_REGISTRY,
        help="Path to persistent one-off probe registry JSON.",
    )
    return parser


def _select_candidate(candidates: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    if strategy == "largest":
        return sorted(candidates, key=lambda c: (c.get("scene_count", 0), c.get("count", 0)), reverse=True)
    return sorted(candidates, key=lambda c: (c.get("scene_count", 0), c.get("count", 0)))


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
    registry_path = args.probe_registry.resolve()
    probe_registry = _load_probe_registry(registry_path)

    source = "safe_candidate"
    if not candidates and args.allow_one_off_probe:
        recommendations = summary.get("recommended_one_off_probes", [])
        if not args.probe_force_retry:
            recommendations = [
                item
                for item in recommendations
                if not _was_one_off_probed(probe_registry, str(item.get("family_signature", "")))
            ]
        candidates = recommendations
        source = "one_off_probe"

    if not candidates:
        skipped_reason = "none"
        if args.allow_one_off_probe:
            recommendations = summary.get("recommended_one_off_probes", [])
            skipped_reason = "no_recommended_one_off_probe" if not recommendations else "all_recommended_one_off_probes_already_tested"
        print(
            json.dumps(
                {
                    "status": "no_safe_candidate",
                    "triage_summary": str(summary_path),
                    "candidate_count": int(summary.get("candidate_count", 0)),
                    "rejected_counts": summary.get("rejected_counts", {}),
                    "rejected_examples": summary.get("rejected_examples", {}),
                    "recommended_one_off_probes": summary.get("recommended_one_off_probes", []),
                    "one_off_probe_enabled": bool(args.allow_one_off_probe),
                    "one_off_probe_skip_reason": skipped_reason,
                    "probe_registry": str(registry_path),
                    "action": "diagnostics_skipped",
                },
                indent=2,
            )
        )
        return 0

    candidates = _select_candidate(candidates, args.select)

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
        "selected_source": source,
        "selected_family": family,
        "selected_family_kind": selected.get("family_kind", ""),
        "selected_scene_count": selected.get("scene_count", 0),
        "selected_count": selected.get("count", 0),
        "triage_summary": str(summary_path),
        "diagnostic_exit_code": diag_rc,
    }

    if source == "one_off_probe":
        result["probe_registry"] = str(registry_path)

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

    if source == "one_off_probe":
        _record_one_off_probe_result(probe_registry, family, result)
        _save_probe_registry(registry_path, probe_registry)

    print(json.dumps(result, indent=2))
    return 0 if diag_rc == 0 else diag_rc


if __name__ == "__main__":
    raise SystemExit(main())
