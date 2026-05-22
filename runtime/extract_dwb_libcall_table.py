#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract DWB libcall dispatch table from relocated image")
    ap.add_argument("--image", required=True, help="Path to dwb_le_relocated_image.bin")
    ap.add_argument("--base", default="0x10000", help="Image base address (default 0x10000)")
    ap.add_argument("--table-va", default="0x25638", help="Dispatcher jump-table VA (default 0x25638)")
    ap.add_argument("--count", type=int, default=0x75, help="Table entry count (default 0x75 = 117)")
    ap.add_argument("--out-dir", required=True, help="Output directory")
    args = ap.parse_args()

    image_path = Path(args.image).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base = int(args.base, 0)
    table_va = int(args.table_va, 0)
    count = int(args.count)

    data = image_path.read_bytes()
    table_off = table_va - base
    if table_off < 0 or table_off + count * 4 > len(data):
        raise SystemExit(f"Table range out of file bounds: off=0x{table_off:x}, size={count*4}, file={len(data)}")

    rows = []
    for idx in range(count):
        raw = struct.unpack_from("<I", data, table_off + idx * 4)[0]
        target_va = raw
        rows.append({
            "index": idx,
            "target_va": f"0x{target_va:08x}",
            "target_addr": f"{target_va:08x}",
        })

    json_path = out_dir / "dwb_libcall_table.json"
    csv_path = out_dir / "dwb_libcall_table.csv"

    json_path.write_text(json.dumps({
        "image": str(image_path),
        "base": f"0x{base:x}",
        "table_va": f"0x{table_va:x}",
        "count": count,
        "entries": rows,
    }, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["index", "target_va", "target_addr"])
        w.writeheader()
        w.writerows(rows)

    print(json.dumps({
        "count": count,
        "table_va": f"0x{table_va:x}",
        "first_10": rows[:10],
        "json": str(json_path),
        "csv": str(csv_path),
    }, indent=2))


if __name__ == "__main__":
    main()
