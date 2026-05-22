#!/usr/bin/env python3
"""Dump relocated LE payload image/objects from Discworld DWB.EXE.

This is a Windows-friendly wrapper around runtime.dwb_le_loader.parse_le that:
- accepts explicit input/output paths,
- writes relocated full image and per-object binaries,
- emits a compact JSON manifest for Ghidra re-import.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dwb_le_loader import parse_le


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump relocated LE payloads from DWB.EXE")
    ap.add_argument(
        "--exe",
        required=True,
        help="Path to DWB.EXE",
    )
    ap.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for relocated image/object binaries",
    )
    args = ap.parse_args()

    exe = Path(args.exe).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    d, le, H, objs, _pm, data_start, minb, maxb, img, page_infos, relocs, errors = parse_le(exe)

    image_path = out_dir / "dwb_le_relocated_image.bin"
    image_path.write_bytes(img)

    object_files = []
    for obj in objs:
        start = obj["base"] - minb
        end = start + obj["vsize"]
        obj_bytes = img[start:end]
        obj_name = f"dwb_le_relocated_object{obj['index']:02d}.bin"
        obj_path = out_dir / obj_name
        obj_path.write_bytes(obj_bytes)
        object_files.append(
            {
                "index": obj["index"],
                "base": obj["base"],
                "vsize": obj["vsize"],
                "file": obj_name,
            }
        )

    manifest = {
        "input_exe": str(exe),
        "input_size": len(d),
        "le_offset": le,
        "data_start": data_start,
        "min_base": minb,
        "max_base": maxb,
        "entry_va": objs[H["csobj"] - 1]["base"] + H["eip"],
        "stack_va": objs[H["ssobj"] - 1]["base"] + H["esp"],
        "header": H,
        "objects": objs,
        "object_files": object_files,
        "page_count": len(page_infos),
        "reloc_count": len(relocs),
        "reloc_applied_count": sum(1 for r in relocs if r.get("applied")),
        "reloc_error_count": len(errors),
        "reloc_errors_sample": errors[:25],
        "outputs": {
            "relocated_image": image_path.name,
            "object_count": len(object_files),
        },
    }

    manifest_path = out_dir / "dwb_payload_dump_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps({
        "input_exe": manifest["input_exe"],
        "entry_va": hex(manifest["entry_va"]),
        "reloc_count": manifest["reloc_count"],
        "reloc_applied_count": manifest["reloc_applied_count"],
        "object_count": len(object_files),
        "output_dir": str(out_dir),
        "manifest": manifest_path.name,
    }, indent=2))


if __name__ == "__main__":
    main()
