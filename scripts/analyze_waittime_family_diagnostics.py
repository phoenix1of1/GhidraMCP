from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "playcomposite_confidence_probe"
DEFAULT_FAMILIES = [
    "tail2=PLAY>WAITTIME|stack_prefix_imm=4",
    "tail1=WAITTIME|stack_prefix_imm=4",
    "tail1=PLAYSAMPLE|stack_prefix_imm=4",
]


def _load_builder_module() -> Any:
    builder_path = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
    spec = importlib.util.spec_from_file_location("waittime_family_builder", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load builder module: {builder_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_imm_arg(args_display: str, name: str) -> int | None:
    match = re.search(rf"{re.escape(name)}=imm:([-0-9]+)", args_display or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_prefix_values(stack: str) -> list[int]:
    if not stack:
        return []
    tokens = [t.strip() for t in stack.split("|") if t.strip()]
    film_idx = -1
    for i, token in enumerate(tokens):
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_idx = i
            break
    if film_idx <= 0:
        return []
    out: list[int] = []
    for token in tokens[:film_idx]:
        if not token.startswith("imm:"):
            continue
        try:
            out.append(int(token[4:]))
        except ValueError:
            continue
    return out


def _play_event_mapping(base: Path, scene: str) -> list[dict[str, Any]]:
    stem = Path(scene).stem.lower()
    manifest_path = base / "play_first_export" / stem / "manifest.json"
    timeline_path = base / "scene_space_placement" / f"{stem}_scene_space_playback_timeline_full.csv"
    if not manifest_path.exists() or not timeline_path.exists():
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    play_events = [event for event in manifest.get("events", []) if event.get("preview_png")]
    timeline_rows = _read_csv(timeline_path)
    if not timeline_rows:
        return []

    # timeline row 0 is BACKGROUND when present; PLAY rows align with play_events order.
    play_rows = [row for row in timeline_rows if (row.get("libcall") or "").upper() == "PLAY"]
    count = min(len(play_events), len(play_rows))
    out: list[dict[str, Any]] = []
    for idx in range(count):
        event = play_events[idx]
        row = play_rows[idx]
        try:
            seq = int(event.get("seq") or -1)
        except ValueError:
            seq = -1
        out.append(
            {
                "index": idx,
                "seq": seq,
                "film": event.get("film_handle") or "",
                "x": int(row.get("x_used") or -1),
                "y": int(row.get("y_used") or -1),
                "source": row.get("position_source") or "",
                "confidence": row.get("placement_confidence") or "",
            }
        )
    return out


def _nearest_trusted_play(
    plays: list[dict[str, Any]],
    start_idx: int,
    direction: int,
) -> dict[str, Any] | None:
    idx = start_idx + direction
    while 0 <= idx < len(plays):
        row = plays[idx]
        if row["source"] != "fallback_visual_validation":
            return row
        idx += direction
    return None


def _nearest_dialogue_anchor(
    timeline_rows: list[dict[str, str]],
    scheduler_by_key: dict[tuple[str, str, int], dict[str, str]],
    scene: str,
    at_index: int,
    lookback: int,
    builder: Any,
) -> dict[str, Any] | None:
    start = max(0, at_index - lookback)
    for idx in range(at_index - 1, start - 1, -1):
        row = timeline_rows[idx]
        libcall = (row.get("libcall") or "").upper()
        args_display = row.get("args_display") or ""
        script = (row.get("script_handle") or "").upper()
        ip_text = row.get("ip") or ""
        ip = int(ip_text) if ip_text.isdigit() else -1

        if libcall == "TALKAT":
            anchor = builder._extract_talkat_anchor(args_display)
            if anchor is not None:
                return {
                    "type": "TALKAT",
                    "age": at_index - idx,
                    "x": anchor[0],
                    "y": anchor[1],
                    "ip": ip,
                }

        if libcall == "TALK" and ip >= 0:
            sched_row = scheduler_by_key.get((scene, script, ip))
            if sched_row is None:
                continue
            anchor = builder._extract_talk_anchor_from_visible_stack(sched_row.get("visible_stack") or "")
            if anchor is not None:
                return {
                    "type": "TALK",
                    "age": at_index - idx,
                    "x": anchor[0],
                    "y": anchor[1],
                    "ip": ip,
                }

    return None


def analyze(base: Path, target_families: list[str], lookback: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    residual_csv = base / "play_composite_export" / "play_composite_residual_skip_report.csv"
    shortlist_csv = base / "play_composite_export" / "residual_signature_shortlist.csv"
    scheduler_csv = base / "scheduler" / "scheduler_trace_events.csv"
    timeline_dir = base / "scene_timeline"

    for path in (residual_csv, shortlist_csv, scheduler_csv):
        if not path.exists():
            raise FileNotFoundError(path)
    if not timeline_dir.exists():
        raise FileNotFoundError(timeline_dir)

    builder = _load_builder_module()
    residual_rows = _read_csv(residual_csv)
    shortlist_rows = _read_csv(shortlist_csv)
    scheduler_rows = _read_csv(scheduler_csv)

    shortlist_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in shortlist_rows:
        scene = (row.get("scene") or "").upper()
        seq = row.get("seq") or ""
        shortlist_by_key[(scene, seq)] = row

    scheduler_by_key: dict[tuple[str, str, int], dict[str, str]] = {}
    for row in scheduler_rows:
        scene = (row.get("file") or "").upper()
        script = (row.get("script_handle") or "").upper()
        ip_text = row.get("ip") or ""
        if not script or not ip_text.isdigit():
            continue
        scheduler_by_key[(scene, script, int(ip_text))] = row

    timeline_rows_by_scene: dict[str, list[dict[str, str]]] = {}
    timeline_idx_by_scene_ip: dict[tuple[str, int], int] = {}
    for timeline_path in timeline_dir.glob("*_timeline.csv"):
        rows = _read_csv(timeline_path)
        scene = f"{timeline_path.stem.replace('_timeline', '').upper()}.SCN"
        timeline_rows_by_scene[scene] = rows
        for idx, row in enumerate(rows):
            ip_text = row.get("ip") or ""
            if ip_text.isdigit():
                timeline_idx_by_scene_ip[(scene, int(ip_text))] = idx

    plays_by_scene: dict[str, list[dict[str, Any]]] = {}
    seq_to_play_by_scene: dict[str, dict[int, dict[str, Any]]] = {}
    for scene in timeline_rows_by_scene.keys():
        plays = _play_event_mapping(base, scene)
        plays_by_scene[scene] = plays
        seq_to_play_by_scene[scene] = {row["seq"]: row for row in plays if row["seq"] >= 0}

    report_rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    carry_candidate_counts: Counter[str] = Counter()
    anchor_type_counts: Counter[str] = Counter()
    prefix_third_fourth: Counter[str] = Counter()
    source_histogram: Counter[str] = Counter()

    for residual in residual_rows:
        scene = (residual.get("scene") or "").upper()
        seq_text = residual.get("seq") or ""
        shortlist_row = shortlist_by_key.get((scene, seq_text))
        if shortlist_row is None:
            continue

        family_tail1 = shortlist_row.get("family_tail1") or ""
        family_tail2 = shortlist_row.get("family_tail2") or ""
        if family_tail1 not in target_families and family_tail2 not in target_families:
            continue

        ip_text = residual.get("ip") or ""
        if not ip_text.isdigit():
            continue
        ip = int(ip_text)
        script = (residual.get("script_handle") or "").upper()

        timeline_rows = timeline_rows_by_scene.get(scene, [])
        timeline_idx = timeline_idx_by_scene_ip.get((scene, ip), -1)
        sched_row = scheduler_by_key.get((scene, script, ip))
        visible_stack = (sched_row or {}).get("visible_stack") or ""
        prefix_values = _extract_prefix_values(visible_stack)
        prefix_anchor = builder._extract_scroll_prefix_anchor_from_visible_stack(visible_stack)

        try:
            seq = int(seq_text)
        except ValueError:
            seq = -1
        play_row = seq_to_play_by_scene.get(scene, {}).get(seq)
        play_idx = play_row["index"] if play_row is not None else -1
        plays = plays_by_scene.get(scene, [])

        prev_trusted = _nearest_trusted_play(plays, play_idx, -1) if play_idx >= 0 else None
        next_trusted = _nearest_trusted_play(plays, play_idx, +1) if play_idx >= 0 else None
        nearest_anchor = (
            _nearest_dialogue_anchor(
                timeline_rows,
                scheduler_by_key,
                scene,
                at_index=timeline_idx,
                lookback=lookback,
                builder=builder,
            )
            if timeline_idx >= 0
            else None
        )

        carry_viable = False
        if prev_trusted is not None and play_idx >= 0 and (play_idx - prev_trusted["index"]) <= 2:
            carry_viable = True

        family_key = family_tail2 if family_tail2 in target_families else family_tail1
        family_counts[family_key] += 1
        source_histogram[residual.get("position_source") or "nominal_play_args"] += 1
        carry_candidate_counts["carry_viable" if carry_viable else "carry_not_viable"] += 1
        if nearest_anchor is not None:
            anchor_type_counts[nearest_anchor["type"]] += 1
        else:
            anchor_type_counts["none"] += 1

        if len(prefix_values) >= 4:
            key = f"{prefix_values[2]}|{prefix_values[3]}"
            prefix_third_fourth[key] += 1
        else:
            prefix_third_fourth["<insufficient_prefix_values>"] += 1

        report_rows.append(
            {
                "scene": scene,
                "seq": seq_text,
                "script_handle": residual.get("script_handle") or "",
                "ip": ip,
                "film_handle": residual.get("film_handle") or "",
                "family_tail1": family_tail1,
                "family_tail2": family_tail2,
                "family_selected": family_key,
                "prev_libcalls": shortlist_row.get("prev_libcalls") or "",
                "stack_prefix_imm": shortlist_row.get("stack_prefix_imm") or "",
                "prefix_values": "|".join(str(v) for v in prefix_values),
                "prefix_anchor_candidate": "" if prefix_anchor is None else f"{prefix_anchor[0]},{prefix_anchor[1]}",
                "carry_viable": int(carry_viable),
                "prev_trusted_gap": "" if prev_trusted is None or play_idx < 0 else (play_idx - prev_trusted["index"]),
                "prev_trusted_source": "" if prev_trusted is None else prev_trusted["source"],
                "prev_trusted_xy": "" if prev_trusted is None else f"{prev_trusted['x']},{prev_trusted['y']}",
                "prev_trusted_film": "" if prev_trusted is None else prev_trusted["film"],
                "next_trusted_gap": "" if next_trusted is None or play_idx < 0 else (next_trusted["index"] - play_idx),
                "next_trusted_source": "" if next_trusted is None else next_trusted["source"],
                "next_trusted_xy": "" if next_trusted is None else f"{next_trusted['x']},{next_trusted['y']}",
                "next_trusted_film": "" if next_trusted is None else next_trusted["film"],
                "nearest_anchor_type": "" if nearest_anchor is None else nearest_anchor["type"],
                "nearest_anchor_age": "" if nearest_anchor is None else nearest_anchor["age"],
                "nearest_anchor_xy": "" if nearest_anchor is None else f"{nearest_anchor['x']},{nearest_anchor['y']}",
                "nearest_anchor_ip": "" if nearest_anchor is None else nearest_anchor["ip"],
            }
        )

    summary = {
        "base": str(base),
        "target_families": target_families,
        "rows_analyzed": len(report_rows),
        "family_counts": dict(family_counts.most_common()),
        "carry_viability_counts": dict(carry_candidate_counts.most_common()),
        "nearest_anchor_type_counts": dict(anchor_type_counts.most_common()),
        "prefix_third_fourth_histogram": dict(prefix_third_fourth.most_common()),
        "position_source_histogram": dict(source_histogram.most_common()),
    }
    return report_rows, summary


def write_outputs(base: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    out_csv = base / "play_composite_export" / "waittime_family_diagnostic_report.csv"
    out_json = base / "play_composite_export" / "waittime_family_diagnostic_summary.json"

    fieldnames = [
        "scene",
        "seq",
        "script_handle",
        "ip",
        "film_handle",
        "family_tail1",
        "family_tail2",
        "family_selected",
        "prev_libcalls",
        "stack_prefix_imm",
        "prefix_values",
        "prefix_anchor_candidate",
        "carry_viable",
        "prev_trusted_gap",
        "prev_trusted_source",
        "prev_trusted_xy",
        "prev_trusted_film",
        "next_trusted_gap",
        "next_trusted_source",
        "next_trusted_xy",
        "next_trusted_film",
        "nearest_anchor_type",
        "nearest_anchor_age",
        "nearest_anchor_xy",
        "nearest_anchor_ip",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_csv, out_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose recurring WAITTIME/PLAY residual families against trusted neighbors, dialogue anchors, and scheduler stack structure.",
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_BASE),
        help="Output base containing play_composite_export, scene_timeline, scheduler, play_first_export, and scene_space_placement.",
    )
    parser.add_argument(
        "--families",
        default=",".join(DEFAULT_FAMILIES),
        help="Comma-separated family signatures to include (matches family_tail1/family_tail2).",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=16,
        help="Timeline lookback window for nearest TALK/TALKAT anchor extraction.",
    )
    args = parser.parse_args()

    target_families = [item.strip() for item in str(args.families).split(",") if item.strip()]
    base = Path(args.base)
    rows, summary = analyze(base, target_families=target_families, lookback=args.lookback)
    out_csv, out_json = write_outputs(base, rows, summary)
    print(json.dumps({"csv": str(out_csv), "json": str(out_json), **summary}, indent=2))


if __name__ == "__main__":
    main()