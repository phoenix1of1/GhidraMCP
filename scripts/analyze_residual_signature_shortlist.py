from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "playcomposite_neighbor_carry_probe"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _stack_prefix_imm_count(stack: str) -> int:
    if not stack:
        return 0
    tokens = [t.strip() for t in stack.split("|") if t.strip()]
    film_idx = -1
    for i, token in enumerate(tokens):
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_idx = i
            break
    if film_idx <= 0:
        return 0
    count = 0
    for token in tokens[:film_idx]:
        if token.startswith("imm:"):
            count += 1
    return count


def _prev_libcalls(row_index: int, timeline_rows: list[dict[str, str]], window: int = 4) -> tuple[str, ...]:
    start = max(0, row_index - window)
    prior = timeline_rows[start:row_index]
    return tuple((r.get("libcall") or "").upper() for r in prior)


def _build_family_signature(prev: tuple[str, ...], prefix_imm: int, width: int) -> str:
    tail = prev[-width:] if prev else ()
    tail_key = ">".join(tail) if tail else "<START>"
    return f"tail{width}={tail_key}|stack_prefix_imm={prefix_imm}"


def _build_signature(row: dict[str, str], timeline_idx: int, timeline_rows: list[dict[str, str]], sched_row: dict[str, str] | None) -> str:
    prev = _prev_libcalls(timeline_idx, timeline_rows, window=4)
    prev_key = ">".join(prev) if prev else "<START>"
    stack = (sched_row or {}).get("visible_stack") or ""
    prefix_imm = _stack_prefix_imm_count(stack)
    waitframe_recent = "WAITFRAME" in prev
    scroll_recent = "SCROLL" in prev
    talk_recent = "TALK" in prev or "TALKAT" in prev
    return (
        f"prev={prev_key}"
        f"|scroll_recent={int(scroll_recent)}"
        f"|waitframe_recent={int(waitframe_recent)}"
        f"|talk_recent={int(talk_recent)}"
        f"|stack_prefix_imm={prefix_imm}"
    )


