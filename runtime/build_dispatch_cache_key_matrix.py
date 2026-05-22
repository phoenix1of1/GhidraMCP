#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def evidence(address: str, function: str, instruction: str, confidence: str = "high") -> dict:
    return {
        "address": address,
        "function": function,
        "instruction": instruction,
        "confidence": confidence,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs" / "dwb_payload_dump"
    out_dir.mkdir(parents=True, exist_ok=True)

    callers = [
        {
            "call_address": "0x00023e06",
            "function": "FUN_00023db4",
            "pre_call": [
                evidence("0x00023e06", "FUN_00023db4", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x00023e0e", "FUN_00023db4", "MOV dword ptr [EBX + 0xc], EAX"),
            ],
            "notes": [
                "Clean caller pattern stores the return value from 0x1fc78 into resolved header +0x0c.",
                "Decompilation now renders this store as DispatchResolvedResourceV1.dwDispatch_cache_key_0c.",
                "This caller then enters FUN_0001fad4 before FUN_00032068, so the cache-key store is part of a larger staged setup sequence rather than a terminal leaf action.",
            ],
        },
        {
            "call_address": "0x0002a2f7",
            "function": "sub_0002a2f7_containing_blob",
            "pre_call": [
                evidence("0x0002a2f0", "sub_0002a2f7_containing_blob", "CALL 0x00024fec"),
                evidence("0x0002a2f5", "sub_0002a2f7_containing_blob", "MOV EDX, EAX"),
                evidence("0x0002a2f7", "sub_0002a2f7_containing_blob", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x0002a302", "sub_0002a2f7_containing_blob", "MOV dword ptr [EDX + 0xc], EAX"),
            ],
            "notes": [
                "Raw disassembly window only; Ghidra does not currently define a clean containing function at this address.",
            ],
        },
        {
            "call_address": "0x0002a671",
            "function": "sub_0002a671_containing_blob",
            "pre_call": [
                evidence("0x0002a66a", "sub_0002a671_containing_blob", "CALL 0x00024fec"),
                evidence("0x0002a66f", "sub_0002a671_containing_blob", "MOV EDX, EAX"),
                evidence("0x0002a671", "sub_0002a671_containing_blob", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x0002a676", "sub_0002a671_containing_blob", "MOV dword ptr [EDX + 0xc], EAX"),
            ],
            "notes": [
                "Raw disassembly window only; Ghidra does not currently define a clean containing function at this address.",
            ],
        },
        {
            "call_address": "0x0002a9da",
            "function": "FUN_0002a9bc",
            "pre_call": [
                evidence("0x0002a9d3", "FUN_0002a9bc", "CALL 0x00024fec"),
                evidence("0x0002a9d8", "FUN_0002a9bc", "MOV EDX, EAX"),
                evidence("0x0002a9da", "FUN_0002a9bc", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x0002a9e5", "FUN_0002a9bc", "MOV dword ptr [EDX + 0xc], EAX"),
            ],
            "notes": [
                "Decompilation now renders the same store via DispatchResolvedResourceV1.dwDispatch_cache_key_0c.",
                "This caller also runs FUN_0001fad4 immediately afterward before continuing into FUN_00032068.",
            ],
        },
        {
            "call_address": "0x00028ded",
            "function": "FUN_00028d54",
            "pre_call": [
                evidence("0x00028de2", "FUN_00028d54", "MOV EDX, 0xe7"),
                evidence("0x00028de7", "FUN_00028d54", "MOV ECX, dword ptr [EAX + 0x18]"),
                evidence("0x00028dea", "FUN_00028d54", "MOV EBX, dword ptr [EAX + 0x14]"),
                evidence("0x00028ded", "FUN_00028d54", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x00028df2", "FUN_00028d54", "CALL 0x00032820"),
            ],
            "notes": [
                "Static dispatch helper path: this caller feeds the blob output indirectly into FUN_00032820 rather than storing through a resolved header pointer.",
            ],
        },
        {
            "call_address": "0x0002ab35",
            "function": "FUN_0002aab0",
            "pre_call": [
                evidence("0x0002ab2a", "FUN_0002aab0", "MOV EDX, 0xe4"),
                evidence("0x0002ab2f", "FUN_0002aab0", "MOV ECX, dword ptr [EAX + 0x18]"),
                evidence("0x0002ab32", "FUN_0002aab0", "MOV EBX, dword ptr [EAX + 0x14]"),
                evidence("0x0002ab35", "FUN_0002aab0", "CALL 0x0001fc78", "medium"),
            ],
            "post_call": [
                evidence("0x0002ab3a", "FUN_0002aab0", "CALL 0x00032820"),
            ],
            "notes": [
                "Second static dispatch helper path mirroring FUN_00028d54 with a different small EDX literal.",
            ],
        },
    ]

    out = {
        "program": "dwb_le_relocated_image.bin",
        "image_base": "0x00010000",
        "schema": "DispatchCacheKeyMatrixV1",
        "blob_address": "0x0001fc78",
        "register_contract": {
            "return_register": "EAX",
            "preserved_or_threaded_registers": [
                "EDX"
            ],
            "contract_notes": [
                "Dynamic callers move the resolved header pointer into EDX before calling 0x1fc78 and immediately reuse the same EDX value as the base for the [EDX + 0x0c] store after the call.",
                "Static callers preload EDX with small literals (0xe7, 0xe4) before calling 0x1fc78 and then pass that same live EDX state onward into FUN_00032820.",
                "Current evidence supports treating EAX as the produced dispatch cache key while EDX remains a threaded caller-owned context register."
            ]
        },
        "resolved_struct": {
            "name": "DispatchResolvedResourceV1",
            "cache_key_offset": "0x0c",
            "cache_key_name": "dwDispatch_cache_key_0c",
        },
        "blob_side_effects": [
            evidence("0x0001fc80", "raw_blob_0001fc78", "MOV [0x00013c9c], EAX", "low"),
            evidence("0x0001fc8b", "raw_blob_0001fc78", "MOV dword ptr [0x0005207c], EDX", "low"),
            evidence("0x0001fb65", "FUN_0001fafc", "ADC byte ptr [EBP + 0x5207c], AL", "medium"),
            evidence("0x0001fcbe", "FUN_0001fafc", "MOV EAX, [0x0005207c]", "medium"),
            evidence("0x0001fd63", "raw_blob_0001fd63", "ADD byte ptr [0x00013c9c], CL", "low"),
        ],
        "candidate_internal_substreams": [
            {
                "start_address": "0x0001fc80",
                "confidence": "low",
                "instructions": [
                    "MOV [0x00013c9c], EAX",
                    "RET",
                ],
                "notes": [
                    "This is a coherent overlapping decode beginning at 0x1fc80, but it is not the direct call target of the blob.",
                    "It matches the observed low-confidence global side effect on 0x13c9c.",
                ],
            },
            {
                "start_address": "0x0001fc88",
                "confidence": "low",
                "instructions": [
                    "PUSH EDX",
                    "XOR EDX, EDX",
                    "MOV dword ptr [0x0005207c], EDX",
                ],
                "notes": [
                    "This is the first clearly coherent instruction sequence after the overlapping entry bytes.",
                    "It supports the interpretation that 0x5207c participates in blob-local state management, but not yet enough to type it semantically.",
                ],
            },
            {
                "start_address": "0x0001fe6c",
                "confidence": "medium",
                "instructions": [
                    "MOV EAX, [0x0005207c]",
                    "RET",
                ],
                "notes": [
                    "No direct xrefs to 0x1fe6c are currently defined in Ghidra, so this remains a candidate helper boundary rather than a confirmed function.",
                    "The decode is coherent and pairs naturally with the FUN_0001fc88 reset/init entry that zeros 0x5207c.",
                ],
            },
        ],
        "direct_helper_entries": [
            {
                "address": "0x0001fc80",
                "function": "FUN_0001fc80",
                "confidence": "high",
                "summary": "Stores EAX into global 0x13c9c and returns.",
                "evidence": [
                    evidence("0x0001fc80", "FUN_0001fc80", "MOV [0x00013c9c], EAX"),
                    evidence("0x0001fc85", "FUN_0001fc80", "RET"),
                    evidence("0x00024afa", "FUN_00024a8c", "CALL 0x0001fc80"),
                    evidence("0x00024b34", "FUN_00024a8c", "CALL 0x0001fc80"),
                    evidence("0x0003914a", "FUN_000390ec", "MOV EAX, 0x1"),
                    evidence("0x0003914f", "FUN_000390ec", "CALL 0x0001fc80"),
                ],
                "notes": [
                    "Direct callers pass small control values in EAX (observed 0 and 1).",
                    "This entry is stronger than the overlapping-blob candidate status and should be treated as a real helper boundary.",
                ],
            },
            {
                "address": "0x0001fc88",
                "function": "FUN_0001fc88",
                "confidence": "medium",
                "summary": "Direct entry that zeroes blob-local globals before entering a still-noisy initialization path.",
                "evidence": [
                    evidence("0x0001fc88", "FUN_0001fc88", "PUSH EDX"),
                    evidence("0x0001fc89", "FUN_0001fc88", "XOR EDX, EDX"),
                    evidence("0x0001fc8b", "FUN_0001fc88", "MOV dword ptr [0x0005207c], EDX"),
                    evidence("0x00024c01", "FUN_00024c00", "CALL 0x0001fc88"),
                ],
                "notes": [
                    "Ghidra recognizes this as a function entry, but the body still overlaps noisier downstream bytes.",
                    "Keep this entry at medium confidence until more of the post-reset path is disentangled.",
                ],
            },
        ],
        "sibling_state_helpers": [
            {
                "global": "0x00013c9c",
                "writer": "FUN_0001fc80",
                "writer_confidence": "high",
                "notes": [
                    "Direct setter helper with observed caller values 0 and 1.",
                ],
            },
            {
                "global": "0x0005207c",
                "writer": "FUN_0001fc88",
                "writer_confidence": "medium",
                "reader_candidate": "0x0001fe6c",
                "reader_confidence": "medium",
                "notes": [
                    "The reset/init helper zeroes this global directly.",
                    "A coherent nearby MOV/RET stub reads the same global, but no direct xrefs to that stub are currently defined.",
                    "The containing blob also mutates the low byte arithmetically at 0x1fb65 and reads the full dword at 0x1fcbe, which is stronger evidence for a state word than for a pure boolean latch.",
                ],
            },
        ],
        "post_cache_pipeline": {
            "builder": {
                "function": "FUN_00031fe8",
                "summary": "Builds an unsorted DispatchChainNodeV2 singly linked list and returns its head in EAX.",
                "notes": [
                    "Dynamic callers copy the return value from EAX into EDX immediately after the call.",
                    "FUN_00031fe8 links nodes through pNext and terminates the chain with NULL.",
                    "Each node carries fixed16 X/Y deltas at offsets 0x08/0x0c and a propagated dispatch value at offset 0x10."
                ]
            },
            "slot_selector": {
                "function": "FUN_0001fad4",
                "summary": "Consumes a mode-like value in EAX and the current chain head in EDX, then returns a destination list-head slot in EAX.",
                "notes": [
                    "Observed callers commonly load EAX with 1 before calling FUN_0001fad4.",
                    "The dynamic and static paths both call FUN_0001fad4 immediately before FUN_00032068."
                ]
            },
            "walker": {
                "function": "FUN_00032068",
                "summary": "Walks the chain in EDX and reinserts each node into the list head slot pointed to by EAX.",
                "notes": [
                    "Raw disassembly shows FUN_00032068 preserving EAX as the list-head slot pointer and EDX as the current node pointer across each iteration.",
                    "Each iteration advances the current node through [node + 0x04], matching DispatchChainNodeV2.pNext."
                ]
            },
            "insert_helper": {
                "function": "FUN_00032528",
                "summary": "Sorted insertion helper for DispatchChainNodeV2 nodes.",
                "notes": [
                    "The helper writes the new node into the singly linked list anchored by the pointer passed in EAX.",
                    "Ordering compares the node dword at offset 0x10 first and the fixed16 Y delta at offset 0x0c second.",
                    "Current evidence therefore supports a primary sort on DispatchChainNodeV2.dwDispatch_value_10 with nDelta_y_fixed16 as the tie-breaker."
                ]
            },
            "dispatch_value_semantics": {
                "field": "DispatchChainNodeV2.dwDispatch_value_10",
                "confidence": "medium",
                "summary": "Packed ordering/control code propagated across the whole chain.",
                "notes": [
                    "FUN_00032278 overwrites this field across every node in the chain, so the final sorted key is often assigned after node construction rather than fixed at build time.",
                    "Observed propagated literals include 0x3de, 0x3e3, 0x3e4, 0xb, and 0xffffffff.",
                    "FUN_0001f46c computes a propagated value in 0x400-sized bands plus a caller-supplied offset before calling FUN_00032278, which is stronger evidence for a packed ordering code than for a simple phase id.",
                    "FUN_00032388 supplies one of those fine offsets by scanning the chain for the maximum of (nDelta_y_fixed16 >> 16) + nFrame_height_34 across resource-backed nodes, then returning that maximum minus 1.",
                    "That makes the low bits of the packed value look like a bottom-edge or depth cutoff term layered under a coarser 0x400-sized band.",
                    "FUN_000382f0 and FUN_00038544 propagate 0xffffffff through the chain when owner-side state indicates a special mode, supporting a control-sentinel interpretation for that specific value."
                ]
            }
        },
        "callers": callers,
        "notes": [
            "Every clean dynamic caller follows the same stable contract: resolve resource header, move the header pointer into EDX, call 0x1fc78, then store EAX into header +0x0c.",
            "The call-site contract is stronger than the blob-local disassembly: EAX behaves as the produced cache key and EDX remains live caller context across the call.",
            "The static helper callers differ only in that they thread the blob result onward into FUN_00032820 instead of immediately storing through a resolved header pointer.",
            "The blob entry at 0x1fc78 lands inside overlapping instruction flow, so call-site agreement is treated as stronger evidence than local linear disassembly.",
            "Current blob-local evidence supports treating 0x5207c as mutable state: one path zeroes it, another updates its low byte with ADC semantics, and a later site reads the full dword back into EAX.",
            "In at least two dynamic dispatch paths, cache-key computation is followed immediately by FUN_0001fad4 and then FUN_00032068, marking those calls as the next stable post-key stages.",
            "The broader post-key contract now looks like: FUN_00031fe8 builds a raw pNext chain, FUN_0001fad4 selects the destination head slot, and FUN_00032068/FUN_00032528 reorder the nodes into a sorted list keyed first by a packed dispatch ordering code and then by fixed16 Y delta.",
            "Current evidence suggests the packed ordering code combines a coarse 0x400-sized band with a fine depth term derived from the chain's maximum bottom edge."
        ],
    }

    out_path = out_dir / "dwb_dispatch_cache_key_matrix.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out_path), "caller_count": len(callers)}, indent=2))


if __name__ == "__main__":
    main()