#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def entry(offset: str, name: str, direction: str, address: str, function: str, instruction: str, confidence: str) -> dict:
    return {
        "offset": offset,
        "name": name,
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
        entry("0x60", "owner_movement_reset_latch", "write", "0x00031c49", "UpdateActorMovementAndTarget", "MOV dword ptr [EDI + 0x60],0x0", "high"),
        entry("0x60", "owner_movement_reset_latch", "write", "0x00031e9f", "UpdateActorMovementAndTarget", "MOV dword ptr [EDI + 0x60],0x0", "high"),

        entry("0x64", "owner_fallback_motion_flag", "read", "0x00031d66", "UpdateActorMovementAndTarget", "CMP dword ptr [ESI + 0x64],0x0", "high"),

        entry("0x6c", "owner_helper_reset_guard", "write", "0x00031b48", "FUN_00031b14", "MOV dword ptr [ESI + 0x6c],0x0", "high"),

        entry("0x27c", "owner_control_state_27c", "read", "0x00031c6b", "UpdateActorMovementAndTarget", "MOV EBP,dword ptr [ESI + 0x27c]", "high"),
        entry("0x280", "owner_wait_delay_ticks", "read", "0x00031c7d", "UpdateActorMovementAndTarget", "MOV EDX,dword ptr [ESI + 0x280]", "medium"),
        entry("0x284", "owner_control_state_284", "read", "0x00031ba6", "UpdateActorMovementAndTarget", "MOV EDI,dword ptr [ESI + 0x284]", "high"),
        entry("0x284", "owner_control_state_284", "write", "0x00031c52", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x284],0x0", "high"),
    ]

    grouped = {}
    for item in accesses:
        offset = item["offset"]
        grouped.setdefault(
            offset,
            {
                "offset": offset,
                "name": item["name"],
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
        "owner_struct": "ActorOwnerStateV1",
        "field_accesses": list(grouped.values()),
        "notes": [
            "Curated from disassembly and typed decompilation in movement-owner slice.",
            "Offset evidence for 0x27c/0x280/0x284 is high confidence; only 0x280 currently has stronger behavioral semantics.",
            "When owner + 0x27c equals 1, UpdateActorMovementAndTarget increments a global tick counter and stalls until it reaches owner + 0x280, so 0x280 behaves like a per-owner wait-threshold in ticks.",
        ],
    }

    out_path = out_dir / "dwb_owner_control_access_matrix.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out_path), "field_count": len(grouped), "access_count": len(accesses)}, indent=2))


if __name__ == "__main__":
    main()
