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

    # Curated from verified disassembly/decompilation evidence.
    accesses = [
        access("0x00", "read", "0x00031bde", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI]", "high"),
        access("0x00", "read", "0x00031ecf", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI]", "high"),
        access("0x00", "write", "0x00031b14", "FUN_00031b14", "*param_1 = param_2", "medium"),

        access("0x04", "read", "0x00031be9", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0x4]", "high"),
        access("0x04", "read", "0x00031ed5", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0x4]", "high"),
        access("0x04", "write", "0x00031b14", "FUN_00031b14", "param_1[1] = ...", "low"),

        access("0x08", "read", "0x00031c97", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0x8]", "high"),
        access("0x08", "write", "0x00031bcc", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x8],EAX", "high"),
        access("0x08", "write", "0x00031cf2", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x8],EAX", "high"),
        access("0x08", "write", "0x00031f06", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x8],EBX", "high"),

        access("0x0c", "read", "0x00031ca3", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0xc]", "high"),
        access("0x0c", "write", "0x00031cf5", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0xc],EAX", "high"),
        access("0x0c", "write", "0x00031f0f", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0xc],ECX", "high"),

        access("0x10", "write", "0x00031bd2", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x10],EAX", "high"),
        access("0x10", "read", "0x00031ee2", "UpdateActorMovementAndTarget", "MOV ECX,dword ptr [ESI + 0x10]", "high"),
        access("0x14", "write", "0x00031bc2", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x14],0xffffffff", "high"),
        access("0x14", "read", "0x00031edf", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0x14]", "high"),

        access("0x1c", "write", "0x00031bd8", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x1c],EAX", "high"),
        access("0x20", "write", "0x00031bc9", "UpdateActorMovementAndTarget", "MOV dword ptr [ESI + 0x20],0xffffffff", "high"),

        access("0x28", "read", "0x00031ef8", "UpdateActorMovementAndTarget", "MOV EDX,dword ptr [ESI + 0x28]", "high"),
        access("0x28", "write", "0x00036396", "ProcessWaitframeWaittimeState", "MOV dword ptr [EDX + 0x28],ESI", "medium"),
        access("0x28", "write", "0x000363a1", "ProcessWaitframeWaittimeState", "MOV dword ptr [EBP + 0x28],0x1", "medium"),

        access("0x2c", "read", "0x00031c9a", "UpdateActorMovementAndTarget", "MOV ECX,dword ptr [ESI + 0x2c]", "high"),
        access("0x2c", "read", "0x00031ced", "UpdateActorMovementAndTarget", "MOV ECX,dword ptr [ESI + 0x2c]", "high"),

        access("0x34", "write", "0x00031eff", "UpdateActorMovementAndTarget", "MOV byte ptr [ESI + 0x34],0x0", "high"),

        access("0x38", "read", "0x00038a51", "FUN_00038a44", "MOV ECX,dword ptr [EAX + 0x38]", "medium"),
        access("0x38", "read", "0x00038ac1", "FUN_00038a44", "CMP dword ptr [EDI + 0x21fd0],0xffffffff", "medium"),

        access("0x48", "read", "0x00031bee", "UpdateActorMovementAndTarget", "CMP dword ptr [ESI + 0x48],0x0", "medium"),
        access("0x48", "read", "0x00031e44", "UpdateActorMovementAndTarget", "CMP dword ptr [ESI + 0x48],0x0", "medium"),

        access("0x49", "read", "0x00031efb", "UpdateActorMovementAndTarget", "MOV EAX,dword ptr [ESI + 0x49]", "medium"),

        access("0x4c", "read", "0x00031c23", "UpdateActorMovementAndTarget", "CMP AL, byte ptr [ESI + 0x4c]", "medium"),
        access("0x4c", "read", "0x00031e79", "UpdateActorMovementAndTarget", "CMP AL, byte ptr [ESI + 0x4c]", "medium"),
        access("0x4c", "read", "0x00031f31", "UpdateActorMovementAndTarget", "CMP CL, byte ptr [ESI + 0x4c]", "medium"),
        access("0x4c", "write", "0x00038755", "FUN_0003869c", "MOV byte ptr [ESI + 0x4c],AL", "medium"),

        access("0x50", "read", "0x00031dc5", "UpdateActorMovementAndTarget", "MOV EBP,dword ptr [ESI + 0x50]", "medium"),
        access("0x50", "read", "0x00031f28", "UpdateActorMovementAndTarget", "MOV EBP,dword ptr [ESI + 0x50]", "medium"),
        access("0x50", "write", "0x00038752", "FUN_0003869c", "MOV dword ptr [ESI + 0x50],EDI", "medium"),

        access("0x54", "write", "0x00031b5a", "FUN_00031b14", "MOV dword ptr [ESI + 0x54],0x0", "high"),
        access("0x54", "read", "0x00031b68", "FUN_00031b14", "MOV EDX,dword ptr [ESI + 0x54]", "high"),
        access("0x54", "write", "0x00031b6f", "FUN_00031b14", "MOV dword ptr [ESI + 0x54],EDX", "high"),
        access("0x54", "write", "0x00031b77", "FUN_00031b14", "MOV dword ptr [ESI + 0x54],0x0", "high"),

        access("0x58", "read", "0x00031bdb", "UpdateActorMovementAndTarget", "MOV EDX,dword ptr [ESI + 0x58]", "high"),
        access("0x5c", "read", "0x00031be9", "UpdateActorMovementAndTarget", "CMP EAX,dword ptr [ESI + 0x5c]", "high"),

        access("0x08 (scene idx)", "read", "0x00035f95", "ComputeStandTargetPointAndSegment", "MOV EBX,dword ptr [EBX + 0x8]", "high"),
    ]

    field_names = {
        "0x00": "actor_current_x",
        "0x04": "actor_current_y",
        "0x08": "actor_target_x",
        "0x0c": "actor_target_y",
        "0x10": "actor_target_slot1_x",
        "0x14": "actor_target_slot1_y_or_id",
        "0x1c": "actor_target_slot2_x",
        "0x20": "actor_target_slot2_y_or_id",
        "0x28": "actor_motion_or_wait_flag",
        "0x2c": "actor_path_segment_id",
        "0x34": "actor_movement_phase_byte",
        "0x38": "actor_nearby_blocker_slot",
        "0x48": "actor_arrival_block_byte_or_flag",
        "0x49": "actor_anim_facing_packed",
        "0x4c": "actor_navigation_class_code",
        "0x50": "actor_motion_or_wait_state_id",
        "0x54": "actor_repath_retry_counter",
        "0x58": "actor_arrival_x",
        "0x5c": "actor_arrival_y",
        "0x08 (scene idx)": "scene_object_index",
    }

    grouped = {}
    for a in accesses:
        off = a["offset"]
        grouped.setdefault(off, {
            "offset": off,
            "name": field_names.get(off, off),
            "reads": [],
            "writes": [],
        })
        if a["direction"] == "read":
            grouped[off]["reads"].append(a)
        else:
            grouped[off]["writes"].append(a)

    out = {
        "program": "dwb_le_relocated_image.bin",
        "image_base": "0x00010000",
        "field_accesses": list(grouped.values()),
        "notes": [
            "Entries are currently curated from verified disassembly/decompilation in the active payload import.",
            "Confidence marks certainty of semantic meaning, not certainty of instruction address extraction.",
            "Actor + 0x38 is treated provisionally as a nearby-blocker slot: FUN_00038a44 only scans other active owner records when this field is -1, then filters for candidates with active dispatch chains and overlapping projected bounds.",
            "Actor + 0x4c is compared against the navigation-class byte returned by FUN_0002f12c; FUN_0003869c later writes the accepted class back to +0x4c after refreshing dispatch, so this field behaves like a cached background navigation-class selector.",
            "Actor + 0x50 is the compared state code returned by FUN_00036a24 and also the row key consumed by FUN_00038658's owner selector matrix; FUN_0003869c writes the accepted state back to +0x50 after refreshing dispatch, so it behaves like a cached motion/wait state id rather than a generic animation id.",
            "FUN_000301a8 consumes the current path-segment id and emits a candidate next waypoint/segment update; when both candidate segment ids already match the caller's current segment pair it clears its out step-status flag instead of reporting a transition.",
            "FUN_0002f12c sits one level above FUN_000301a8: it first asks FUN_00036bdc to translate the current region id into a one-byte background navigation class at resource offset +0x4c; only class 2 enters the waypoint-advancement loop, while every other classifier result is returned to the caller unchanged.",
        ],
    }

    out_path = out_dir / "dwb_actor_field_access_matrix.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out_path), "field_count": len(grouped), "access_count": len(accesses)}, indent=2))


if __name__ == "__main__":
    main()
