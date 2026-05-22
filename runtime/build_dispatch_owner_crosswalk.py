#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def edge(
    name: str,
    relation: str,
    source_struct: str,
    source_offset: str,
    target_struct: str,
    confidence: str,
    evidence: list[dict[str, str]],
    notes: list[str],
) -> dict:
    return {
        "name": name,
        "relation": relation,
        "source": {
            "struct": source_struct,
            "offset": source_offset,
        },
        "target": {
            "struct": target_struct,
        },
        "confidence": confidence,
        "evidence": evidence,
        "notes": notes,
    }


def evidence(address: str, function: str, instruction: str) -> dict:
    return {
        "address": address,
        "function": function,
        "instruction": instruction,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs" / "dwb_payload_dump"
    out_dir.mkdir(parents=True, exist_ok=True)

    out = {
        "program": "dwb_le_relocated_image.bin",
        "image_base": "0x00010000",
        "schema": "DispatchOwnerCrosswalkV1",
        "structs": [
            {
                "name": "ActorRuntimeStateLayoutV2",
                "role": "embedded actor runtime layout",
            },
            {
                "name": "ActorOwnerStateV1",
                "role": "owner state embedding actor runtime and owner-local control state",
            },
            {
                "name": "DispatchCursorV1",
                "role": "cursor consumed by FUN_0001f6a4",
            },
            {
                "name": "DispatchWrapperSlotV1",
                "role": "concrete wrapper datatype applied in Ghidra and used by FUN_0001f864",
            },
            {
                "name": "DispatchSelectorMatrixV1",
                "role": "owner-local dispatch selector matrix indexed by state row and facing column",
            },
        ],
        "edges": [
            edge(
                name="owner_embeds_actor",
                relation="embedded_prefix",
                source_struct="ActorOwnerStateV1",
                source_offset="0x00",
                target_struct="ActorRuntimeStateLayoutV2",
                confidence="high",
                evidence=[
                    evidence(
                        "0x00031b84",
                        "UpdateActorMovementAndTarget",
                        "ActorOwnerStateV1 typed as owner object with embedded actor prefix",
                    ),
                    evidence(
                        "0x00031b14",
                        "FUN_00031b14",
                        "ActorOwnerStateV1 typed as owner object with embedded actor prefix",
                    ),
                ],
                notes=[
                    "This edge reflects the active owner datatype already applied in Ghidra.",
                ],
            ),
            edge(
                name="cursor_points_to_owner",
                relation="direct_pointer",
                source_struct="DispatchCursorV1",
                source_offset="0x08",
                target_struct="ActorOwnerStateV1",
                confidence="high",
                evidence=[
                    evidence("0x0001f6f2", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                    evidence("0x0001f703", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                    evidence("0x0001f714", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                    evidence("0x0001f71f", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                    evidence("0x0001f734", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                    evidence("0x0001f755", "FUN_0001f6a4", "MOV EAX,dword ptr [ECX + 0x8]"),
                ],
                notes=[
                    "This is the direct owner-pointer edge already captured by the DispatchCursorV1 access matrix.",
                ],
            ),
            edge(
                name="owner_dispatch_selector_matrix",
                relation="indexed_lookup_base",
                source_struct="ActorOwnerStateV1",
                source_offset="0x128",
                target_struct="DispatchSelectorMatrixV1",
                confidence="high",
                evidence=[
                    evidence("0x00038678", "FUN_00038658", "MOV EDX,dword ptr [EBX + 0x50]"),
                    evidence("0x00038681", "FUN_00038658", "MOV EDX,dword ptr [EBX + 0x49]"),
                    evidence("0x00038687", "FUN_00038658", "MOV EDX,dword ptr [EAX + EDX*0x4 + 0x128]"),
                    evidence("0x00038692", "FUN_00038658", "CALL 0x00038544"),
                ],
                notes=[
                    "FUN_00038658 waits for owner + 0x70 to become non-zero, then indexes owner + 0x128 by a 0x10-byte row derived from the embedded actor's nMotion_or_wait_flag at owner + 0x50 and a 4-byte facing column derived from the high byte of owner + 0x49.",
                    "The looked-up dword is passed directly as the selector argument to FUN_00038544.",
                ],
            ),
            edge(
                name="owner_exposes_wrapper_slot",
                relation="embedded_substruct_base",
                source_struct="ActorOwnerStateV1",
                source_offset="0x74",
                target_struct="DispatchWrapperSlotV1",
                confidence="high",
                evidence=[
                    evidence("0x000385c7", "FUN_00038544", "LEA EAX,[ESI + 0x74]"),
                    evidence("0x000385ca", "FUN_00038544", "CALL 0x0001f864"),
                    evidence("0x00038735", "FUN_0003869c", "LEA EBP,[ESI + 0x74]"),
                    evidence("0x00038740", "FUN_0003869c", "CALL 0x0001f864"),
                ],
                notes=[
                    "Clean owner-side callsites consistently pass owner + 0x74 as the wrapper base to FUN_0001f864.",
                    "The owner field is now named dispatchWrapper in live Ghidra.",
                    "FUN_0003869c now carries an ActorOwnerStateV1 * prototype in Ghidra; FUN_00038544 was left untyped because an additional implicit BL input degraded decompilation when forced into a plain prototype.",
                ],
            ),
            edge(
                name="owner_dispatch_runtime_value",
                relation="register_argument_to_wrapper",
                source_struct="ActorOwnerStateV1",
                source_offset="0x70",
                target_struct="DispatchChainNodeV2",
                confidence="high",
                evidence=[
                    evidence("0x000385c4", "FUN_00038544", "MOV EDX,dword ptr [ESI + 0x70]"),
                    evidence("0x0003873b", "FUN_0003869c", "MOV EDX,dword ptr [ESI + 0x70]"),
                ],
                notes=[
                    "The value at owner + 0x70 is passed alongside the wrapper base into FUN_0001f864.",
                    "The owner field is now named pDispatch_chain_head in live Ghidra.",
                    "FUN_00038658 waits until this field becomes non-zero before dispatching, and FUN_00032278 consumes the same value as a linked chain head.",
                ],
            ),
            edge(
                name="wrapper_loads_cursor_pointer",
                relation="direct_pointer",
                source_struct="DispatchWrapperSlotV1",
                source_offset="0x04",
                target_struct="DispatchCursorV1",
                confidence="medium",
                evidence=[
                    evidence("0x0001f890", "FUN_0001f864", "MOV ECX,dword ptr [ECX + 0x4]"),
                    evidence("0x0001f8ac", "FUN_0001f864", "CALL 0x0001f6a4"),
                ],
                notes=[
                    "The clean mid-function handoff loads a pointer from wrapper + 0x04 immediately before calling FUN_0001f6a4.",
                    "Wrapper entry bytes are partially overlapping, so this edge is held at medium confidence until the prologue is fully stabilized.",
                ],
            ),
        ],
        "path_summary": [
            "ActorOwnerStateV1.pDispatch_chain_head@0x70 -> DispatchChainNodeV2 *",
            "ActorOwnerStateV1.dispatchWrapper@0x74 -> DispatchWrapperSlotV1",
            "ActorOwnerStateV1 + 0x128 -> DispatchSelectorMatrixV1 (state/facing-indexed selector table)",
            "DispatchWrapperSlotV1 + 0x04 -> DispatchCursorV1 *",
            "DispatchCursorV1 + 0x08 -> ActorOwnerStateV1 *",
            "ActorOwnerStateV1 + 0x00 -> ActorRuntimeStateLayoutV2",
        ],
    }

    out_path = out_dir / "dwb_dispatch_owner_crosswalk_v1.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()