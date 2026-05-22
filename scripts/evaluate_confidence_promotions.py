from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs" / "playcomposite_confidence_probe"


def evaluate(
    summary_path: Path,
    min_trusted_rows: int,
    require_zero_negative: bool,
) -> dict[str, Any]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    candidates = payload.get("confidence_promotion_candidates") or []

    promoted: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    for item in candidates:
        source = str(item.get("source") or "")
        trusted_rows = int(item.get("trusted_rows") or 0)
        negative_rows = int(item.get("negative_rows") or 0)

        reasons: list[str] = []
        if trusted_rows < min_trusted_rows:
            reasons.append(f"trusted_rows<{min_trusted_rows}")
        if require_zero_negative and negative_rows != 0:
            reasons.append("negative_rows_nonzero")

        decision = {
            "source": source,
            "trusted_rows": trusted_rows,
            "negative_rows": negative_rows,
            "decision": "promote" if not reasons else "defer",
            "reasons": reasons,
        }
        if not reasons:
            promoted.append(decision)
        else:
            deferred.append(decision)

    return {
        "summary_source": str(summary_path),
        "thresholds": {
            "min_trusted_rows": min_trusted_rows,
            "require_zero_negative": require_zero_negative,
        },
        "candidate_count": len(candidates),
        "promoted_count": len(promoted),
        "deferred_count": len(deferred),
        "promoted": promoted,
        "deferred": deferred,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate and materialize confidence-promotion decisions from residual summary artifacts.",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_BASE,
        help="Base output directory containing play_composite_export/play_composite_residual_skip_summary.json",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional explicit summary JSON path (overrides --base default summary location).",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Optional explicit promotion decision output JSON path.",
    )
    parser.add_argument(
        "--min-trusted-rows",
        type=int,
        default=2,
        help="Minimum trusted rows required to promote a source.",
    )
    parser.add_argument(
        "--allow-negative",
        action="store_true",
        help="Allow promotions even if negative generated rows are non-zero.",
    )
    args = parser.parse_args()

    base = args.base.resolve()
    summary_path = args.summary.resolve() if args.summary else base / "play_composite_export" / "play_composite_residual_skip_summary.json"
    out_json = args.out_json.resolve() if args.out_json else base / "play_composite_export" / "confidence_promotion_decisions.json"

    if not summary_path.exists():
        raise FileNotFoundError(summary_path)

    result = evaluate(
        summary_path=summary_path,
        min_trusted_rows=max(args.min_trusted_rows, 1),
        require_zero_negative=not args.allow_negative,
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), **result}, indent=2))


if __name__ == "__main__":
    main()