def analyze(base: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    residual_csv = base / "play_composite_export" / "play_composite_residual_skip_report.csv"
    timeline_dir = base / "scene_timeline"
    scheduler_csv = base / "scheduler" / "scheduler_trace_events.csv"

    for path in (residual_csv, scheduler_csv):
        if not path.exists():
            raise FileNotFoundError(path)
    if not timeline_dir.exists():
        raise FileNotFoundError(timeline_dir)

    residual_rows = _read_csv(residual_csv)
    scheduler_rows = _read_csv(scheduler_csv)

    # Build per-scene/script/ip scheduler lookup.
    scheduler_by_key: dict[tuple[str, str, int], dict[str, str]] = {}
    for row in scheduler_rows:
        scene = (row.get("file") or "").upper()
        script = (row.get("script_handle") or "").upper()
        ip_text = row.get("ip") or ""
        if not ip_text.isdigit():
            continue
        scheduler_by_key[(scene, script, int(ip_text))] = row

    # Load per-scene timeline rows and ip->index map.
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

    expanded: list[dict[str, Any]] = []
    sig_counter: Counter[str] = Counter()
    sig_scene_set: dict[str, set[str]] = defaultdict(set)
    sig_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    family_counters: dict[str, Counter[str]] = {
        "tail1": Counter(),
        "tail2": Counter(),
    }
    family_scene_sets: dict[str, dict[str, set[str]]] = {
        "tail1": defaultdict(set),
        "tail2": defaultdict(set),
    }
    family_rows: dict[str, dict[str, list[dict[str, Any]]]] = {
        "tail1": defaultdict(list),
        "tail2": defaultdict(list),
    }

    for residual in residual_rows:
        scene = (residual.get("scene") or "").upper()
        script = (residual.get("script_handle") or "").upper()
        ip_text = residual.get("ip") or ""
        if not ip_text.isdigit():
            continue
        ip = int(ip_text)

        timeline_rows = timeline_rows_by_scene.get(scene)
        timeline_idx = timeline_idx_by_scene_ip.get((scene, ip), -1)
        sched_row = scheduler_by_key.get((scene, script, ip))
        if timeline_rows is None or timeline_idx < 0:
            signature = "timeline_missing"
            prev = ""
        else:
            signature = _build_signature(residual, timeline_idx, timeline_rows, sched_row)
            prev = ">".join(_prev_libcalls(timeline_idx, timeline_rows, window=4))
        prev_tuple = tuple(p for p in prev.split(">") if p)
        prefix_imm = _stack_prefix_imm_count((sched_row or {}).get("visible_stack") or "")
        family_tail1 = _build_family_signature(prev_tuple, prefix_imm, width=1)
        family_tail2 = _build_family_signature(prev_tuple, prefix_imm, width=2)

        rec = {
            "scene": scene,
            "seq": residual.get("seq") or "",
            "script_handle": residual.get("script_handle") or "",
            "ip": ip,
            "film_handle": residual.get("film_handle") or "",
            "signature": signature,
            "prev_libcalls": prev,
            "stack_prefix_imm": prefix_imm,
            "family_tail1": family_tail1,
            "family_tail2": family_tail2,
        }
        expanded.append(rec)
        sig_counter[signature] += 1
        sig_scene_set[signature].add(scene)
        sig_rows[signature].append(rec)
        for family_kind, family_signature in (("tail1", family_tail1), ("tail2", family_tail2)):
            family_counters[family_kind][family_signature] += 1
            family_scene_sets[family_kind][family_signature].add(scene)
            family_rows[family_kind][family_signature].append(rec)

    ranked = []
    for signature, count in sig_counter.most_common():
        scenes = sorted(sig_scene_set[signature])
        # Prefer signatures recurring across scenes first, then by count.
        rank_score = (len(scenes), count)
        ranked.append(
            {
                "signature": signature,
                "count": count,
                "scene_count": len(scenes),
                "scenes": scenes,
                "rank_score": rank_score,
                "sample_rows": [
                    {
                        "scene": row["scene"],
                        "seq": row["seq"],
                        "ip": row["ip"],
                        "film_handle": row["film_handle"],
                    }
                    for row in sig_rows[signature][:5]
                ],
            }
        )

    ranked.sort(key=lambda r: (r["scene_count"], r["count"]), reverse=True)

    family_ranked = []
    for family_kind, counter in family_counters.items():
        for family_signature, count in counter.items():
            scenes = sorted(family_scene_sets[family_kind][family_signature])
            family_ranked.append(
                {
                    "family_kind": family_kind,
                    "family_signature": family_signature,
                    "count": count,
                    "scene_count": len(scenes),
                    "scenes": scenes,
                    "rank_score": (len(scenes), count),
                    "sample_rows": [
                        {
                            "scene": row["scene"],
                            "seq": row["seq"],
                            "ip": row["ip"],
                            "film_handle": row["film_handle"],
                        }
                        for row in family_rows[family_kind][family_signature][:5]
                    ],
                }
            )

    family_ranked.sort(key=lambda r: (r["scene_count"], r["count"], r["family_kind"]), reverse=True)

    summary = {
        "base": str(base),
        "residual_count": len(expanded),
        "distinct_signatures": len(ranked),
        "top_signatures": ranked[:10],
        "top_family_signatures": family_ranked[:10],
    }
    return expanded, summary


def write_outputs(base: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    out_csv = base / "play_composite_export" / "residual_signature_shortlist.csv"
    out_json = base / "play_composite_export" / "residual_signature_shortlist.json"

    fieldnames = [
        "scene",
        "seq",
        "script_handle",
        "ip",
        "film_handle",
        "signature",
        "prev_libcalls",
        "stack_prefix_imm",
        "family_tail1",
        "family_tail2",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_csv, out_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ranked residual signature shortlist from playcomposite outputs.")
    parser.add_argument("--base", default=str(DEFAULT_BASE), help="Output base containing residual, scheduler, and timeline artifacts")
    args = parser.parse_args()

    base = Path(args.base)
    rows, summary = analyze(base)
    out_csv, out_json = write_outputs(base, rows, summary)
    print(json.dumps({"csv": str(out_csv), "json": str(out_json), **summary}, indent=2))


if __name__ == "__main__":
    main()
