#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def access(offset: str, direction: str, address: str, function: str, instruction: str, confidence: str = "high") -> dict:
    return {
        "offset": offset,
        "direction": direction,
        "address": address,
        "function": function,
        "instruction": instruction,
        "confidence": confidence,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs" / "dwb_payload_dump"
    out_dir.mkdir(parents=True, exist_ok=True)

    accesses = [
        access("0x08", "read", "0x0001f6f2", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
        access("0x08", "read", "0x0001f703", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
        access("0x08", "read", "0x0001f714", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
        access("0x08", "read", "0x0001f71f", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
        access("0x08", "read", "0x0001f734", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
        access("0x08", "read", "0x0001f755", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),

        access("0x0c", "read", "0x0001f6ac", "FUN_0001f6a4", "MOV EAX,dword ptr [EAX + 0xc]"),

        access("0x10", "read", "0x0001f6b8", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x10]"),
        access("0x10", "read", "0x0001f6cf", "FUN_0001f6a4", "MOV EBX,dword ptr [ECX + 0x10]"),
        access("0x10", "write", "0x0001f6d5", "FUN_0001f6a4", "MOV dword ptr [ECX + 0x10],EBX"),
        access("0x10", "read", "0x0001f6df", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x10]"),
        access("0x10", "write", "0x0001f6e3", "FUN_0001f6a4", "MOV dword ptr [ECX + 0x10],EAX"),
        access("0x10", "write", "0x0001f6e9", "FUN_0001f6a4", "ADD dword ptr [ECX + 0x10],EAX"),
        access("0x10", "read", "0x0001f6ee", "FUN_0001f6a4", "MOV EBP,dword ptr [ECX + 0x10]"),
        access("0x10", "write", "0x0001f6f5", "FUN_0001f6a4", "MOV dword ptr [ECX + 0x10],EBP"),
    ]

    field_names = {
        "0x08": "dispatch_owner_ptr",
        "0x0c": "dispatch_resource_selector",
        "0x10": "dispatch_script_pc",
    }

    grouped = {}
    for item in accesses:
        offset = item["offset"]
        grouped.setdefault(
            offset,
            {
                "offset": offset,
                "name": field_names.get(offset, offset),
                "reads": [],
                "writes": [],
            },
        )
        if item["direction"] == "read":
            grouped[offset]["reads"].append(item)
        else:
            grouped[offset]["writes"].append(item)

    out = {
        "program": "dwb_le_relocated_image.bin",
        "image_base": "0x00010000",
        "struct": "DispatchCursorV1",
        "field_accesses": list(grouped.values()),
        "notes": [
            "Curated from clean disassembly window at 0x0001f6a4.",
            "0x0c access uses EAX base at entry and is interpreted as cursor resource-selector input to tinsel_resolve_resource_pointer.",
            "0x10 is used as an index into the resolved resource stream and is then incremented or relative-adjusted, so it behaves like a dispatch script/program counter rather than a plain ordinal.",
            "Function prototype remains void due calling-convention ambiguity in this noisy region; accesses are still valid evidence.",
        ],
    }

    out_path = out_dir / "dwb_dispatch_cursor_access_matrix.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out_path), "field_count": len(grouped), "access_count": len(accesses)}, indent=2))


if __name__ == "__main__":
    main()
