#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

from tinsel1_vm_lite import LIBCALL_NAMES


BEHAVIOR_NOTES = {
    31: "SelectPlayEventTargetPoint builds four inward-offset region corners, scores them by Manhattan distance to the candidate point, and only accepts a corner when FUN_00035b14 succeeds for both adjacent background-region selector checks; on both the movement caller and the non-movement setup path at 0x2fd08, FUN_00037298 seeds a shared quad buffer, FUN_000370b0 precomputes min/max and per-edge line-test terms, and CheckBackgroundPointInside consumes that prepared state as a bounding-box reject followed by per-edge half-plane tests.",
    49: "SelectPlayEventTargetPoint builds four inward-offset region corners, scores them by Manhattan distance to the candidate point, and only accepts a corner when FUN_00035b14 succeeds for both adjacent background-region selector checks; on both the movement caller and the non-movement setup path at 0x2fd08, FUN_00037298 seeds a shared quad buffer, FUN_000370b0 precomputes min/max and per-edge line-test terms, and CheckBackgroundPointInside consumes that prepared state as a bounding-box reject followed by per-edge half-plane tests.",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    table_path = root / "outputs" / "dwb_payload_dump" / "dwb_libcall_table.json"
    out_csv = root / "outputs" / "dwb_payload_dump" / "dwb_libcall_crosswalk.csv"
    out_json = root / "outputs" / "dwb_payload_dump" / "dwb_libcall_crosswalk.json"

    table = json.loads(table_path.read_text(encoding="utf-8"))
    rows = []
    for e in table["entries"]:
        idx = int(e["index"])
        rows.append({
            "index": idx,
            "libcall_name": LIBCALL_NAMES.get(idx, f"LIB_{idx}"),
            "target_va": e["target_va"],
            "behavior_note": BEHAVIOR_NOTES.get(idx, ""),
        })

    out_json.write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["index", "libcall_name", "target_va", "behavior_note"])
        w.writeheader()
        w.writerows(rows)

    print(json.dumps({
        "count": len(rows),
        "csv": str(out_csv),
        "json": str(out_json),
        "sample": rows[:12],
    }, indent=2))


if __name__ == "__main__":
    main()
