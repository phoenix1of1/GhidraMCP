from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "full_playcomposite_pipeline"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_csv_arg(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def triage(
    base: Path,
    max_scene_count: int,
    require_tokens: list[str],
    exclude_families: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    shortlist_csv = base / "play_composite_export" / "residual_signature_shortlist.csv"
    if not shortlist_csv.exists():
        raise FileNotFoundError(shortlist_csv)

    rows = _read_csv(shortlist_csv)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        scene = (row.get("scene") or "").upper()
        for family_kind in ("tail1", "tail2"):
            signature = (row.get(f"family_{family_kind}") or "").strip()
            if not signature:
                continue
            key = (family_kind, signature)
            bucket = grouped.setdefault(
                key,
                {
                    "family_kind": family_kind,
                    "family_signature": signature,
                    "count": 0,
                    "scenes": set(),
                    "sample_rows": [],
                },
            )
            bucket["count"] += 1
            if scene:
                bucket["scenes"].add(scene)
            if len(bucket["sample_rows"]) < 5:
                bucket["sample_rows"].append(
                    {
                        "scene": scene,
                        "seq": row.get("seq") or "",
                        "ip": row.get("ip") or "",
                        "film_handle": row.get("film_handle") or "",
                    }
                )

    norm_tokens = [token.upper() for token in require_tokens]
    candidates: list[dict[str, Any]] = []
    rejected_counts = defaultdict(int)
    rejected_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def _record_rejection(reason: str, bucket: dict[str, Any], scene_count: int) -> None:
        rejected_counts[reason] += 1
        examples = rejected_examples[reason]
        if len(examples) >= 5:
            return
        examples.append(
            {
                "family_kind": bucket["family_kind"],
                "family_signature": bucket["family_signature"],
                "count": bucket["count"],
                "scene_count": scene_count,
                "scenes": sorted(bucket["scenes"]),
            }
        )

    for (_kind, _sig), bucket in grouped.items():
        signature = bucket["family_signature"]
        scene_count = len(bucket["scenes"])
        signature_upper = signature.upper()

        if signature in exclude_families:
            _record_rejection("excluded_already_tested", bucket, scene_count)
            continue
        if scene_count > max_scene_count:
            _record_rejection("too_broad_scene_count", bucket, scene_count)
            continue
        if norm_tokens and not any(token in signature_upper for token in norm_tokens):
            _record_rejection("missing_required_anchor_token", bucket, scene_count)
            continue

        candidates.append(
            {
                "family_kind": bucket["family_kind"],
                "family_signature": signature,
                "count": bucket["count"],
                "scene_count": scene_count,
                "scenes": sorted(bucket["scenes"]),
                "sample_rows": bucket["sample_rows"],
            }
        )

    candidates.sort(key=lambda item: (item["scene_count"], item["count"], item["family_kind"]), reverse=False)

    summary = {
        "base": str(base),
        "rows_read": len(rows),
        "family_signatures_seen": len(grouped),
        "max_scene_count": max_scene_count,
        "require_tokens": norm_tokens,
        "excluded_families_count": len(exclude_families),
        "candidate_count": len(candidates),
        "rejected_counts": dict(rejected_counts),
        "rejected_examples": dict(rejected_examples),
        "top_candidates": candidates[:10],
    }
    return candidates, summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Triage residual family signatures for narrow, anchor-token-matching "
            "diagnostic candidates."
        )
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_BASE,
        help="Pipeline base directory (default: outputs/full_playcomposite_pipeline).",
    )
    parser.add_argument(
        "--max-scene-count",
        type=int,
        default=2,
        help="Maximum unique scene count allowed for a candidate family.",
    )
    parser.add_argument(
        "--require-tokens",
        type=str,
        default="TALK,TALKAT",
        help="Comma-separated tokens that must appear in the family signature.",
    )
    parser.add_argument(
        "--exclude-families",
        type=str,
        default="",
        help="Comma-separated family signatures to skip (for already-tested families).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    require_tokens = _parse_csv_arg(args.require_tokens)
    exclude_families = set(_parse_csv_arg(args.exclude_families))
    candidates, summary = triage(
        base=args.base,
        max_scene_count=args.max_scene_count,
        require_tokens=require_tokens,
        exclude_families=exclude_families,
    )

    export_dir = args.base / "play_composite_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    out_json = export_dir / "waittime_frontier_candidate_summary.json"
    out_csv = export_dir / "waittime_frontier_candidates.csv"

    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "family_kind",
            "family_signature",
            "count",
            "scene_count",
            "scenes",
            "sample_scene",
            "sample_seq",
            "sample_ip",
            "sample_film_handle",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cand in candidates:
            sample = cand["sample_rows"][0] if cand["sample_rows"] else {}
            writer.writerow(
                {
                    "family_kind": cand["family_kind"],
                    "family_signature": cand["family_signature"],
                    "count": cand["count"],
                    "scene_count": cand["scene_count"],
                    "scenes": ",".join(cand["scenes"]),
                    "sample_scene": sample.get("scene") or "",
                    "sample_seq": sample.get("seq") or "",
                    "sample_ip": sample.get("ip") or "",
                    "sample_film_handle": sample.get("film_handle") or "",
                }
            )

    print(
        json.dumps(
            {
                "json": str(out_json),
                "csv": str(out_csv),
                "candidate_count": summary["candidate_count"],
                "top_candidates": summary["top_candidates"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
