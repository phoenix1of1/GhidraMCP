from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "playcomposite_scrollprefix_probe"
TARGET_SCENE = "CUTBARN.SCN"
TARGET_SCRIPT = "0X23847917"


def _load_builder_module() -> Any:
    builder_path = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
    spec = importlib.util.spec_from_file_location("cutbarn_scroll_prefix_builder", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load builder module: {builder_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _last_scroll_index(rows: list[dict[str, str]], play_idx: int) -> int:
    for idx in range(play_idx - 1, -1, -1):
        if (rows[idx].get("libcall") or "").upper() == "SCROLL":
            return idx
    return -1


def _classify_row(
    row: dict[str, str],
    timeline_rows: list[dict[str, str]],
    idx_by_ip: dict[int, int],
    scheduler_rows: dict[tuple[str, int], dict[str, str]],
    builder: Any,
) -> dict[str, Any]:
    ip = int(row["ip"])
    script = (row.get("script_handle") or "").strip().upper()
    timeline_idx = idx_by_ip.get(ip, -1)

    result: dict[str, Any] = {
        "scene": row.get("scene") or "",
        "seq": row.get("seq") or "",
        "script_handle": row.get("script_handle") or "",
        "ip": row.get("ip") or "",
        "film_handle": row.get("film_handle") or "",
        "reason": "unknown",
        "last_scroll_age": "",
        "candidate_x": "",
        "candidate_y": "",
    }

    if timeline_idx < 0:
        result["reason"] = "timeline_ip_missing"
        return result

    last_scroll_idx = _last_scroll_index(timeline_rows, timeline_idx)
    if last_scroll_idx < 0:
        result["reason"] = "no_prior_scroll"
        return result

    scroll_age = timeline_idx - last_scroll_idx
    result["last_scroll_age"] = scroll_age
    if scroll_age > int(builder.SCROLL_PREFIX_MAX_AGE):
        result["reason"] = "scroll_too_old"
        return result

    if (row.get("scene") or "").upper() != builder.CUTBARN_SCROLL_PREFIX_SCENE:
        result["reason"] = "scene_gate_miss"
        return result

    if script != builder.CUTBARN_SCROLL_PREFIX_SCRIPT:
        result["reason"] = "script_gate_miss"
        return result

    sched_key = (builder.CUTBARN_SCROLL_PREFIX_SCRIPT, ip)
    sched_row = scheduler_rows.get(sched_key)
    if sched_row is None:
        result["reason"] = "scheduler_row_missing"
        return result

    candidate = builder._extract_scroll_prefix_anchor_from_visible_stack(sched_row.get("visible_stack") or "")
    if candidate is None:
        result["reason"] = "no_plausible_prefix_pair"
        return result

    result["reason"] = "candidate_available"
    result["candidate_x"] = candidate[0]
    result["candidate_y"] = candidate[1]
    return result


def analyze(base: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    residual_csv = base / "play_composite_export" / "play_composite_residual_skip_report.csv"
    timeline_csv = base / "scene_timeline" / "CUTBARN_timeline.csv"
    scheduler_csv = base / "scheduler" / "scheduler_trace_events.csv"

    for path in (residual_csv, timeline_csv, scheduler_csv):
        if not path.exists():
            raise FileNotFoundError(path)

    builder = _load_builder_module()

    residual_rows = [r for r in _read_csv(residual_csv) if (r.get("scene") or "").upper() == TARGET_SCENE]
    timeline_rows = _read_csv(timeline_csv)
    scheduler_all = _read_csv(scheduler_csv)

    idx_by_ip = {int(r["ip"]): idx for idx, r in enumerate(timeline_rows) if (r.get("ip") or "").isdigit()}
    scheduler_rows: dict[tuple[str, int], dict[str, str]] = {}
    for row in scheduler_all:
        if (row.get("file") or "").upper() != TARGET_SCENE:
            continue
        script = (row.get("script_handle") or "").strip().upper()
        if not script:
            continue
        ip_text = row.get("ip") or ""
        if not ip_text.isdigit():
            continue
        scheduler_rows[(script, int(ip_text))] = row

    report_rows = [
        _classify_row(row, timeline_rows, idx_by_ip, scheduler_rows, builder)
        for row in sorted(residual_rows, key=lambda r: int(r.get("seq") or 0))
    ]

    reason_counts: dict[str, int] = {}
    for row in report_rows:
        reason = str(row["reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    summary = {
        "base": str(base),
        "scene": TARGET_SCENE,
        "residual_rows": len(report_rows),
        "reason_counts": reason_counts,
    }
    return report_rows, summary


def write_outputs(base: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    out_csv = base / "play_composite_export" / "cutbarn_scroll_prefix_rejection_report.csv"
    out_json = base / "play_composite_export" / "cutbarn_scroll_prefix_rejection_summary.json"

    fieldnames = [
        "scene",
        "seq",
        "script_handle",
        "ip",
        "film_handle",
        "reason",
        "last_scroll_age",
        "candidate_x",
        "candidate_y",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_csv, out_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze why CUTBARN residual rows do or do not pass timeline_scroll_prefix gating.",
    )
    parser.add_argument("--base", default=str(DEFAULT_BASE), help="Output base containing scene_timeline/scheduler/play_composite_export")
    args = parser.parse_args()

    base = Path(args.base)
    rows, summary = analyze(base)
    out_csv, out_json = write_outputs(base, rows, summary)
    print(json.dumps({"csv": str(out_csv), "json": str(out_json), **summary}, indent=2))


if __name__ == "__main__":
    main()
