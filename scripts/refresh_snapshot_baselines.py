#!/usr/bin/env python3
"""Refresh deterministic regression snapshot baselines.

This utility regenerates committed snapshot JSON files used by regression tests.
It should be run intentionally after validated tool/runtime changes.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


SCENE_SET = ["BAR.SCN", "LIBRARY.SCN", "OBJECTS.SCN", "DW.SCN", "CLIMAX.SCN"]
SCHEDULER_LIBCALLS = {
    "BACKGROUND",
    "PLAY",
    "TOPPLAY",
    "SPLAY",
    "STAND",
    "SWALK",
    "WALK",
    "WAITFRAME",
    "WAITTIME",
    "EVENT",
    "CONTROL",
    "OFFSET",
    "SCROLL",
    "PLAYSAMPLE",
    "STOPSAMPLE",
    "SETTAG",
    "KILLTAG",
    "TAGACTOR",
    "TALK",
    "TALKAT",
    "PRINTOBJ",
    "PRINTTAG",
}
FILM_SCHEDULER_LIBCALLS = {"BACKGROUND", "PLAY", "TOPPLAY", "SPLAY"}
PLACEMENT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
BRANCH_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
INVENTORY_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
HOTSPOT_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
DIALOGUE_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
TIMING_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
CFG_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
LIBSIG_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
IR_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
STRUCT_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
SEMANTIC_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
SYMBOL_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
CANON_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
PSEUDO_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
EMIT_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
BUNDLE_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
DELTA_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
DIGEST_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
DELIVER_CONTRACT_SCENES = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
POLY_RECORD_SIZE_T1 = 104
CONTRACT_CORE_CALLS = ["PLAY", "WAITFRAME", "WAITTIME", "CONTROL", "TALK", "PLAYSAMPLE"]
BRANCH_MAX_STEPS = 1200
BRANCH_MAX_PATHS = 16
INVENTORY_LIBCALLS = {
    "INVENTORY",
    "ININVENTORY",
    "INWHICHINV",
    "WHICHINVENTORY",
    "ADDINV1",
    "ADDINV2",
    "ADDOPENINV",
    "DELINV",
    "SETINVLIMIT",
    "GETINVLIMIT",
    "SETINVSIZE",
    "HELDOBJECT",
    "OBJECTHELD",
    "SCANICON",
}
INVENTORY_MAX_STEPS = 1200
INVENTORY_MAX_PATHS = 16
HOTSPOT_POLY_TYPES = {5: "EXIT", 6: "TAG"}
HOTSPOT_LIBCALLS = {
    "CONVERSATION",
    "CONVTOPIC",
    "TALK",
    "TALKAT",
    "PRINTOBJ",
    "PRINTTAG",
    "SHOWSTRING",
    "SETTAG",
    "KILLTAG",
    "TAGACTOR",
    "UNTAGACTOR",
}
HOTSPOT_DISPATCH_TARGETS = {
    "TALK",
    "TALKAT",
    "PLAY",
    "INVENTORY",
    "ININVENTORY",
    "INWHICHINV",
    "WHICHINVENTORY",
}
HOTSPOT_MAX_STEPS = 1200
HOTSPOT_MAX_PATHS = 16
DIALOGUE_LIBCALLS = {
    "CONVERSATION",
    "CONVTOPIC",
    "ADDTOPIC",
    "TALK",
    "TALKAT",
    "TALKATS",
    "PRINTOBJ",
    "PRINTTAG",
    "SHOWSTRING",
}
DIALOGUE_ACTION_TARGETS = {
    "PLAY",
    "EVENT",
    "WAITFRAME",
    "WAITTIME",
    "INVENTORY",
    "ININVENTORY",
    "INWHICHINV",
    "WHICHINVENTORY",
}
DIALOGUE_MAX_STEPS = 1200
DIALOGUE_MAX_PATHS = 16
TIMING_WAIT_CALLS = {"WAITFRAME", "WAITTIME", "EVENT"}
TIMING_DIALOGUE_CALLS = {"CONVERSATION", "CONVTOPIC", "ADDTOPIC", "TALK", "TALKAT", "TALKATS"}
TIMING_PLAY_CALLS = {"PLAY", "TOPPLAY", "SPLAY", "STAND", "SWALK", "WALK"}
TIMING_MAX_STEPS = 1200
TIMING_MAX_PATHS = 16
CFG_EVENT_NAMES = {"jump", "conditional_jump"}
CFG_MAX_STEPS = 1200
CFG_MAX_PATHS = 16
LIBSIG_MAX_STEPS = 1200
LIBSIG_MAX_PATHS = 16
LIBSIG_MAX_CALLS = 30
LIBSIG_ARG_SHAPE_WINDOW = 6
IR_MAX_INS = 800
STRUCT_MAX_INS = 800
STRUCT_REGION_SIGNATURE_LIMIT = 60
SEMANTIC_MAX_STEPS = 1200
SEMANTIC_MAX_PATHS = 16
SEMANTIC_MAX_CALLS = 30
SEMANTIC_PSEUDOCODE_LINE_LIMIT = 48
SYMBOL_MAX_STEPS = 1200
SYMBOL_MAX_PATHS = 16
SYMBOL_MAX_SYMBOLS_PER_KIND = 40
SYMBOL_SUMMARY_HEAD_LIMIT = 60
CANON_REGISTRY_LIMIT = 80
CANON_ALIAS_HEAD_LIMIT = 80
PSEUDO_MAX_STEPS = 1200
PSEUDO_MAX_PATHS = 16
PSEUDO_LINE_HEAD_LIMIT = 80
EMIT_MAX_STEPS = 1200
EMIT_MAX_PATHS = 16
EMIT_MAX_BODY_LINES = 10
EMIT_FUNCTION_HEAD_LIMIT = 24
BUNDLE_MAX_STEPS = 1200
BUNDLE_MAX_PATHS = 16
BUNDLE_MAX_BODY_LINES = 32
BUNDLE_FUNCTION_LIMIT = 40
BUNDLE_TEXT_HEAD_LIMIT = 120
DELTA_CHANGE_HEAD_LIMIT = 80
DIGEST_HEAD_LIMIT = 80
DELIVER_TEXT_HEAD_LIMIT = 80
SEMANTIC_BEHAVIOR_TAGS = {
    "WAITFRAME": ["timing"],
    "WAITTIME": ["timing"],
    "EVENT": ["flow", "timing"],
    "PLAY": ["playback"],
    "TOPPLAY": ["playback"],
    "SPLAY": ["playback"],
    "STAND": ["playback"],
    "SWALK": ["playback"],
    "WALK": ["playback"],
    "BACKGROUND": ["render"],
    "CONTROL": ["flow"],
    "CONVERSATION": ["dialogue"],
    "CONVTOPIC": ["dialogue"],
    "ADDTOPIC": ["dialogue"],
    "TALK": ["dialogue"],
    "TALKAT": ["dialogue"],
    "TALKATS": ["dialogue"],
    "PRINTOBJ": ["dialogue", "ui"],
    "PRINTTAG": ["dialogue", "ui"],
    "SHOWSTRING": ["dialogue", "ui"],
    "INVENTORY": ["inventory", "ui"],
    "ININVENTORY": ["inventory"],
    "INWHICHINV": ["inventory"],
    "WHICHINVENTORY": ["inventory"],
    "ADDINV1": ["inventory"],
    "ADDINV2": ["inventory"],
    "ADDOPENINV": ["inventory"],
    "DELINV": ["inventory"],
    "SETINVLIMIT": ["inventory"],
    "GETINVLIMIT": ["inventory"],
    "SETINVSIZE": ["inventory"],
    "HELDOBJECT": ["inventory"],
    "OBJECTHELD": ["inventory"],
    "SCANICON": ["inventory", "ui"],
    "PLAYSAMPLE": ["audio"],
    "STOPSAMPLE": ["audio"],
    "SETTAG": ["tag"],
    "KILLTAG": ["tag"],
    "TAGACTOR": ["tag", "actor"],
    "UNTAGACTOR": ["tag", "actor"],
}
SEMANTIC_ARG_LABELS = {
    "PLAY": ["film", "x", "y", "flags"],
    "TOPPLAY": ["film", "x", "y", "flags"],
    "SPLAY": ["film", "x", "y", "flags"],
    "STAND": ["film", "x", "y", "flags"],
    "SWALK": ["film", "x", "y", "flags"],
    "WALK": ["film", "x", "y", "flags"],
    "WAITFRAME": ["frames"],
    "WAITTIME": ["ticks"],
    "EVENT": ["event_id"],
    "CONTROL": ["control_id", "value"],
    "TALK": ["actor", "text"],
    "TALKAT": ["actor", "x", "y", "text"],
    "TALKATS": ["actor", "x", "y", "text"],
    "CONVERSATION": ["conversation_id"],
    "CONVTOPIC": ["topic_id"],
    "ADDTOPIC": ["topic_id"],
    "INVENTORY": ["item_id"],
    "ININVENTORY": ["item_id"],
    "INWHICHINV": ["item_id"],
    "WHICHINVENTORY": ["item_id"],
    "ADDINV1": ["item_id"],
    "ADDINV2": ["item_id"],
    "ADDOPENINV": ["item_id"],
    "DELINV": ["item_id"],
}


def _load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_dataset_dir(repo_root: Path, explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).resolve()
        if (candidate / "INDEX").exists():
            return candidate
        raise FileNotFoundError(f"Provided --input has no INDEX file: {candidate}")

    candidates = [
        repo_root.parent / "clean-game" / "DISCWLD",
        repo_root.parent / "clean-game",
        repo_root / "sample_data",
    ]

    for candidate in candidates:
        if (candidate / "INDEX").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate default input with INDEX file. "
        "Tried: " + ", ".join(str(p) for p in candidates)
    )


def _build_scn_chunk_snapshots(extractor_mod, dataset_dir: Path) -> dict:
    out = {}
    for scene_name in SCENE_SET:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        chunks = list(extractor_mod.walk_chunks(data))
        out[scene_name] = {
            "file_size": len(data),
            "chunk_count": len(chunks),
            "chunk_ids": [c["chunk_id"] for c in chunks],
            "chunk_names": [c["chunk_name"] for c in chunks],
            "next_offsets": [c["next_offset"] for c in chunks],
        }
    return out


def _build_pcode_libcall_snapshots(scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = scanner_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in SCENE_SET:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts, films = scanner_mod.collect_script_handles(scene_path, idx_by_name)

        libcall_names = []
        opcode_names = []
        scripts_scanned = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = scanner_mod.handle_to_file_offset(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            result = scanner_mod.disassemble(data, offset, max_ins=800)
            scripts_scanned += 1
            libcall_names.extend(lc["libcall_name"] for lc in result["libcalls"])
            opcode_names.extend(ins["name"] for ins in result["instructions"])

        out[scene_name] = {
            "script_handles_found": len(scripts),
            "scripts_scanned": scripts_scanned,
            "icon_films_found": len(films),
            "libcall_count": len(libcall_names),
            "libcall_histogram": dict(sorted(collections.Counter(libcall_names).items())),
            "opcode_count": len(opcode_names),
            "opcode_histogram": dict(sorted(collections.Counter(opcode_names).items())),
        }

    return out


def _build_bitmap_checksum_snapshots(renderer_mod, dataset_dir: Path) -> dict:
    out = {}
    for scene_name in SCENE_SET:
        scene = renderer_mod.Tinsel1Scene(dataset_dir / scene_name)
        entries = []
        for rec in scene.image_records():
            if rec.width <= 0 or rec.height <= 0:
                continue

            indexed_pixels, stats = scene.render_wrt_nonzero(rec)
            palette = scene.palette(rec.palette_offset)
            rgba = bytearray()
            for pixel_index in indexed_pixels:
                rgba.extend(palette[pixel_index])

            entries.append(
                {
                    "index": rec.index,
                    "width": rec.width,
                    "height": rec.height,
                    "indexed_sha256": hashlib.sha256(bytes(indexed_pixels)).hexdigest(),
                    "rgba_sha256": hashlib.sha256(bytes(rgba)).hexdigest(),
                    "consumed_index_bytes": stats.consumed_index_bytes,
                }
            )
            if len(entries) >= 3:
                break

        out[scene_name] = entries

    return out


def _build_scheduler_event_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in SCENE_SET:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        all_libcalls = []
        scheduler_libcalls = []
        film_scheduler_with_args = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=1200, max_paths=16)
            for event in trace["events"]:
                if event.get("event") != "libcall":
                    continue

                libcall_name = event.get("libcall_name")
                all_libcalls.append(libcall_name)

                if libcall_name in SCHEDULER_LIBCALLS:
                    scheduler_libcalls.append(libcall_name)
                    if libcall_name in FILM_SCHEDULER_LIBCALLS and event.get("film_args"):
                        film_scheduler_with_args += 1

        out[scene_name] = {
            "script_handles_found": len(vm_mod.collect_script_handles(scene_path, idx_by_name)),
            "scripts_traced": len(scripts),
            "libcall_events_total": len(all_libcalls),
            "scheduler_event_count": len(scheduler_libcalls),
            "film_scheduler_events_with_film_args": film_scheduler_with_args,
            "scheduler_histogram": dict(sorted(collections.Counter(scheduler_libcalls).items())),
        }

    return out


def _build_scheduler_side_effect_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        scheduler_names: list[str] = []
        contracts: dict[str, dict] = {}
        scripts_with_scheduler_events = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=1200, max_paths=16)
            has_scheduler = False
            for event in trace["events"]:
                if event.get("event") != "libcall":
                    continue
                name = event.get("libcall_name")
                if name not in SCHEDULER_LIBCALLS:
                    continue

                has_scheduler = True
                scheduler_names.append(name)
                contract = contracts.setdefault(
                    name,
                    {
                        "count": 0,
                        "stack_depth_min": None,
                        "stack_depth_max": 0,
                        "film_args_nonempty_count": 0,
                    },
                )

                contract["count"] += 1
                depth = int(event.get("stack_depth") or 0)
                contract["stack_depth_min"] = depth if contract["stack_depth_min"] is None else min(contract["stack_depth_min"], depth)
                contract["stack_depth_max"] = max(contract["stack_depth_max"], depth)

                film_args = event.get("film_args") or []
                if isinstance(film_args, list) and len(film_args) > 0:
                    contract["film_args_nonempty_count"] += 1

            if has_scheduler:
                scripts_with_scheduler_events += 1

        for values in contracts.values():
            if values["stack_depth_min"] is None:
                values["stack_depth_min"] = 0

        transitions = collections.Counter()
        for i in range(len(scheduler_names) - 1):
            transitions[f"{scheduler_names[i]}->{scheduler_names[i + 1]}"] += 1

        for call in CONTRACT_CORE_CALLS:
            contracts.setdefault(
                call,
                {
                    "count": 0,
                    "stack_depth_min": 0,
                    "stack_depth_max": 0,
                    "film_args_nonempty_count": 0,
                },
            )

        sequence_head = scheduler_names[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_scheduler_events": scripts_with_scheduler_events,
            "scheduler_event_count": len(scheduler_names),
            "core_call_counts": {call: contracts[call]["count"] for call in CONTRACT_CORE_CALLS},
            "libcall_contracts": {key: contracts[key] for key in sorted(contracts.keys())},
            "transition_histogram": dict(sorted(transitions.items())),
            "sequence_head": sequence_head,
            "sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _path_depth(path_name: str | None) -> int:
    if not path_name:
        return 0
    return str(path_name).count(".br")


def _event_path_depth(event: dict) -> int:
    return _path_depth(event.get("path"))


def _state_path_depth(state: dict) -> int:
    return _path_depth(state.get("path"))


def _stack_token_kind(token: str) -> str:
    token = str(token or "")
    if token.startswith("imm:"):
        return "imm"
    if token.startswith("global:"):
        return "global"
    if token.startswith("local:"):
        return "local"
    if token.startswith("film:"):
        return "film"
    if token.startswith("cdfilm:"):
        return "cdfilm"
    if token.startswith("underflow"):
        return "underflow"
    return "expr"


def _arg_shape(stack_top: list, window: int = LIBSIG_ARG_SHAPE_WINDOW) -> str:
    if not stack_top:
        return "empty"
    suffix = stack_top[-window:]
    return ">".join(_stack_token_kind(token) for token in suffix)


def _ir_node_kind(opcode_name: str) -> str:
    if opcode_name == "LIBCALL":
        return "libcall"
    if opcode_name in {"HALT", "RET", "CALL", "JUMP", "JMPFALSE", "JMPTRUE"}:
        return "control"
    if opcode_name in {"IMM", "ZERO", "ONE", "MINUSONE", "LOAD", "GLOAD", "STORE", "GSTORE", "ALLOC", "DUP"}:
        return "stack"
    if opcode_name in {"FILM", "CDFILM", "STR", "FONT", "PAL", "CIMM"}:
        return "resource"
    if opcode_name in {"PLUS", "MINUS", "MULT", "DIV", "MOD", "NEG", "COMP"}:
        return "math"
    if opcode_name in {"EQUAL", "LESS", "LEQUAL", "NEQUAL", "GEQUAL", "GREAT", "LOR", "LAND", "NOT", "AND", "OR", "EOR"}:
        return "logic"
    if opcode_name in {"ESCON", "ESCOFF"}:
        return "state"
    return "unknown"


def _script_block_shapes(instructions: list[dict]) -> tuple[list[int], list[str]]:
    if not instructions:
        return [], []

    ip_to_index = {ins["ip"]: idx for idx, ins in enumerate(instructions)}
    leader_ips = {instructions[0]["ip"]}

    for idx, ins in enumerate(instructions):
        name = ins.get("name")
        if name not in {"JUMP", "JMPFALSE", "JMPTRUE"}:
            continue

        target = ins.get("operand")
        if isinstance(target, int) and target in ip_to_index:
            leader_ips.add(target)

        if idx + 1 < len(instructions):
            leader_ips.add(instructions[idx + 1]["ip"])

    leader_indices = sorted(ip_to_index[ip] for ip in leader_ips)

    block_sizes: list[int] = []
    block_terminators: list[str] = []
    for i, start_idx in enumerate(leader_indices):
        end_idx = leader_indices[i + 1] if i + 1 < len(leader_indices) else len(instructions)
        block = instructions[start_idx:end_idx]
        if not block:
            continue

        block_sizes.append(len(block))
        tail = block[-1].get("name")
        if tail == "JUMP":
            block_terminators.append("jump")
        elif tail in {"JMPFALSE", "JMPTRUE"}:
            block_terminators.append("conditional")
        elif tail == "HALT":
            block_terminators.append("halt")
        elif tail == "RET":
            block_terminators.append("ret")
        else:
            block_terminators.append("fallthrough")

    return block_sizes, block_terminators


def _script_structured_regions(instructions: list[dict]) -> list[dict]:
    if not instructions:
        return []

    ip_to_index = {ins["ip"]: idx for idx, ins in enumerate(instructions)}
    leader_ips = {instructions[0]["ip"]}

    for idx, ins in enumerate(instructions):
        name = ins.get("name")
        if name not in {"JUMP", "JMPFALSE", "JMPTRUE"}:
            continue

        target = ins.get("operand")
        if isinstance(target, int) and target in ip_to_index:
            leader_ips.add(target)

        if idx + 1 < len(instructions):
            leader_ips.add(instructions[idx + 1]["ip"])

    leader_indices = sorted(ip_to_index[ip] for ip in leader_ips)
    blocks: list[dict] = []
    for i, start_idx in enumerate(leader_indices):
        end_idx = leader_indices[i + 1] if i + 1 < len(leader_indices) else len(instructions)
        block = instructions[start_idx:end_idx]
        if not block:
            continue

        tail = block[-1].get("name")
        if tail == "JUMP":
            terminator = "jump"
        elif tail in {"JMPFALSE", "JMPTRUE"}:
            terminator = "conditional"
        elif tail == "HALT":
            terminator = "halt"
        elif tail == "RET":
            terminator = "ret"
        else:
            terminator = "fallthrough"

        blocks.append(
            {
                "index": len(blocks),
                "start_ip": block[0]["ip"],
                "end_ip": block[-1]["ip"],
                "size": len(block),
                "terminator": terminator,
                "tail_operand": block[-1].get("operand"),
            }
        )

    if not blocks:
        return []

    start_ip_to_block = {block["start_ip"]: block for block in blocks}

    for idx, block in enumerate(blocks):
        successors: list[int] = []
        term = block["terminator"]
        target = block.get("tail_operand")

        if term in {"jump", "conditional"} and isinstance(target, int):
            dest = start_ip_to_block.get(target)
            if dest is not None:
                successors.append(dest["index"])

        if term in {"conditional", "fallthrough"} and idx + 1 < len(blocks):
            successors.append(blocks[idx + 1]["index"])

        unique_successors = sorted(set(successors))
        block["successors"] = unique_successors
        block["fanout"] = len(unique_successors)
        block["has_backedge"] = any(dst <= block["index"] for dst in unique_successors)

    # Approximate nesting depth by longest acyclic conditional chain in forward edges.
    cache: dict[int, int] = {}

    def cond_depth(block_index: int) -> int:
        if block_index in cache:
            return cache[block_index]

        block = blocks[block_index]
        forward = [dst for dst in block["successors"] if dst > block_index]
        best = 0
        for dst in forward:
            best = max(best, cond_depth(dst))
        cache[block_index] = (1 if block["terminator"] == "conditional" else 0) + best
        return cache[block_index]

    max_conditional_depth = max(cond_depth(i) for i in range(len(blocks)))
    for block in blocks:
        block["max_conditional_depth"] = max_conditional_depth

    return blocks


def _semantic_behavior_tags(libcall_name: str) -> list[str]:
    if libcall_name in SEMANTIC_BEHAVIOR_TAGS:
        return list(SEMANTIC_BEHAVIOR_TAGS[libcall_name])

    upper = str(libcall_name or "").upper()
    inferred: list[str] = []
    if "INV" in upper:
        inferred.append("inventory")
    if upper.startswith("TALK") or upper.startswith("CONV"):
        inferred.append("dialogue")
    if upper.startswith("WAIT"):
        inferred.append("timing")
    if "PLAY" in upper:
        inferred.append("playback")
    if not inferred:
        inferred.append("state")
    return inferred


def _semantic_arg_labels(libcall_name: str, max_observed_arity: int) -> list[str]:
    if max_observed_arity <= 0:
        return []

    base = list(SEMANTIC_ARG_LABELS.get(libcall_name, []))
    labels = base[:max_observed_arity]
    while len(labels) < max_observed_arity:
        labels.append(f"arg{len(labels) + 1}")
    return labels


def _region_pseudocode_line(terminator: str, has_backedge: bool, primary_intent: str, region_calls: list[str]) -> str:
    if has_backedge:
        prefix = "loop"
    elif terminator == "conditional":
        prefix = "if cond"
    elif terminator in {"halt", "ret"}:
        prefix = "return"
    elif terminator == "jump":
        prefix = "goto"
    else:
        prefix = "step"

    if region_calls:
        call_phrase = ", ".join(region_calls[:2]).lower()
    else:
        call_phrase = "state"

    if prefix == "if cond":
        return f"if cond: {primary_intent} via {call_phrase}"
    return f"{prefix} {primary_intent} via {call_phrase}"


def _build_branch_convergence_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in BRANCH_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        max_branch_fanout = 0
        max_path_depth = 0
        truncated_paths_max_steps = 0
        truncated_paths_max_paths = 0
        branch_opcode_histogram = collections.Counter()

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=BRANCH_MAX_STEPS, max_paths=BRANCH_MAX_PATHS)
            events = trace.get("events", [])
            states = trace.get("final_states", [])

            for event in events:
                event_name = event.get("event")
                if event_name == "jump":
                    targets = event.get("targets") or []
                    max_branch_fanout = max(max_branch_fanout, len(targets))
                    branch_opcode_histogram["JUMP"] += 1
                elif event_name == "conditional_jump":
                    targets = event.get("targets") or []
                    max_branch_fanout = max(max_branch_fanout, len(targets))
                    opcode = event.get("opcode") or "COND"
                    branch_opcode_histogram[opcode] += 1

                max_path_depth = max(max_path_depth, _event_path_depth(event))

            for state in states:
                max_path_depth = max(max_path_depth, _state_path_depth(state))
                if int(state.get("steps") or 0) >= BRANCH_MAX_STEPS:
                    truncated_paths_max_steps += 1

            unknown_conditional_with_targets = sum(
                1
                for event in events
                if event.get("event") == "conditional_jump"
                and bool(event.get("targets"))
                and not str(event.get("condition") or "").startswith("imm:")
            )
            forks_created = max(0, int(trace.get("paths_started") or 1) - 1)
            prevented = max(0, unknown_conditional_with_targets - forks_created)
            truncated_paths_max_paths += prevented

        top_branch_opcodes = [name for name, _ in branch_opcode_histogram.most_common(8)]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "max_branch_fanout": max_branch_fanout,
            "max_path_depth": max_path_depth,
            "truncated_paths": {
                "max_steps": truncated_paths_max_steps,
                "max_paths": truncated_paths_max_paths,
                "total": truncated_paths_max_steps + truncated_paths_max_paths,
            },
            "branch_opcode_histogram": dict(sorted(branch_opcode_histogram.items())),
            "top_branch_opcodes": top_branch_opcodes,
            "top_branch_opcodes_sha256": hashlib.sha256("|".join(top_branch_opcodes).encode("utf-8")).hexdigest(),
        }

    return out


def _build_inventory_interaction_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in INVENTORY_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        inventory_sequence: list[str] = []
        inventory_sources = collections.Counter()
        inventory_histogram = collections.Counter()
        stack_depth_min: int | None = None
        stack_depth_max = 0
        max_path_depth_at_inventory_event = 0
        max_paths_started_for_inventory_scripts = 0
        scripts_with_inventory_events = 0

        inventory_script_handles_found = sum(
            1 for script in scripts if script.get("source") == "inventory.script"
        )

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(
                data,
                offset,
                max_steps=INVENTORY_MAX_STEPS,
                max_paths=INVENTORY_MAX_PATHS,
            )
            has_inventory = False
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue
                name = event.get("libcall_name")
                if name not in INVENTORY_LIBCALLS:
                    continue

                has_inventory = True
                inventory_sequence.append(name)
                inventory_histogram[name] += 1
                inventory_sources[script.get("source", "unknown")] += 1

                depth = int(event.get("stack_depth") or 0)
                stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
                stack_depth_max = max(stack_depth_max, depth)
                max_path_depth_at_inventory_event = max(
                    max_path_depth_at_inventory_event,
                    _event_path_depth(event),
                )

            if has_inventory:
                scripts_with_inventory_events += 1
                max_paths_started_for_inventory_scripts = max(
                    max_paths_started_for_inventory_scripts,
                    int(trace.get("paths_started") or 1),
                )

        transitions = collections.Counter()
        for i in range(len(inventory_sequence) - 1):
            transitions[f"{inventory_sequence[i]}->{inventory_sequence[i + 1]}"] += 1

        sequence_head = inventory_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "inventory_script_handles_found": inventory_script_handles_found,
            "scripts_with_inventory_events": scripts_with_inventory_events,
            "inventory_event_count": len(inventory_sequence),
            "inventory_libcall_histogram": dict(sorted(inventory_histogram.items())),
            "inventory_source_histogram": dict(sorted(inventory_sources.items())),
            "inventory_transition_histogram": dict(sorted(transitions.items())),
            "stack_depth_min": 0 if stack_depth_min is None else stack_depth_min,
            "stack_depth_max": stack_depth_max,
            "max_path_depth_at_inventory_event": max_path_depth_at_inventory_event,
            "max_paths_started_for_inventory_scripts": max_paths_started_for_inventory_scripts,
            "inventory_sequence_head": sequence_head,
            "inventory_sequence_head_sha256": hashlib.sha256(
                "|".join(sequence_head).encode("utf-8")
            ).hexdigest(),
        }

    return out


def _build_hotspot_interaction_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in HOTSPOT_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        polys = _parse_scene_polygons(data)
        hotspot_polys = [p for p in polys if p.get("type") in HOTSPOT_POLY_TYPES]
        hotspot_polygon_histogram = collections.Counter(HOTSPOT_POLY_TYPES[p["type"]] for p in hotspot_polys)
        hotspot_with_tagtext_count = sum(1 for p in hotspot_polys if int(p.get("h_tagtext") or 0) != 0)
        hotspot_with_id_count = sum(1 for p in hotspot_polys if int(p.get("id") or 0) != 0)

        all_hotspot_x = [x for p in hotspot_polys for x in p.get("x", [])]
        all_hotspot_y = [y for p in hotspot_polys for y in p.get("y", [])]
        hotspot_bounds = {
            "min_x": min(all_hotspot_x) if all_hotspot_x else None,
            "max_x": max(all_hotspot_x) if all_hotspot_x else None,
            "min_y": min(all_hotspot_y) if all_hotspot_y else None,
            "max_y": max(all_hotspot_y) if all_hotspot_y else None,
        }

        hotspot_sequence: list[str] = []
        all_libcall_sequence: list[str] = []
        hotspot_sources = collections.Counter()
        hotspot_histogram = collections.Counter()
        stack_depth_min: int | None = None
        stack_depth_max = 0
        max_path_depth_at_hotspot_event = 0
        max_paths_started_for_hotspot_scripts = 0
        scripts_with_hotspot_events = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(
                data,
                offset,
                max_steps=HOTSPOT_MAX_STEPS,
                max_paths=HOTSPOT_MAX_PATHS,
            )
            has_hotspot = False
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue

                name = event.get("libcall_name")
                if not name:
                    continue
                all_libcall_sequence.append(name)

                if name not in HOTSPOT_LIBCALLS:
                    continue

                has_hotspot = True
                hotspot_sequence.append(name)
                hotspot_histogram[name] += 1
                hotspot_sources[script.get("source", "unknown")] += 1

                depth = int(event.get("stack_depth") or 0)
                stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
                stack_depth_max = max(stack_depth_max, depth)
                max_path_depth_at_hotspot_event = max(
                    max_path_depth_at_hotspot_event,
                    _event_path_depth(event),
                )

            if has_hotspot:
                scripts_with_hotspot_events += 1
                max_paths_started_for_hotspot_scripts = max(
                    max_paths_started_for_hotspot_scripts,
                    int(trace.get("paths_started") or 1),
                )

        hotspot_transitions = collections.Counter()
        for i in range(len(hotspot_sequence) - 1):
            hotspot_transitions[f"{hotspot_sequence[i]}->{hotspot_sequence[i + 1]}"] += 1

        hotspot_to_dispatch_transitions = collections.Counter()
        for i in range(len(all_libcall_sequence) - 1):
            left = all_libcall_sequence[i]
            right = all_libcall_sequence[i + 1]
            if left in HOTSPOT_LIBCALLS and right in HOTSPOT_DISPATCH_TARGETS:
                hotspot_to_dispatch_transitions[f"{left}->{right}"] += 1

        sequence_head = hotspot_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_hotspot_events": scripts_with_hotspot_events,
            "hotspot_event_count": len(hotspot_sequence),
            "hotspot_polygon_count": len(hotspot_polys),
            "hotspot_polygon_histogram": dict(sorted(hotspot_polygon_histogram.items())),
            "hotspot_with_tagtext_count": hotspot_with_tagtext_count,
            "hotspot_with_id_count": hotspot_with_id_count,
            "hotspot_bounds": hotspot_bounds,
            "hotspot_libcall_histogram": dict(sorted(hotspot_histogram.items())),
            "hotspot_source_histogram": dict(sorted(hotspot_sources.items())),
            "hotspot_transition_histogram": dict(sorted(hotspot_transitions.items())),
            "hotspot_to_dispatch_transition_histogram": dict(sorted(hotspot_to_dispatch_transitions.items())),
            "stack_depth_min": 0 if stack_depth_min is None else stack_depth_min,
            "stack_depth_max": stack_depth_max,
            "max_path_depth_at_hotspot_event": max_path_depth_at_hotspot_event,
            "max_paths_started_for_hotspot_scripts": max_paths_started_for_hotspot_scripts,
            "hotspot_sequence_head": sequence_head,
            "hotspot_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _build_dialogue_topic_routing_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in DIALOGUE_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        dialogue_sequence: list[str] = []
        all_libcall_sequence: list[str] = []
        dialogue_sources = collections.Counter()
        dialogue_histogram = collections.Counter()
        stack_depth_min: int | None = None
        stack_depth_max = 0
        max_path_depth_at_dialogue_event = 0
        max_paths_started_for_dialogue_scripts = 0
        scripts_with_dialogue_events = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(
                data,
                offset,
                max_steps=DIALOGUE_MAX_STEPS,
                max_paths=DIALOGUE_MAX_PATHS,
            )
            has_dialogue = False
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue

                name = event.get("libcall_name")
                if not name:
                    continue
                all_libcall_sequence.append(name)

                if name not in DIALOGUE_LIBCALLS:
                    continue

                has_dialogue = True
                dialogue_sequence.append(name)
                dialogue_histogram[name] += 1
                dialogue_sources[script.get("source", "unknown")] += 1

                depth = int(event.get("stack_depth") or 0)
                stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
                stack_depth_max = max(stack_depth_max, depth)
                max_path_depth_at_dialogue_event = max(
                    max_path_depth_at_dialogue_event,
                    _event_path_depth(event),
                )

            if has_dialogue:
                scripts_with_dialogue_events += 1
                max_paths_started_for_dialogue_scripts = max(
                    max_paths_started_for_dialogue_scripts,
                    int(trace.get("paths_started") or 1),
                )

        dialogue_transitions = collections.Counter()
        for i in range(len(dialogue_sequence) - 1):
            dialogue_transitions[f"{dialogue_sequence[i]}->{dialogue_sequence[i + 1]}"] += 1

        hotspot_to_dialogue_transitions = collections.Counter()
        inventory_to_dialogue_transitions = collections.Counter()
        dialogue_to_action_transitions = collections.Counter()
        for i in range(len(all_libcall_sequence) - 1):
            left = all_libcall_sequence[i]
            right = all_libcall_sequence[i + 1]
            if left in HOTSPOT_LIBCALLS and right in DIALOGUE_LIBCALLS:
                hotspot_to_dialogue_transitions[f"{left}->{right}"] += 1
            if left in INVENTORY_LIBCALLS and right in DIALOGUE_LIBCALLS:
                inventory_to_dialogue_transitions[f"{left}->{right}"] += 1
            if left in DIALOGUE_LIBCALLS and right in DIALOGUE_ACTION_TARGETS:
                dialogue_to_action_transitions[f"{left}->{right}"] += 1

        sequence_head = dialogue_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_dialogue_events": scripts_with_dialogue_events,
            "dialogue_event_count": len(dialogue_sequence),
            "dialogue_libcall_histogram": dict(sorted(dialogue_histogram.items())),
            "dialogue_source_histogram": dict(sorted(dialogue_sources.items())),
            "dialogue_transition_histogram": dict(sorted(dialogue_transitions.items())),
            "hotspot_to_dialogue_transition_histogram": dict(sorted(hotspot_to_dialogue_transitions.items())),
            "inventory_to_dialogue_transition_histogram": dict(sorted(inventory_to_dialogue_transitions.items())),
            "dialogue_to_action_transition_histogram": dict(sorted(dialogue_to_action_transitions.items())),
            "stack_depth_min": 0 if stack_depth_min is None else stack_depth_min,
            "stack_depth_max": stack_depth_max,
            "max_path_depth_at_dialogue_event": max_path_depth_at_dialogue_event,
            "max_paths_started_for_dialogue_scripts": max_paths_started_for_dialogue_scripts,
            "dialogue_sequence_head": sequence_head,
            "dialogue_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _build_timing_wait_semantics_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in TIMING_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        wait_sequence: list[str] = []
        all_scheduler_sequence: list[str] = []
        wait_histogram = collections.Counter()
        wait_transitions = collections.Counter()
        dialogue_to_wait_transitions = collections.Counter()
        play_to_wait_transitions = collections.Counter()
        wait_to_event_transitions = collections.Counter()

        stack_depth_min: int | None = None
        stack_depth_max = 0
        max_path_depth_at_timing_event = 0
        max_paths_started_for_timing_scripts = 0
        scripts_with_timing_events = 0
        scheduler_event_count = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(
                data,
                offset,
                max_steps=TIMING_MAX_STEPS,
                max_paths=TIMING_MAX_PATHS,
            )
            has_timing = False
            local_scheduler_sequence: list[str] = []

            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue

                name = event.get("libcall_name")
                if not name:
                    continue
                if name in SCHEDULER_LIBCALLS:
                    scheduler_event_count += 1
                    all_scheduler_sequence.append(name)
                    local_scheduler_sequence.append(name)

                if name not in TIMING_WAIT_CALLS:
                    continue

                has_timing = True
                wait_sequence.append(name)
                wait_histogram[name] += 1

                depth = int(event.get("stack_depth") or 0)
                stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
                stack_depth_max = max(stack_depth_max, depth)
                max_path_depth_at_timing_event = max(
                    max_path_depth_at_timing_event,
                    _event_path_depth(event),
                )

            if has_timing:
                scripts_with_timing_events += 1
                max_paths_started_for_timing_scripts = max(
                    max_paths_started_for_timing_scripts,
                    int(trace.get("paths_started") or 1),
                )

            for i in range(len(local_scheduler_sequence) - 1):
                left = local_scheduler_sequence[i]
                right = local_scheduler_sequence[i + 1]
                if left in TIMING_DIALOGUE_CALLS and right in TIMING_WAIT_CALLS:
                    dialogue_to_wait_transitions[f"{left}->{right}"] += 1
                if left in TIMING_PLAY_CALLS and right in TIMING_WAIT_CALLS:
                    play_to_wait_transitions[f"{left}->{right}"] += 1
                if left in {"WAITFRAME", "WAITTIME"} and right == "EVENT":
                    wait_to_event_transitions[f"{left}->{right}"] += 1

        for i in range(len(wait_sequence) - 1):
            wait_transitions[f"{wait_sequence[i]}->{wait_sequence[i + 1]}"] += 1

        wait_count = len(wait_sequence)
        wait_density_per_million = (wait_count * 1_000_000) // scheduler_event_count if scheduler_event_count else 0
        sequence_head = wait_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_timing_events": scripts_with_timing_events,
            "timing_event_count": wait_count,
            "scheduler_event_count": scheduler_event_count,
            "wait_density_per_million": wait_density_per_million,
            "timing_wait_histogram": dict(sorted(wait_histogram.items())),
            "timing_wait_transition_histogram": dict(sorted(wait_transitions.items())),
            "dialogue_to_wait_transition_histogram": dict(sorted(dialogue_to_wait_transitions.items())),
            "play_to_wait_transition_histogram": dict(sorted(play_to_wait_transitions.items())),
            "wait_to_event_transition_histogram": dict(sorted(wait_to_event_transitions.items())),
            "stack_depth_min": 0 if stack_depth_min is None else stack_depth_min,
            "stack_depth_max": stack_depth_max,
            "max_path_depth_at_timing_event": max_path_depth_at_timing_event,
            "max_paths_started_for_timing_scripts": max_paths_started_for_timing_scripts,
            "timing_sequence_head": sequence_head,
            "timing_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _build_pcode_cfg_invariant_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in CFG_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        opcode_histogram = collections.Counter()
        branch_target_count_histogram = collections.Counter()
        cfg_transition_histogram = collections.Counter()
        cfg_sequence: list[str] = []

        scripts_with_cfg_events = 0
        scripts_with_multi_path = 0
        cfg_event_count = 0
        max_branch_fanout = 0
        max_paths_started = 0
        max_path_depth = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=CFG_MAX_STEPS, max_paths=CFG_MAX_PATHS)
            events = trace.get("events", [])
            states = trace.get("final_states", [])

            local_cfg_sequence: list[str] = []
            for event in events:
                max_path_depth = max(max_path_depth, _event_path_depth(event))
                event_name = event.get("event")
                if event_name not in CFG_EVENT_NAMES:
                    continue

                opcode = "JUMP" if event_name == "jump" else (event.get("opcode") or "COND")
                local_cfg_sequence.append(opcode)
                cfg_sequence.append(opcode)
                opcode_histogram[opcode] += 1
                cfg_event_count += 1

                targets = event.get("targets") or []
                fanout = len(targets)
                max_branch_fanout = max(max_branch_fanout, fanout)
                branch_target_count_histogram[fanout] += 1

            for state in states:
                max_path_depth = max(max_path_depth, _state_path_depth(state))

            for i in range(len(local_cfg_sequence) - 1):
                cfg_transition_histogram[f"{local_cfg_sequence[i]}->{local_cfg_sequence[i + 1]}"] += 1

            if local_cfg_sequence:
                scripts_with_cfg_events += 1
                paths_started = int(trace.get("paths_started") or 1)
                max_paths_started = max(max_paths_started, paths_started)
                if paths_started > 1:
                    scripts_with_multi_path += 1

        top_cfg_opcodes = [name for name, _ in opcode_histogram.most_common(8)]
        sequence_head = cfg_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_cfg_events": scripts_with_cfg_events,
            "scripts_with_multi_path": scripts_with_multi_path,
            "cfg_event_count": cfg_event_count,
            "max_branch_fanout": max_branch_fanout,
            "max_paths_started": max_paths_started,
            "max_path_depth": max_path_depth,
            "cfg_opcode_histogram": dict(sorted(opcode_histogram.items())),
            "cfg_target_count_histogram": {
                str(key): branch_target_count_histogram[key] for key in sorted(branch_target_count_histogram.keys())
            },
            "cfg_transition_histogram": dict(sorted(cfg_transition_histogram.items())),
            "top_cfg_opcodes": top_cfg_opcodes,
            "top_cfg_opcodes_sha256": hashlib.sha256("|".join(top_cfg_opcodes).encode("utf-8")).hexdigest(),
            "cfg_sequence_head": sequence_head,
            "cfg_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _build_pcode_libcall_signature_contract_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in LIBSIG_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        signatures: dict[str, dict] = {}
        predecessor_hist = collections.Counter()
        libcall_sequence: list[str] = []

        scripts_with_libcalls = 0
        max_path_depth_at_libcall = 0
        max_paths_started_for_libcall_scripts = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=LIBSIG_MAX_STEPS, max_paths=LIBSIG_MAX_PATHS)
            local_sequence: list[str] = []

            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue

                name = event.get("libcall_name")
                if not name:
                    continue

                local_sequence.append(name)
                libcall_sequence.append(name)
                max_path_depth_at_libcall = max(max_path_depth_at_libcall, _event_path_depth(event))

                signature = signatures.setdefault(
                    name,
                    {
                        "occurrence_count": 0,
                        "stack_depth_min": None,
                        "stack_depth_max": 0,
                        "observed_arg_count_histogram": collections.Counter(),
                        "arg_shape_histogram": collections.Counter(),
                    },
                )

                signature["occurrence_count"] += 1
                depth = int(event.get("stack_depth") or 0)
                signature["stack_depth_min"] = (
                    depth if signature["stack_depth_min"] is None else min(signature["stack_depth_min"], depth)
                )
                signature["stack_depth_max"] = max(signature["stack_depth_max"], depth)

                stack_top = event.get("stack_top") or []
                arg_count_candidate = len(stack_top)
                signature["observed_arg_count_histogram"][str(arg_count_candidate)] += 1
                signature["arg_shape_histogram"][_arg_shape(stack_top)] += 1

            if local_sequence:
                scripts_with_libcalls += 1
                max_paths_started_for_libcall_scripts = max(
                    max_paths_started_for_libcall_scripts,
                    int(trace.get("paths_started") or 1),
                )

            for i in range(1, len(local_sequence)):
                predecessor_hist[f"{local_sequence[i - 1]}->{local_sequence[i]}"] += 1

        ranked_calls = sorted(
            signatures.keys(),
            key=lambda name: (-signatures[name]["occurrence_count"], name),
        )[:LIBSIG_MAX_CALLS]

        libcall_contracts = {}
        for name in ranked_calls:
            signature = signatures[name]
            top_shapes = [shape for shape, _ in signature["arg_shape_histogram"].most_common(6)]
            libcall_contracts[name] = {
                "occurrence_count": signature["occurrence_count"],
                "stack_depth_min": 0 if signature["stack_depth_min"] is None else signature["stack_depth_min"],
                "stack_depth_max": signature["stack_depth_max"],
                "observed_arg_count_histogram": {
                    key: signature["observed_arg_count_histogram"][key]
                    for key in sorted(signature["observed_arg_count_histogram"].keys(), key=int)
                },
                "top_arg_shapes": top_shapes,
                "top_arg_shapes_sha256": hashlib.sha256("|".join(top_shapes).encode("utf-8")).hexdigest(),
            }

        sequence_head = libcall_sequence[:30]
        out[scene_name] = {
            "scripts_traced": len(scripts),
            "scripts_with_libcalls": scripts_with_libcalls,
            "libcall_event_count": len(libcall_sequence),
            "unique_libcall_count": len(signatures),
            "max_path_depth_at_libcall": max_path_depth_at_libcall,
            "max_paths_started_for_libcall_scripts": max_paths_started_for_libcall_scripts,
            "libcalls_ranked": ranked_calls,
            "libcall_signatures": {name: libcall_contracts[name] for name in sorted(libcall_contracts.keys())},
            "libcall_predecessor_transition_histogram": dict(sorted(predecessor_hist.items())),
            "libcall_sequence_head": sequence_head,
            "libcall_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
        }

    return out


def _build_pcode_ir_lift_snapshots(scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = scanner_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in IR_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts, films = scanner_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        node_kind_histogram = collections.Counter()
        opcode_histogram = collections.Counter()
        block_size_histogram = collections.Counter()
        block_terminator_histogram = collections.Counter()
        block_terminator_sequence: list[str] = []

        scripts_with_blocks = 0
        scripts_with_control_branches = 0
        libcall_annotated_node_count = 0
        instruction_count = 0
        block_count = 0
        max_block_size = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = scanner_mod.handle_to_file_offset(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            result = scanner_mod.disassemble(data, offset, max_ins=IR_MAX_INS)
            instructions = result.get("instructions", [])
            if not instructions:
                continue

            scripts_with_blocks += 1
            instruction_count += len(instructions)

            has_control_branch = False
            for ins in instructions:
                opcode_name = ins.get("name") or "OP_UNKNOWN"
                opcode_histogram[opcode_name] += 1
                node_kind_histogram[_ir_node_kind(opcode_name)] += 1
                if opcode_name == "LIBCALL":
                    libcall_annotated_node_count += 1
                if opcode_name in {"JUMP", "JMPFALSE", "JMPTRUE"}:
                    has_control_branch = True

            if has_control_branch:
                scripts_with_control_branches += 1

            block_sizes, block_terminators = _script_block_shapes(instructions)
            block_count += len(block_sizes)
            for size in block_sizes:
                block_size_histogram[str(size)] += 1
                max_block_size = max(max_block_size, size)
            for term in block_terminators:
                block_terminator_histogram[term] += 1
                block_terminator_sequence.append(term)

        top_ir_node_kinds = [name for name, _ in node_kind_histogram.most_common(8)]
        top_ir_opcodes = [name for name, _ in opcode_histogram.most_common(12)]
        sequence_head = block_terminator_sequence[:40]
        out[scene_name] = {
            "script_handles_found": len(scripts),
            "icon_films_found": len(films),
            "scripts_with_blocks": scripts_with_blocks,
            "scripts_with_control_branches": scripts_with_control_branches,
            "instruction_count": instruction_count,
            "block_count": block_count,
            "max_block_size": max_block_size,
            "libcall_annotated_node_count": libcall_annotated_node_count,
            "ir_node_kind_histogram": dict(sorted(node_kind_histogram.items())),
            "ir_opcode_histogram": dict(sorted(opcode_histogram.items())),
            "ir_block_size_histogram": {
                key: block_size_histogram[key] for key in sorted(block_size_histogram.keys(), key=int)
            },
            "ir_block_terminator_histogram": dict(sorted(block_terminator_histogram.items())),
            "top_ir_node_kinds": top_ir_node_kinds,
            "top_ir_node_kinds_sha256": hashlib.sha256("|".join(top_ir_node_kinds).encode("utf-8")).hexdigest(),
            "top_ir_opcodes": top_ir_opcodes,
            "top_ir_opcodes_sha256": hashlib.sha256("|".join(top_ir_opcodes).encode("utf-8")).hexdigest(),
            "ir_block_terminator_sequence_head": sequence_head,
            "ir_block_terminator_sequence_head_sha256": hashlib.sha256(
                "|".join(sequence_head).encode("utf-8")
            ).hexdigest(),
        }

    return out


def _build_pcode_structuring_snapshots(scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = scanner_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in STRUCT_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts, films = scanner_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        terminator_histogram = collections.Counter()
        region_size_histogram = collections.Counter()
        region_signature_histogram = collections.Counter()
        region_sequence: list[str] = []

        scripts_with_regions = 0
        scripts_with_loops = 0
        region_count = 0
        loop_region_count = 0
        conditional_region_count = 0
        max_region_size = 0
        max_cfg_fanout = 0
        max_conditional_nesting = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = scanner_mod.handle_to_file_offset(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            result = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = result.get("instructions", [])
            regions = _script_structured_regions(instructions)
            if not regions:
                continue

            scripts_with_regions += 1
            script_has_loop = False
            for region in regions:
                region_count += 1
                terminator = region["terminator"]
                size = int(region["size"])
                fanout = int(region["fanout"])
                has_backedge = bool(region["has_backedge"])

                terminator_histogram[terminator] += 1
                region_size_histogram[str(size)] += 1
                max_region_size = max(max_region_size, size)
                max_cfg_fanout = max(max_cfg_fanout, fanout)
                max_conditional_nesting = max(max_conditional_nesting, int(region["max_conditional_depth"]))

                if terminator == "conditional":
                    conditional_region_count += 1
                if has_backedge:
                    loop_region_count += 1
                    script_has_loop = True

                signature = f"{terminator}:{fanout}:{'loop' if has_backedge else 'plain'}"
                region_signature_histogram[signature] += 1
                region_sequence.append(signature)

            if script_has_loop:
                scripts_with_loops += 1

        top_region_signatures = [name for name, _ in region_signature_histogram.most_common(12)]
        sequence_head = region_sequence[:STRUCT_REGION_SIGNATURE_LIMIT]
        out[scene_name] = {
            "script_handles_found": len(scripts),
            "icon_films_found": len(films),
            "scripts_with_regions": scripts_with_regions,
            "scripts_with_loops": scripts_with_loops,
            "region_count": region_count,
            "loop_region_count": loop_region_count,
            "conditional_region_count": conditional_region_count,
            "max_region_size": max_region_size,
            "max_cfg_fanout": max_cfg_fanout,
            "max_conditional_nesting": max_conditional_nesting,
            "region_terminator_histogram": dict(sorted(terminator_histogram.items())),
            "region_size_histogram": {
                key: region_size_histogram[key] for key in sorted(region_size_histogram.keys(), key=int)
            },
            "top_region_signatures": top_region_signatures,
            "top_region_signatures_sha256": hashlib.sha256(
                "|".join(top_region_signatures).encode("utf-8")
            ).hexdigest(),
            "region_signature_sequence_head": sequence_head,
            "region_signature_sequence_head_sha256": hashlib.sha256(
                "|".join(sequence_head).encode("utf-8")
            ).hexdigest(),
        }

    return out


def _build_pcode_semantic_annotation_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in SEMANTIC_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]
        _, films = scanner_mod.collect_script_handles(scene_path, idx_by_name)

        semantic_calls: dict[str, dict] = {}
        transition_histogram = collections.Counter()
        region_semantic_histogram = collections.Counter()
        region_semantic_sequence: list[str] = []
        pseudocode_lines: list[str] = []

        scripts_with_semantics = 0
        semantic_region_count = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=SEMANTIC_MAX_STEPS, max_paths=SEMANTIC_MAX_PATHS)
            events = trace.get("events", [])

            disassembly = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = disassembly.get("instructions", [])
            regions = _script_structured_regions(instructions)
            if not regions:
                continue

            local_sequence: list[str] = []
            libcall_events_by_ip: dict[int, list[str]] = collections.defaultdict(list)

            for event in events:
                if event.get("event") != "libcall":
                    continue

                name = event.get("libcall_name")
                if not name:
                    continue

                local_sequence.append(name)
                stack_top = event.get("stack_top") or []
                depth = int(event.get("stack_depth") or 0)
                arity = len(stack_top)

                entry = semantic_calls.setdefault(
                    name,
                    {
                        "occurrence_count": 0,
                        "max_observed_arity": 0,
                        "stack_depth_min": None,
                        "stack_depth_max": 0,
                        "arg_arity_histogram": collections.Counter(),
                        "behavior_tags": set(),
                    },
                )
                entry["occurrence_count"] += 1
                entry["max_observed_arity"] = max(entry["max_observed_arity"], arity)
                entry["stack_depth_min"] = depth if entry["stack_depth_min"] is None else min(entry["stack_depth_min"], depth)
                entry["stack_depth_max"] = max(entry["stack_depth_max"], depth)
                entry["arg_arity_histogram"][str(arity)] += 1
                entry["behavior_tags"].update(_semantic_behavior_tags(name))

                ip = event.get("ip")
                if isinstance(ip, int):
                    libcall_events_by_ip[ip].append(name)

            for i in range(1, len(local_sequence)):
                transition_histogram[f"{local_sequence[i - 1]}->{local_sequence[i]}"] += 1

            script_has_semantic_region = False
            for region in regions:
                start_ip = int(region["start_ip"])
                end_ip = int(region["end_ip"])
                region_calls: list[str] = []
                for ip in sorted(libcall_events_by_ip.keys()):
                    if start_ip <= ip <= end_ip:
                        region_calls.extend(libcall_events_by_ip[ip])

                if region_calls:
                    script_has_semantic_region = True
                    semantic_region_count += 1
                    intent_set = set()
                    for call in region_calls:
                        intent_set.update(_semantic_behavior_tags(call))
                    intents = sorted(intent_set)
                    primary_intent = intents[0] if intents else "state"
                else:
                    primary_intent = "control"

                signature = (
                    f"{region['terminator']}:{primary_intent}:"
                    f"{'loop' if region['has_backedge'] else 'plain'}"
                )
                region_semantic_histogram[signature] += 1
                region_semantic_sequence.append(signature)

                if len(pseudocode_lines) < SEMANTIC_PSEUDOCODE_LINE_LIMIT:
                    pseudocode_lines.append(
                        _region_pseudocode_line(
                            region["terminator"],
                            bool(region["has_backedge"]),
                            primary_intent,
                            region_calls,
                        )
                    )

            if script_has_semantic_region:
                scripts_with_semantics += 1

        ranked_calls = sorted(
            semantic_calls.keys(),
            key=lambda name: (-semantic_calls[name]["occurrence_count"], name),
        )[:SEMANTIC_MAX_CALLS]

        semantic_call_contracts = {}
        for name in ranked_calls:
            entry = semantic_calls[name]
            max_arity = int(entry["max_observed_arity"])
            behavior_tags = sorted(entry["behavior_tags"])
            semantic_call_contracts[name] = {
                "occurrence_count": int(entry["occurrence_count"]),
                "behavior_tags": behavior_tags,
                "behavior_tags_sha256": hashlib.sha256("|".join(behavior_tags).encode("utf-8")).hexdigest(),
                "max_observed_arity": max_arity,
                "argument_labels": _semantic_arg_labels(name, max_arity),
                "arg_arity_histogram": {
                    key: entry["arg_arity_histogram"][key]
                    for key in sorted(entry["arg_arity_histogram"].keys(), key=int)
                },
                "stack_depth_min": 0 if entry["stack_depth_min"] is None else int(entry["stack_depth_min"]),
                "stack_depth_max": int(entry["stack_depth_max"]),
            }

        top_region_semantics = [name for name, _ in region_semantic_histogram.most_common(12)]
        region_sequence_head = region_semantic_sequence[:STRUCT_REGION_SIGNATURE_LIMIT]
        pseudocode_head = pseudocode_lines[:SEMANTIC_PSEUDOCODE_LINE_LIMIT]

        semantic_libcall_count = sum(int(values["occurrence_count"]) for values in semantic_calls.values())
        out[scene_name] = {
            "script_handles_found": len(scripts),
            "icon_films_found": len(films),
            "scripts_with_semantics": scripts_with_semantics,
            "semantic_region_count": semantic_region_count,
            "semantic_libcall_count": semantic_libcall_count,
            "unique_semantic_libcall_count": len(semantic_calls),
            "libcalls_ranked": ranked_calls,
            "libcall_semantics": {name: semantic_call_contracts[name] for name in sorted(semantic_call_contracts.keys())},
            "libcall_transition_histogram": dict(sorted(transition_histogram.items())),
            "top_region_semantics": top_region_semantics,
            "top_region_semantics_sha256": hashlib.sha256("|".join(top_region_semantics).encode("utf-8")).hexdigest(),
            "region_semantic_sequence_head": region_sequence_head,
            "region_semantic_sequence_head_sha256": hashlib.sha256(
                "|".join(region_sequence_head).encode("utf-8")
            ).hexdigest(),
            "pseudocode_summary_head": pseudocode_head,
            "pseudocode_summary_head_sha256": hashlib.sha256("|".join(pseudocode_head).encode("utf-8")).hexdigest(),
        }

    return out


def _parse_symbol_token(token: str) -> tuple[str, int] | None:
    text = str(token or "")
    if text.startswith("local:"):
        try:
            return "local", int(text.split(":", 1)[1])
        except ValueError:
            return None
    if text.startswith("global:"):
        try:
            return "global", int(text.split(":", 1)[1])
        except ValueError:
            return None
    return None


def _symbol_primary_role(tags: set[str], reads: int, writes: int) -> str:
    if "inventory" in tags:
        return "item"
    if "dialogue" in tags:
        return "dialogue"
    if "timing" in tags:
        return "timer"
    if "playback" in tags:
        return "playback"
    if "tag" in tags:
        return "tag"
    if "audio" in tags:
        return "audio"
    if reads == 0 and writes > 0:
        return "output"
    if writes == 0 and reads > 0:
        return "input"
    return "state"


def _symbol_type_hint(role: str, kind: str) -> str:
    if role == "item":
        return "item_id"
    if role == "dialogue":
        return "topic_id"
    if role == "timer":
        return "counter"
    if role == "playback":
        return "handle_or_coord"
    if role == "tag":
        return "tag_id"
    if role == "audio":
        return "sample_id"
    if role == "input":
        return "input_value"
    if role == "output":
        return "output_value"
    if kind == "global":
        return "state_value"
    return "temp_value"


def _build_pcode_symbol_recovery_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    out = {}
    for scene_name in SYMBOL_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        symbols: dict[str, dict] = {}
        symbol_transition_histogram = collections.Counter()
        symbol_summary_head: list[str] = []
        scripts_with_symbol_activity = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=SYMBOL_MAX_STEPS, max_paths=SYMBOL_MAX_PATHS)
            disassembly = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = disassembly.get("instructions", [])
            local_sequence: list[str] = []
            had_activity = False

            for ins in instructions:
                name = str(ins.get("name") or "")
                operand = ins.get("operand")
                if not isinstance(operand, int):
                    continue
                if name not in {"LOAD", "GLOAD", "STORE", "GSTORE"}:
                    continue

                if name in {"LOAD", "STORE"}:
                    kind = "local"
                    index = operand
                else:
                    kind = "global"
                    index = operand

                key = f"{kind}:{index}"
                entry = symbols.setdefault(
                    key,
                    {
                        "kind": kind,
                        "index": index,
                        "reads": 0,
                        "writes": 0,
                        "refs": 0,
                        "libcall_context_histogram": collections.Counter(),
                        "behavior_tags": set(),
                        "stack_depth_min": None,
                        "stack_depth_max": 0,
                    },
                )
                if name in {"LOAD", "GLOAD"}:
                    entry["reads"] += 1
                else:
                    entry["writes"] += 1

            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue
                libcall_name = event.get("libcall_name")
                if not libcall_name:
                    continue

                depth = int(event.get("stack_depth") or 0)
                stack_top = event.get("stack_top") or []
                event_symbols: list[str] = []

                for token in stack_top:
                    parsed = _parse_symbol_token(str(token))
                    if parsed is None:
                        continue
                    kind, index = parsed
                    key = f"{kind}:{index}"
                    entry = symbols.setdefault(
                        key,
                        {
                            "kind": kind,
                            "index": index,
                            "reads": 0,
                            "writes": 0,
                            "refs": 0,
                            "libcall_context_histogram": collections.Counter(),
                            "behavior_tags": set(),
                            "stack_depth_min": None,
                            "stack_depth_max": 0,
                        },
                    )
                    entry["refs"] += 1
                    entry["libcall_context_histogram"][libcall_name] += 1
                    entry["behavior_tags"].update(_semantic_behavior_tags(libcall_name))
                    entry["stack_depth_min"] = depth if entry["stack_depth_min"] is None else min(entry["stack_depth_min"], depth)
                    entry["stack_depth_max"] = max(entry["stack_depth_max"], depth)
                    event_symbols.append(key)
                    had_activity = True

                event_symbols = sorted(set(event_symbols))
                local_sequence.extend(event_symbols)

            if had_activity:
                scripts_with_symbol_activity += 1

            for i in range(1, len(local_sequence)):
                symbol_transition_histogram[f"{local_sequence[i - 1]}->{local_sequence[i]}"] += 1

        locals_ranked = sorted(
            [key for key, val in symbols.items() if val["kind"] == "local"],
            key=lambda key: (-(symbols[key]["refs"] + symbols[key]["reads"] + symbols[key]["writes"]), key),
        )[:SYMBOL_MAX_SYMBOLS_PER_KIND]
        globals_ranked = sorted(
            [key for key, val in symbols.items() if val["kind"] == "global"],
            key=lambda key: (-(symbols[key]["refs"] + symbols[key]["reads"] + symbols[key]["writes"]), key),
        )[:SYMBOL_MAX_SYMBOLS_PER_KIND]
        ranked_symbols = locals_ranked + globals_ranked

        symbol_table = {}
        role_histogram = collections.Counter()
        type_histogram = collections.Counter()
        for key in ranked_symbols:
            entry = symbols[key]
            role = _symbol_primary_role(set(entry["behavior_tags"]), int(entry["reads"]), int(entry["writes"]))
            type_hint = _symbol_type_hint(role, str(entry["kind"]))
            role_histogram[role] += 1
            type_histogram[type_hint] += 1
            label_prefix = "l" if entry["kind"] == "local" else "g"
            recovered_name = f"{label_prefix}{entry['index']}_{role}"
            top_libcalls = [name for name, _ in entry["libcall_context_histogram"].most_common(6)]

            symbol_table[key] = {
                "kind": entry["kind"],
                "index": int(entry["index"]),
                "recovered_name": recovered_name,
                "role": role,
                "type_hint": type_hint,
                "reads": int(entry["reads"]),
                "writes": int(entry["writes"]),
                "refs": int(entry["refs"]),
                "stack_depth_min": 0 if entry["stack_depth_min"] is None else int(entry["stack_depth_min"]),
                "stack_depth_max": int(entry["stack_depth_max"]),
                "top_libcalls": top_libcalls,
                "top_libcalls_sha256": hashlib.sha256("|".join(top_libcalls).encode("utf-8")).hexdigest(),
                "behavior_tags": sorted(entry["behavior_tags"]),
                "behavior_tags_sha256": hashlib.sha256("|".join(sorted(entry["behavior_tags"])).encode("utf-8")).hexdigest(),
            }

            summary_line = (
                f"{recovered_name}:{type_hint}:r{entry['reads']}:w{entry['writes']}:"
                f"x{entry['refs']}"
            )
            symbol_summary_head.append(summary_line)

        symbol_summary_head = symbol_summary_head[:SYMBOL_SUMMARY_HEAD_LIMIT]
        out[scene_name] = {
            "script_handles_found": len(scripts),
            "scripts_with_symbol_activity": scripts_with_symbol_activity,
            "local_symbol_count": sum(1 for val in symbols.values() if val["kind"] == "local"),
            "global_symbol_count": sum(1 for val in symbols.values() if val["kind"] == "global"),
            "locals_ranked": locals_ranked,
            "globals_ranked": globals_ranked,
            "symbol_table": {name: symbol_table[name] for name in sorted(symbol_table.keys())},
            "symbol_role_histogram": dict(sorted(role_histogram.items())),
            "symbol_type_histogram": dict(sorted(type_histogram.items())),
            "symbol_transition_histogram": dict(sorted(symbol_transition_histogram.items())),
            "symbol_summary_head": symbol_summary_head,
            "symbol_summary_head_sha256": hashlib.sha256("|".join(symbol_summary_head).encode("utf-8")).hexdigest(),
        }

    return out


def _canonical_cluster_key(symbol_entry: dict) -> str:
    kind = str(symbol_entry.get("kind") or "unknown")
    role = str(symbol_entry.get("role") or "state")
    type_hint = str(symbol_entry.get("type_hint") or "value")
    behavior_hash = str(symbol_entry.get("behavior_tags_sha256") or "")[:12]
    top_hash = str(symbol_entry.get("top_libcalls_sha256") or "")[:12]
    return f"{kind}:{role}:{type_hint}:{behavior_hash}:{top_hash}"


def _canonical_name(kind: str, role: str, cluster_index: int) -> str:
    prefix = "l" if kind == "local" else "g"
    return f"{prefix}_{role}_{cluster_index:03d}"


def _build_pcode_symbol_canonicalization_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    per_scene_symbols = _build_pcode_symbol_recovery_snapshots(vm_mod, scanner_mod, dataset_dir)

    cluster_members: dict[str, list[tuple[str, str, dict]]] = {}
    for scene_name in CANON_CONTRACT_SCENES:
        scene_payload = per_scene_symbols.get(scene_name, {})
        scene_table = scene_payload.get("symbol_table", {})
        for symbol_key, symbol_entry in scene_table.items():
            cluster_key = _canonical_cluster_key(symbol_entry)
            cluster_members.setdefault(cluster_key, []).append((scene_name, symbol_key, symbol_entry))

    ranked_clusters = sorted(
        cluster_members.keys(),
        key=lambda key: (
            -len(cluster_members[key]),
            len({scene for scene, _, _ in cluster_members[key]}),
            key,
        ),
    )

    cluster_to_canonical: dict[str, str] = {}
    for idx, cluster_key in enumerate(ranked_clusters, start=1):
        members = cluster_members[cluster_key]
        member_kind = str(members[0][2].get("kind") or "global")
        member_role = str(members[0][2].get("role") or "state")
        cluster_to_canonical[cluster_key] = _canonical_name(member_kind, member_role, idx)

    registry_rows = []
    for cluster_key in ranked_clusters[:CANON_REGISTRY_LIMIT]:
        canonical = cluster_to_canonical[cluster_key]
        members = sorted(cluster_members[cluster_key], key=lambda row: (row[0], row[1]))
        scenes = sorted({scene for scene, _, _ in members})
        exemplar = members[0][2]
        registry_rows.append(
            {
                "canonical_name": canonical,
                "cluster_key": cluster_key,
                "kind": exemplar.get("kind"),
                "role": exemplar.get("role"),
                "type_hint": exemplar.get("type_hint"),
                "member_count": len(members),
                "scene_count": len(scenes),
                "scenes": scenes,
                "member_examples": [f"{scene}:{symbol_key}" for scene, symbol_key, _ in members[:6]],
            }
        )

    out = {}
    multi_scene_cluster_count = sum(
        1 for key in ranked_clusters if len({scene for scene, _, _ in cluster_members[key]}) > 1
    )
    for scene_name in CANON_CONTRACT_SCENES:
        scene_payload = per_scene_symbols.get(scene_name, {})
        scene_table = scene_payload.get("symbol_table", {})
        scene_transition_hist = scene_payload.get("symbol_transition_histogram", {})

        canonical_map = {}
        alias_lines: list[str] = []
        alias_transition_hist = collections.Counter()

        for symbol_key in sorted(scene_table.keys()):
            symbol_entry = scene_table[symbol_key]
            cluster_key = _canonical_cluster_key(symbol_entry)
            canonical = cluster_to_canonical.get(cluster_key, "g_state_000")
            canonical_map[symbol_key] = {
                "canonical_name": canonical,
                "cluster_key": cluster_key,
                "recovered_name": symbol_entry.get("recovered_name"),
                "role": symbol_entry.get("role"),
                "type_hint": symbol_entry.get("type_hint"),
            }
            alias_lines.append(f"{canonical} <- {symbol_entry.get('recovered_name')}")

        for edge, count in scene_transition_hist.items():
            src, sep, dst = str(edge).partition("->")
            if not sep:
                continue
            src_canonical = canonical_map.get(src, {}).get("canonical_name")
            dst_canonical = canonical_map.get(dst, {}).get("canonical_name")
            if not src_canonical or not dst_canonical:
                continue
            alias_transition_hist[f"{src_canonical}->{dst_canonical}"] += int(count)

        alias_head = alias_lines[:CANON_ALIAS_HEAD_LIMIT]
        canonical_names_ranked = sorted(
            {row["canonical_name"] for row in canonical_map.values()},
            key=lambda name: name,
        )

        out[scene_name] = {
            "script_handles_found": scene_payload.get("script_handles_found", 0),
            "symbols_with_canonical_alias": len(canonical_map),
            "canonical_names_ranked": canonical_names_ranked,
            "canonical_symbol_map": {key: canonical_map[key] for key in sorted(canonical_map.keys())},
            "canonical_alias_transition_histogram": dict(sorted(alias_transition_hist.items())),
            "canonical_alias_head": alias_head,
            "canonical_alias_head_sha256": hashlib.sha256("|".join(alias_head).encode("utf-8")).hexdigest(),
            "global_cluster_count": len(ranked_clusters),
            "multi_scene_cluster_count": multi_scene_cluster_count,
            "canonical_registry_head": registry_rows,
            "canonical_registry_head_sha256": hashlib.sha256(
                "|".join(row["canonical_name"] for row in registry_rows).encode("utf-8")
            ).hexdigest(),
        }

    return out


def _region_control_prefix(terminator: str, has_backedge: bool) -> str:
    if has_backedge:
        return "while"
    if terminator == "conditional":
        return "if"
    if terminator in {"halt", "ret"}:
        return "return"
    if terminator == "jump":
        return "goto"
    return "step"


def _build_pcode_pseudocode_quality_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    canonical_by_scene = _build_pcode_symbol_canonicalization_snapshots(vm_mod, scanner_mod, dataset_dir)

    out = {}
    for scene_name in PSEUDO_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        scene_canonical_map = (
            canonical_by_scene.get(scene_name, {}).get("canonical_symbol_map", {})
        )

        pseudocode_lines: list[str] = []
        symbol_alias_usage_histogram = collections.Counter()
        libcall_usage_histogram = collections.Counter()
        region_intent_histogram = collections.Counter()
        scripts_with_pseudocode = 0

        for script in scripts:
            handle = script["handle"]
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=PSEUDO_MAX_STEPS, max_paths=PSEUDO_MAX_PATHS)
            disassembly = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = disassembly.get("instructions", [])
            regions = _script_structured_regions(instructions)
            if not regions:
                continue

            libcall_events_by_ip: dict[int, list[dict]] = collections.defaultdict(list)
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue
                ip = event.get("ip")
                if isinstance(ip, int):
                    libcall_events_by_ip[ip].append(event)

            script_line_count = 0
            for region in regions:
                start_ip = int(region["start_ip"])
                end_ip = int(region["end_ip"])
                region_calls: list[str] = []
                region_aliases: list[str] = []

                for ip in sorted(libcall_events_by_ip.keys()):
                    if not (start_ip <= ip <= end_ip):
                        continue
                    for event in libcall_events_by_ip[ip]:
                        libcall_name = str(event.get("libcall_name") or "")
                        if libcall_name:
                            region_calls.append(libcall_name)
                            libcall_usage_histogram[libcall_name] += 1

                        for token in event.get("stack_top") or []:
                            parsed = _parse_symbol_token(str(token))
                            if parsed is None:
                                continue
                            kind, index = parsed
                            symbol_key = f"{kind}:{index}"
                            canonical_name = (
                                scene_canonical_map.get(symbol_key, {}).get("canonical_name")
                            )
                            if canonical_name:
                                region_aliases.append(canonical_name)

                region_aliases = sorted(set(region_aliases))
                for alias in region_aliases:
                    symbol_alias_usage_histogram[alias] += 1

                intent_tags = set()
                for call_name in region_calls:
                    intent_tags.update(_semantic_behavior_tags(call_name))
                primary_intent = sorted(intent_tags)[0] if intent_tags else "control"
                region_intent_histogram[primary_intent] += 1

                control_prefix = _region_control_prefix(
                    str(region["terminator"]),
                    bool(region["has_backedge"]),
                )
                alias_phrase = ",".join(region_aliases[:2]) if region_aliases else "state"
                call_phrase = ",".join(region_calls[:2]).lower() if region_calls else "noop"

                if control_prefix == "if":
                    line = f"if {alias_phrase}: {primary_intent} via {call_phrase}"
                elif control_prefix == "while":
                    line = f"while {alias_phrase}: {primary_intent} via {call_phrase}"
                elif control_prefix == "return":
                    line = f"return {primary_intent} via {call_phrase}"
                elif control_prefix == "goto":
                    line = f"goto {primary_intent} via {call_phrase}"
                else:
                    line = f"step {primary_intent} via {call_phrase}"

                pseudocode_lines.append(line)
                script_line_count += 1

            if script_line_count > 0:
                scripts_with_pseudocode += 1

        lines_head = pseudocode_lines[:PSEUDO_LINE_HEAD_LIMIT]
        top_symbol_aliases = [name for name, _ in symbol_alias_usage_histogram.most_common(20)]
        top_libcalls = [name for name, _ in libcall_usage_histogram.most_common(20)]

        out[scene_name] = {
            "script_handles_found": len(scripts),
            "scripts_with_pseudocode": scripts_with_pseudocode,
            "pseudocode_line_count": len(pseudocode_lines),
            "pseudocode_summary_head": lines_head,
            "pseudocode_summary_head_sha256": hashlib.sha256("|".join(lines_head).encode("utf-8")).hexdigest(),
            "region_intent_histogram": dict(sorted(region_intent_histogram.items())),
            "symbol_alias_usage_histogram": dict(sorted(symbol_alias_usage_histogram.items())),
            "libcall_usage_histogram": dict(sorted(libcall_usage_histogram.items())),
            "top_symbol_aliases": top_symbol_aliases,
            "top_symbol_aliases_sha256": hashlib.sha256("|".join(top_symbol_aliases).encode("utf-8")).hexdigest(),
            "top_libcalls": top_libcalls,
            "top_libcalls_sha256": hashlib.sha256("|".join(top_libcalls).encode("utf-8")).hexdigest(),
        }

    return out


def _build_pcode_emitter_output_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    canonical_by_scene = _build_pcode_symbol_canonicalization_snapshots(vm_mod, scanner_mod, dataset_dir)
    pseudo_by_scene = _build_pcode_pseudocode_quality_snapshots(vm_mod, scanner_mod, dataset_dir)

    out = {}
    for scene_name in EMIT_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        scene_canonical_map = (
            canonical_by_scene.get(scene_name, {}).get("canonical_symbol_map", {})
        )

        function_rows = []
        function_signature_histogram = collections.Counter()
        emitted_line_fingerprint_tokens: list[str] = []
        scripts_emitted = 0

        scene_stub = scene_name.split(".", 1)[0].lower()
        for script in scripts:
            handle = int(script.get("handle") or 0)
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            disassembly = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = disassembly.get("instructions", [])
            regions = _script_structured_regions(instructions)
            if not regions:
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=EMIT_MAX_STEPS, max_paths=EMIT_MAX_PATHS)
            libcall_events_by_ip: dict[int, list[dict]] = collections.defaultdict(list)
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue
                ip = event.get("ip")
                if isinstance(ip, int):
                    libcall_events_by_ip[ip].append(event)

            body_lines: list[str] = []
            terminator_hist = collections.Counter()
            intent_hist = collections.Counter()
            alias_usage = collections.Counter()
            for region in regions:
                start_ip = int(region["start_ip"])
                end_ip = int(region["end_ip"])
                terminator = str(region["terminator"])
                terminator_hist[terminator] += 1

                calls: list[str] = []
                aliases: list[str] = []
                for ip in sorted(libcall_events_by_ip.keys()):
                    if not (start_ip <= ip <= end_ip):
                        continue
                    for event in libcall_events_by_ip[ip]:
                        call_name = str(event.get("libcall_name") or "")
                        if call_name:
                            calls.append(call_name)
                        for token in event.get("stack_top") or []:
                            parsed = _parse_symbol_token(str(token))
                            if parsed is None:
                                continue
                            kind, index = parsed
                            symbol_key = f"{kind}:{index}"
                            canonical_name = scene_canonical_map.get(symbol_key, {}).get("canonical_name")
                            if canonical_name:
                                aliases.append(canonical_name)

                aliases = sorted(set(aliases))
                for alias in aliases:
                    alias_usage[alias] += 1

                intent_tags = set()
                for call_name in calls:
                    intent_tags.update(_semantic_behavior_tags(call_name))
                intent = sorted(intent_tags)[0] if intent_tags else "control"
                intent_hist[intent] += 1

                control = _region_control_prefix(terminator, bool(region["has_backedge"]))
                alias_phrase = ",".join(aliases[:2]) if aliases else "state"
                call_phrase = ",".join(calls[:2]).lower() if calls else "noop"
                if control == "if":
                    line = f"if ({alias_phrase}) then {intent}::{call_phrase}"
                elif control == "while":
                    line = f"while ({alias_phrase}) do {intent}::{call_phrase}"
                elif control == "return":
                    line = f"return {intent}::{call_phrase}"
                elif control == "goto":
                    line = f"goto {intent}::{call_phrase}"
                else:
                    line = f"step {intent}::{call_phrase}"

                if len(body_lines) < EMIT_MAX_BODY_LINES:
                    body_lines.append(line)
                    emitted_line_fingerprint_tokens.append(line)

            if not body_lines:
                continue

            scripts_emitted += 1
            function_name = f"{scene_stub}_fn_{handle:08X}"
            signature_tokens = [
                f"regions:{len(regions)}",
                f"paths:{int(trace.get('paths_started') or 1)}",
                f"top_term:{','.join(name for name, _ in terminator_hist.most_common(2))}",
                f"top_intent:{','.join(name for name, _ in intent_hist.most_common(2))}",
            ]
            signature = "|".join(signature_tokens)
            function_signature_histogram[signature] += 1

            top_aliases = [name for name, _ in alias_usage.most_common(6)]
            function_rows.append(
                {
                    "function_name": function_name,
                    "script_handle": f"0x{handle:08X}",
                    "script_source": script.get("source"),
                    "region_count": len(regions),
                    "line_count": len(body_lines),
                    "signature": signature,
                    "signature_sha256": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
                    "body_head": body_lines,
                    "body_head_sha256": hashlib.sha256("|".join(body_lines).encode("utf-8")).hexdigest(),
                    "top_aliases": top_aliases,
                    "top_aliases_sha256": hashlib.sha256("|".join(top_aliases).encode("utf-8")).hexdigest(),
                }
            )

        function_rows = sorted(function_rows, key=lambda row: row["function_name"])
        function_head = function_rows[:EMIT_FUNCTION_HEAD_LIMIT]
        function_name_head = [row["function_name"] for row in function_head]
        top_signatures = [sig for sig, _ in function_signature_histogram.most_common(16)]

        out[scene_name] = {
            "script_handles_found": len(scripts),
            "scripts_emitted": scripts_emitted,
            "function_count": len(function_rows),
            "function_name_head": function_name_head,
            "function_name_head_sha256": hashlib.sha256("|".join(function_name_head).encode("utf-8")).hexdigest(),
            "top_function_signatures": top_signatures,
            "top_function_signatures_sha256": hashlib.sha256("|".join(top_signatures).encode("utf-8")).hexdigest(),
            "function_head": function_head,
            "function_head_sha256": hashlib.sha256(
                "|".join(row["function_name"] for row in function_head).encode("utf-8")
            ).hexdigest(),
            "emitted_line_digest": hashlib.sha256("|".join(emitted_line_fingerprint_tokens).encode("utf-8")).hexdigest(),
            "pseudo_summary_head_sha256": pseudo_by_scene.get(scene_name, {}).get("pseudocode_summary_head_sha256", ""),
        }

    return out


def _build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / "INDEX")
    idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}

    canonical_by_scene = _build_pcode_symbol_canonicalization_snapshots(vm_mod, scanner_mod, dataset_dir)

    out = {}
    for scene_name in BUNDLE_CONTRACT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

        scene_canonical_map = (
            canonical_by_scene.get(scene_name, {}).get("canonical_symbol_map", {})
        )

        functions: list[dict] = []
        bundle_lines: list[str] = []
        function_signature_histogram = collections.Counter()

        scene_stub = scene_name.split(".", 1)[0].lower()
        for script in scripts:
            if len(functions) >= BUNDLE_FUNCTION_LIMIT:
                break

            handle = int(script.get("handle") or 0)
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            disassembly = scanner_mod.disassemble(data, offset, max_ins=STRUCT_MAX_INS)
            instructions = disassembly.get("instructions", [])
            regions = _script_structured_regions(instructions)
            if not regions:
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=BUNDLE_MAX_STEPS, max_paths=BUNDLE_MAX_PATHS)
            libcall_events_by_ip: dict[int, list[dict]] = collections.defaultdict(list)
            for event in trace.get("events", []):
                if event.get("event") != "libcall":
                    continue
                ip = event.get("ip")
                if isinstance(ip, int):
                    libcall_events_by_ip[ip].append(event)

            body_lines: list[str] = []
            terminator_hist = collections.Counter()
            intent_hist = collections.Counter()
            alias_hist = collections.Counter()
            for region in regions:
                start_ip = int(region["start_ip"])
                end_ip = int(region["end_ip"])
                terminator = str(region["terminator"])
                terminator_hist[terminator] += 1

                calls: list[str] = []
                aliases: list[str] = []
                for ip in sorted(libcall_events_by_ip.keys()):
                    if not (start_ip <= ip <= end_ip):
                        continue
                    for event in libcall_events_by_ip[ip]:
                        call_name = str(event.get("libcall_name") or "")
                        if call_name:
                            calls.append(call_name)
                        for token in event.get("stack_top") or []:
                            parsed = _parse_symbol_token(str(token))
                            if parsed is None:
                                continue
                            kind, index = parsed
                            symbol_key = f"{kind}:{index}"
                            canonical_name = scene_canonical_map.get(symbol_key, {}).get("canonical_name")
                            if canonical_name:
                                aliases.append(canonical_name)

                aliases = sorted(set(aliases))
                for alias in aliases:
                    alias_hist[alias] += 1

                intent_tags = set()
                for call_name in calls:
                    intent_tags.update(_semantic_behavior_tags(call_name))
                intent = sorted(intent_tags)[0] if intent_tags else "control"
                intent_hist[intent] += 1

                control = _region_control_prefix(terminator, bool(region["has_backedge"]))
                alias_phrase = ",".join(aliases[:3]) if aliases else "state"
                call_phrase = ",".join(calls[:3]).lower() if calls else "noop"
                if control == "if":
                    line = f"if ({alias_phrase}) then {intent}::{call_phrase};"
                elif control == "while":
                    line = f"while ({alias_phrase}) do {intent}::{call_phrase};"
                elif control == "return":
                    line = f"return {intent}::{call_phrase};"
                elif control == "goto":
                    line = f"goto {intent}::{call_phrase};"
                else:
                    line = f"step {intent}::{call_phrase};"
                body_lines.append(line)

            if not body_lines:
                continue

            body_lines = body_lines[:BUNDLE_MAX_BODY_LINES]
            function_name = f"{scene_stub}_fn_{handle:08X}"
            signature_tokens = [
                f"regions:{len(regions)}",
                f"paths:{int(trace.get('paths_started') or 1)}",
                f"term:{','.join(name for name, _ in terminator_hist.most_common(3))}",
                f"intent:{','.join(name for name, _ in intent_hist.most_common(3))}",
                f"aliases:{','.join(name for name, _ in alias_hist.most_common(3))}",
            ]
            signature = "|".join(signature_tokens)
            function_signature_histogram[signature] += 1

            function_block = [f"function {function_name}() {{"]
            function_block.extend(f"  {line}" for line in body_lines)
            function_block.append("}")
            bundle_lines.extend(function_block)

            functions.append(
                {
                    "function_name": function_name,
                    "script_handle": f"0x{handle:08X}",
                    "script_source": script.get("source"),
                    "line_count": len(body_lines),
                    "signature": signature,
                    "signature_sha256": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
                    "body": body_lines,
                    "body_sha256": hashlib.sha256("|".join(body_lines).encode("utf-8")).hexdigest(),
                }
            )

        functions = sorted(functions, key=lambda row: row["function_name"])
        bundle_lines_head = bundle_lines[:BUNDLE_TEXT_HEAD_LIMIT]
        top_signatures = [sig for sig, _ in function_signature_histogram.most_common(24)]

        out[scene_name] = {
            "script_handles_found": len(scripts),
            "function_count": len(functions),
            "function_names": [row["function_name"] for row in functions],
            "function_names_sha256": hashlib.sha256(
                "|".join(row["function_name"] for row in functions).encode("utf-8")
            ).hexdigest(),
            "top_function_signatures": top_signatures,
            "top_function_signatures_sha256": hashlib.sha256("|".join(top_signatures).encode("utf-8")).hexdigest(),
            "function_bundle_head": functions,
            "function_bundle_head_sha256": hashlib.sha256(
                "|".join(row["function_name"] for row in functions).encode("utf-8")
            ).hexdigest(),
            "bundle_text_head": bundle_lines_head,
            "bundle_text_head_sha256": hashlib.sha256("|".join(bundle_lines_head).encode("utf-8")).hexdigest(),
            "bundle_text_digest": hashlib.sha256("\n".join(bundle_lines).encode("utf-8")).hexdigest(),
        }

    return out


def _build_pcode_semantic_delta_report_snapshots(
    previous_bundle: dict,
    current_bundle: dict,
) -> dict:
    out = {}
    for scene_name in DELTA_CONTRACT_SCENES:
        previous_scene = previous_bundle.get(scene_name, {}) if isinstance(previous_bundle, dict) else {}
        current_scene = current_bundle.get(scene_name, {}) if isinstance(current_bundle, dict) else {}

        previous_names = set(previous_scene.get("function_names") or [])
        current_names = set(current_scene.get("function_names") or [])
        added_names = sorted(current_names - previous_names)
        removed_names = sorted(previous_names - current_names)

        previous_rows = {
            row.get("function_name"): row
            for row in (previous_scene.get("function_bundle_head") or [])
            if isinstance(row, dict) and row.get("function_name")
        }
        current_rows = {
            row.get("function_name"): row
            for row in (current_scene.get("function_bundle_head") or [])
            if isinstance(row, dict) and row.get("function_name")
        }

        changed_body = []
        changed_signature = []
        for name in sorted(previous_names & current_names):
            prev_row = previous_rows.get(name, {})
            cur_row = current_rows.get(name, {})
            if str(prev_row.get("body_sha256") or "") != str(cur_row.get("body_sha256") or ""):
                changed_body.append(name)
            if str(prev_row.get("signature_sha256") or "") != str(cur_row.get("signature_sha256") or ""):
                changed_signature.append(name)

        previous_sig_hash = str(previous_scene.get("top_function_signatures_sha256") or "")
        current_sig_hash = str(current_scene.get("top_function_signatures_sha256") or "")
        previous_bundle_hash = str(previous_scene.get("bundle_text_digest") or "")
        current_bundle_hash = str(current_scene.get("bundle_text_digest") or "")

        change_head = []
        change_head.extend(f"+fn:{name}" for name in added_names)
        change_head.extend(f"-fn:{name}" for name in removed_names)
        change_head.extend(f"~body:{name}" for name in changed_body)
        change_head.extend(f"~sig:{name}" for name in changed_signature)
        if previous_sig_hash != current_sig_hash:
            change_head.append("~scene:top_signatures")
        if previous_bundle_hash != current_bundle_hash:
            change_head.append("~scene:bundle_text")
        change_head = change_head[:DELTA_CHANGE_HEAD_LIMIT]

        out[scene_name] = {
            "previous_function_count": int(previous_scene.get("function_count") or 0),
            "current_function_count": int(current_scene.get("function_count") or 0),
            "added_function_count": len(added_names),
            "removed_function_count": len(removed_names),
            "changed_body_count": len(changed_body),
            "changed_signature_count": len(changed_signature),
            "has_scene_digest_change": previous_bundle_hash != current_bundle_hash,
            "has_scene_signature_change": previous_sig_hash != current_sig_hash,
            "added_functions": added_names,
            "removed_functions": removed_names,
            "changed_body_functions": changed_body,
            "changed_signature_functions": changed_signature,
            "change_head": change_head,
            "change_head_sha256": hashlib.sha256("|".join(change_head).encode("utf-8")).hexdigest(),
            "previous_bundle_text_digest": previous_bundle_hash,
            "current_bundle_text_digest": current_bundle_hash,
            "delta_token": hashlib.sha256(
                "|".join(
                    [
                        previous_bundle_hash,
                        current_bundle_hash,
                        previous_sig_hash,
                        current_sig_hash,
                        str(len(added_names)),
                        str(len(removed_names)),
                        str(len(changed_body)),
                        str(len(changed_signature)),
                    ]
                ).encode("utf-8")
            ).hexdigest(),
        }

    return out


def _build_pcode_regression_digest_snapshots(
    delta_payload: dict,
    bundle_payload: dict,
) -> dict:
    out = {}
    for scene_name in DIGEST_CONTRACT_SCENES:
        delta_scene = delta_payload.get(scene_name, {}) if isinstance(delta_payload, dict) else {}
        bundle_scene = bundle_payload.get(scene_name, {}) if isinstance(bundle_payload, dict) else {}

        current_count = int(delta_scene.get("current_function_count") or 0)
        added_count = int(delta_scene.get("added_function_count") or 0)
        removed_count = int(delta_scene.get("removed_function_count") or 0)
        changed_body_count = int(delta_scene.get("changed_body_count") or 0)
        changed_sig_count = int(delta_scene.get("changed_signature_count") or 0)
        severity_score = added_count * 3 + removed_count * 3 + changed_body_count * 2 + changed_sig_count

        if severity_score == 0:
            severity = "none"
        elif severity_score <= 3:
            severity = "low"
        elif severity_score <= 8:
            severity = "medium"
        else:
            severity = "high"

        digest_lines = [
            f"# {scene_name} regression digest",
            f"severity: {severity} (score={severity_score})",
            f"functions: current={current_count} added={added_count} removed={removed_count}",
            f"changes: body={changed_body_count} signature={changed_sig_count}",
        ]

        if bool(delta_scene.get("has_scene_digest_change")):
            digest_lines.append("scene bundle digest changed")
        else:
            digest_lines.append("scene bundle digest unchanged")

        if bool(delta_scene.get("has_scene_signature_change")):
            digest_lines.append("scene signature profile changed")
        else:
            digest_lines.append("scene signature profile unchanged")

        added = list(delta_scene.get("added_functions") or [])
        removed = list(delta_scene.get("removed_functions") or [])
        changed_body = list(delta_scene.get("changed_body_functions") or [])
        changed_sig = list(delta_scene.get("changed_signature_functions") or [])

        for name in added[:8]:
            digest_lines.append(f"+ {name}")
        for name in removed[:8]:
            digest_lines.append(f"- {name}")
        for name in changed_body[:8]:
            digest_lines.append(f"~ body {name}")
        for name in changed_sig[:8]:
            digest_lines.append(f"~ sig {name}")

        top_sigs = list(bundle_scene.get("top_function_signatures") or [])
        for signature in top_sigs[:6]:
            digest_lines.append(f"sig {signature}")

        digest_lines = digest_lines[:DIGEST_HEAD_LIMIT]
        out[scene_name] = {
            "severity": severity,
            "severity_score": severity_score,
            "current_function_count": current_count,
            "added_function_count": added_count,
            "removed_function_count": removed_count,
            "changed_body_count": changed_body_count,
            "changed_signature_count": changed_sig_count,
            "digest_head": digest_lines,
            "digest_head_sha256": hashlib.sha256("|".join(digest_lines).encode("utf-8")).hexdigest(),
            "delta_token": str(delta_scene.get("delta_token") or ""),
            "bundle_text_digest": str(bundle_scene.get("bundle_text_digest") or ""),
        }

    return out


def _render_bundle_text(scene_name: str, scene_bundle: dict) -> list[str]:
    function_rows = scene_bundle.get("function_bundle_head") or []
    out = [f"# Scene Decomp Bundle: {scene_name}"]
    for row in function_rows:
        if not isinstance(row, dict):
            continue
        function_name = str(row.get("function_name") or "unknown_function")
        signature = str(row.get("signature") or "")
        out.append("")
        out.append(f"function {function_name}() {{")
        if signature:
            out.append(f"  ; signature: {signature}")
        for line in row.get("body") or []:
            out.append(f"  {str(line)}")
        out.append("}")
    return out


def _build_pcode_decomp_delivery_manifest_snapshots(bundle_payload: dict) -> dict:
    out = {}
    for scene_name in DELIVER_CONTRACT_SCENES:
        scene_bundle = bundle_payload.get(scene_name, {}) if isinstance(bundle_payload, dict) else {}
        text_lines = _render_bundle_text(scene_name, scene_bundle)
        file_name = f"{scene_name.split('.', 1)[0].lower()}_decomp.pseudo"

        function_names = scene_bundle.get("function_names") or []
        out[scene_name] = {
            "artifact_file": file_name,
            "function_count": int(scene_bundle.get("function_count") or 0),
            "function_names": function_names,
            "function_names_sha256": hashlib.sha256("|".join(function_names).encode("utf-8")).hexdigest(),
            "bundle_text_digest": str(scene_bundle.get("bundle_text_digest") or ""),
            "artifact_line_count": len(text_lines),
            "artifact_text_head": text_lines[:DELIVER_TEXT_HEAD_LIMIT],
            "artifact_text_head_sha256": hashlib.sha256(
                "|".join(text_lines[:DELIVER_TEXT_HEAD_LIMIT]).encode("utf-8")
            ).hexdigest(),
            "artifact_full_sha256": hashlib.sha256("\n".join(text_lines).encode("utf-8")).hexdigest(),
        }

    return out


def _read_chunks(data: bytes) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    off = 0
    while off < len(data):
        if off + 8 > len(data):
            break
        cid, nxt = int.from_bytes(data[off:off+4], 'little'), int.from_bytes(data[off+4:off+8], 'little')
        end = nxt if nxt else len(data)
        out[cid] = (off + 8, end)
        if nxt == 0:
            break
        off = nxt
    return out


def _parse_scene_polygons(data: bytes) -> list[dict]:
    chunks = _read_chunks(data)
    if 0x3334000E not in chunks or 0x3334000C not in chunks:
        return []
    scene_payload, _ = chunks[0x3334000E]
    vals = [int.from_bytes(data[scene_payload + i * 4:scene_payload + i * 4 + 4], 'little') for i in range(8)]
    num_poly = vals[1]
    h_poly = vals[6]
    start = h_poly & 0x007FFFFF

    polys = []
    for i in range(num_poly):
        off = start + i * POLY_RECORD_SIZE_T1
        if off + POLY_RECORD_SIZE_T1 > len(data):
            break
        row = [int.from_bytes(data[off + j * 4:off + j * 4 + 4], 'little', signed=True) for j in range(26)]
        polys.append(
            {
                'index': i,
                'type': row[0],
                'x': list(row[1:5]),
                'y': list(row[5:9]),
                'h_tagtext': row[11],
                'id': row[16],
            }
        )
    return polys


def _point_in_polygon(x: int, y: int, poly: dict) -> bool:
    xs = poly['x']
    ys = poly['y']
    inside = False
    j = len(xs) - 1
    for i in range(len(xs)):
        xi, yi = xs[i], ys[i]
        xj, yj = xs[j], ys[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def _block_candidates(block_poly: dict) -> list[dict]:
    xs = block_poly['x']
    ys = block_poly['y']
    cx = sum(xs) / 4.0
    cy = sum(ys) / 4.0
    out = []
    for corner, (x, y) in enumerate(zip(xs, ys)):
        out.append({'corner': corner, 'x': x + (4 if x >= cx else -4), 'y': y + (4 if y >= cy else -4)})
    return out


def _parse_play_xy(stack_top: list[str]) -> tuple[int, int] | None:
    film_index = -1
    for i in range(len(stack_top) - 1, -1, -1):
        token = str(stack_top[i])
        if token.startswith('film:') or token.startswith('cdfilm:'):
            film_index = i
            break
    if film_index < 0:
        return None
    values: list[int] = []
    for token in stack_top[film_index + 1:]:
        token = str(token)
        if token.startswith('imm:'):
            try:
                values.append(int(token[4:]))
            except ValueError:
                continue
    if len(values) < 2:
        return None
    x, y = values[0], values[1]
    if x < 0 or y < 0:
        return None
    if x > 4096 or y > 4096:
        return None
    return x, y


def _resolve_placement_case(x: int, y: int, block_polys: list[dict], non_block_polys: list[dict]) -> dict:
    inside_block = any(_point_in_polygon(x, y, p) for p in block_polys)
    candidates = []
    if inside_block:
        for block in block_polys:
            for cand in _block_candidates(block):
                cx, cy = cand['x'], cand['y']
                if any(_point_in_polygon(cx, cy, p) for p in block_polys):
                    continue
                dist = abs(cx - x) + abs(cy - y)
                candidates.append((dist, cx, cy, block['index'], cand['corner']))

    if candidates:
        candidates.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4]))
        dist, adj_x, adj_y, src_block, src_corner = candidates[0]
    else:
        dist, adj_x, adj_y, src_block, src_corner = 0, x, y, None, None

    selected_poly = None
    for poly in non_block_polys:
        if _point_in_polygon(adj_x, adj_y, poly):
            selected_poly = poly['index']
            break

    return {
        'nominal_x': x,
        'nominal_y': y,
        'inside_block': inside_block,
        'candidate_count': len(candidates),
        'selected_polygon_index': selected_poly,
        'adjusted_x': adj_x,
        'adjusted_y': adj_y,
        'chosen_manhattan_distance': dist,
        'candidate_source_block_index': src_block,
        'candidate_corner': src_corner,
    }


def _build_placement_convergence_snapshots(vm_mod, dataset_dir: Path) -> dict:
    idx_rows = vm_mod.read_index(dataset_dir / 'INDEX')
    idx_by_name = {row['filename'].lower(): row['index'] for row in idx_rows}
    out = {}

    for scene_name in PLACEMENT_SCENES:
        scene_path = dataset_dir / scene_name
        data = scene_path.read_bytes()
        polys = _parse_scene_polygons(data)
        block_polys = [p for p in polys if p['type'] == 2]
        non_block_polys = [p for p in polys if p['type'] != 2]

        scripts = vm_mod.collect_script_handles(scene_path, idx_by_name)
        scripts = sorted(scripts, key=lambda s: (s.get('source', ''), s.get('handle', 0)))[:60]

        runtime_cases = []
        seen_coords = set()
        for script in scripts:
            handle = script['handle']
            file_index, offset = vm_mod.split_handle(handle)
            if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
                continue

            trace = vm_mod.execute_script(data, offset, max_steps=1200, max_paths=8)
            for event in trace['events']:
                if event.get('event') != 'libcall' or event.get('libcall_name') != 'PLAY':
                    continue
                xy = _parse_play_xy(event.get('stack_top') or [])
                if xy is None or xy in seen_coords:
                    continue
                seen_coords.add(xy)
                runtime_cases.append({'event_ip': event.get('ip'), **_resolve_placement_case(xy[0], xy[1], block_polys, non_block_polys)})
                if len(runtime_cases) >= 12:
                    break
            if len(runtime_cases) >= 12:
                break

        block_probe_case = None
        if block_polys:
            block = block_polys[0]
            cx = round(sum(block['x']) / 4)
            cy = round(sum(block['y']) / 4)
            block_probe_case = {
                'source_block_index': block['index'],
                'source': 'block_centroid_probe',
                **_resolve_placement_case(cx, cy, block_polys, non_block_polys),
            }

        out[scene_name] = {
            'scene_has_block_polygons': len(block_polys) > 0,
            'block_polygon_count': len(block_polys),
            'runtime_case_count': len(runtime_cases),
            'runtime_cases': runtime_cases,
            'block_probe_case': block_probe_case,
        }

    return out


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_snapshot(path: Path, payload: dict) -> bool:
    if not path.exists():
        print(f"- missing snapshot file: {path.name}")
        return False
    existing = _read_json(path)
    if existing != payload:
        print(f"- drift detected: {path.name}")
        return False
    print(f"- ok: {path.name}")
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Refresh regression snapshot baselines")
    parser.add_argument("--input", help="Dataset path containing INDEX and SCN files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-check snapshots for drift without writing files",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=["scn", "pcode", "bitmap", "scheduler", "placement", "contracts", "branch", "inventory", "hotspot", "dialogue", "timing", "cfg", "libsig", "ir", "struct", "semantic", "symbols", "canon", "pseudo", "emit", "bundle", "delta", "digest", "deliver", "all"],
        default=["all"],
        help="Refresh only selected snapshot groups",
    )
    args = parser.parse_args()

    try:
        dataset_dir = _resolve_dataset_dir(repo_root, args.input)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    refresh = set(args.only)
    if "all" in refresh:
        refresh = {"scn", "pcode", "bitmap", "scheduler", "placement", "contracts", "branch", "inventory", "hotspot", "dialogue", "timing", "cfg", "libsig", "ir", "struct", "semantic", "symbols", "canon", "pseudo", "emit", "bundle", "delta", "digest", "deliver"}

    extractor_mod = _load_module("discworld_extract_module", repo_root / "extractor" / "discworld_extract.py")

    targets = {
        "scn": repo_root / "tests" / "snapshots" / "scn_chunk_snapshots.json",
        "pcode": repo_root / "tests" / "snapshots" / "pcode_libcall_snapshots.json",
        "bitmap": repo_root / "tests" / "snapshots" / "bitmap_render_checksums.json",
        "scheduler": repo_root / "tests" / "snapshots" / "scheduler_event_snapshots.json",
        "placement": repo_root / "tests" / "snapshots" / "placement_convergence_snapshots.json",
        "contracts": repo_root / "tests" / "snapshots" / "scheduler_side_effect_contracts.json",
        "branch": repo_root / "tests" / "snapshots" / "branch_convergence_contracts.json",
        "inventory": repo_root / "tests" / "snapshots" / "inventory_interaction_contracts.json",
        "hotspot": repo_root / "tests" / "snapshots" / "hotspot_interaction_contracts.json",
        "dialogue": repo_root / "tests" / "snapshots" / "dialogue_topic_routing_contracts.json",
        "timing": repo_root / "tests" / "snapshots" / "timing_wait_semantics_contracts.json",
        "cfg": repo_root / "tests" / "snapshots" / "pcode_cfg_invariant_snapshots.json",
        "libsig": repo_root / "tests" / "snapshots" / "pcode_libcall_signature_contracts.json",
        "ir": repo_root / "tests" / "snapshots" / "pcode_ir_lift_snapshots.json",
        "struct": repo_root / "tests" / "snapshots" / "pcode_structuring_snapshots.json",
        "semantic": repo_root / "tests" / "snapshots" / "pcode_semantic_annotation_snapshots.json",
        "symbols": repo_root / "tests" / "snapshots" / "pcode_symbol_recovery_snapshots.json",
        "canon": repo_root / "tests" / "snapshots" / "pcode_symbol_canonicalization_snapshots.json",
        "pseudo": repo_root / "tests" / "snapshots" / "pcode_pseudocode_quality_snapshots.json",
        "emit": repo_root / "tests" / "snapshots" / "pcode_emitter_output_snapshots.json",
        "bundle": repo_root / "tests" / "snapshots" / "pcode_scene_decomp_bundle_snapshots.json",
        "delta": repo_root / "tests" / "snapshots" / "pcode_semantic_delta_report_snapshots.json",
        "digest": repo_root / "tests" / "snapshots" / "pcode_regression_digest_snapshots.json",
        "deliver": repo_root / "tests" / "snapshots" / "pcode_decomp_delivery_manifest_snapshots.json",
    }

    previous_bundle_payload = {}
    if targets["bundle"].exists():
        previous_bundle_payload = _read_json(targets["bundle"])

    previous_delta_payload = {}
    if targets["delta"].exists():
        previous_delta_payload = _read_json(targets["delta"])

    if args.check:
        print("Checking snapshot baselines (dry mode)")
    else:
        print("Refreshing snapshot baselines")
    print("Dataset:", dataset_dir)

    ok = True

    if "scn" in refresh:
        payload = _build_scn_chunk_snapshots(extractor_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["scn"], payload) and ok
        else:
            _write_json(targets["scn"], payload)
            print("- updated scn_chunk_snapshots.json")

    if "pcode" in refresh:
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_libcall_snapshots(scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["pcode"], payload) and ok
        else:
            _write_json(targets["pcode"], payload)
            print("- updated pcode_libcall_snapshots.json")

    if "bitmap" in refresh:
        renderer_mod = _load_module("tinsel1_renderer_module", repo_root / "extractor" / "tinsel1_renderer.py")
        payload = _build_bitmap_checksum_snapshots(renderer_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["bitmap"], payload) and ok
        else:
            _write_json(targets["bitmap"], payload)
            print("- updated bitmap_render_checksums.json")

    if "scheduler" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_scheduler_event_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["scheduler"], payload) and ok
        else:
            _write_json(targets["scheduler"], payload)
            print("- updated scheduler_event_snapshots.json")

    if "placement" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_placement_convergence_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["placement"], payload) and ok
        else:
            _write_json(targets["placement"], payload)
            print("- updated placement_convergence_snapshots.json")

    if "contracts" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_scheduler_side_effect_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["contracts"], payload) and ok
        else:
            _write_json(targets["contracts"], payload)
            print("- updated scheduler_side_effect_contracts.json")

    if "branch" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_branch_convergence_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["branch"], payload) and ok
        else:
            _write_json(targets["branch"], payload)
            print("- updated branch_convergence_contracts.json")

    if "inventory" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_inventory_interaction_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["inventory"], payload) and ok
        else:
            _write_json(targets["inventory"], payload)
            print("- updated inventory_interaction_contracts.json")

    if "hotspot" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_hotspot_interaction_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["hotspot"], payload) and ok
        else:
            _write_json(targets["hotspot"], payload)
            print("- updated hotspot_interaction_contracts.json")

    if "dialogue" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_dialogue_topic_routing_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["dialogue"], payload) and ok
        else:
            _write_json(targets["dialogue"], payload)
            print("- updated dialogue_topic_routing_contracts.json")

    if "timing" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_timing_wait_semantics_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["timing"], payload) and ok
        else:
            _write_json(targets["timing"], payload)
            print("- updated timing_wait_semantics_contracts.json")

    if "cfg" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_pcode_cfg_invariant_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["cfg"], payload) and ok
        else:
            _write_json(targets["cfg"], payload)
            print("- updated pcode_cfg_invariant_snapshots.json")

    if "libsig" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        payload = _build_pcode_libcall_signature_contract_snapshots(vm_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["libsig"], payload) and ok
        else:
            _write_json(targets["libsig"], payload)
            print("- updated pcode_libcall_signature_contracts.json")

    if "ir" in refresh:
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_ir_lift_snapshots(scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["ir"], payload) and ok
        else:
            _write_json(targets["ir"], payload)
            print("- updated pcode_ir_lift_snapshots.json")

    if "struct" in refresh:
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_structuring_snapshots(scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["struct"], payload) and ok
        else:
            _write_json(targets["struct"], payload)
            print("- updated pcode_structuring_snapshots.json")

    if "semantic" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_semantic_annotation_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["semantic"], payload) and ok
        else:
            _write_json(targets["semantic"], payload)
            print("- updated pcode_semantic_annotation_snapshots.json")

    if "symbols" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_symbol_recovery_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["symbols"], payload) and ok
        else:
            _write_json(targets["symbols"], payload)
            print("- updated pcode_symbol_recovery_snapshots.json")

    if "canon" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_symbol_canonicalization_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["canon"], payload) and ok
        else:
            _write_json(targets["canon"], payload)
            print("- updated pcode_symbol_canonicalization_snapshots.json")

    if "pseudo" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_pseudocode_quality_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["pseudo"], payload) and ok
        else:
            _write_json(targets["pseudo"], payload)
            print("- updated pcode_pseudocode_quality_snapshots.json")

    if "emit" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_emitter_output_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["emit"], payload) and ok
        else:
            _write_json(targets["emit"], payload)
            print("- updated pcode_emitter_output_snapshots.json")

    if "bundle" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        payload = _build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir)
        if args.check:
            ok = _check_snapshot(targets["bundle"], payload) and ok
        else:
            _write_json(targets["bundle"], payload)
            print("- updated pcode_scene_decomp_bundle_snapshots.json")

    if "delta" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        current_bundle_payload = _build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir)
        payload = _build_pcode_semantic_delta_report_snapshots(previous_bundle_payload, current_bundle_payload)
        if args.check:
            ok = _check_snapshot(targets["delta"], payload) and ok
        else:
            _write_json(targets["delta"], payload)
            print("- updated pcode_semantic_delta_report_snapshots.json")

    if "digest" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        current_bundle_payload = _build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir)
        if "delta" in refresh:
            delta_payload = _build_pcode_semantic_delta_report_snapshots(previous_bundle_payload, current_bundle_payload)
        else:
            delta_payload = previous_delta_payload if previous_delta_payload else _build_pcode_semantic_delta_report_snapshots(previous_bundle_payload, current_bundle_payload)
        payload = _build_pcode_regression_digest_snapshots(delta_payload, current_bundle_payload)
        if args.check:
            ok = _check_snapshot(targets["digest"], payload) and ok
        else:
            _write_json(targets["digest"], payload)
            print("- updated pcode_regression_digest_snapshots.json")

    if "deliver" in refresh:
        vm_mod = _load_module("tinsel1_vm_lite_module", repo_root / "runtime" / "tinsel1_vm_lite.py")
        scanner_mod = _load_module("tinsel1_pcode_scanner_module", repo_root / "runtime" / "tinsel1_pcode_scanner.py")
        current_bundle_payload = _build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir)
        payload = _build_pcode_decomp_delivery_manifest_snapshots(current_bundle_payload)
        if args.check:
            ok = _check_snapshot(targets["deliver"], payload) and ok
        else:
            _write_json(targets["deliver"], payload)
            print("- updated pcode_decomp_delivery_manifest_snapshots.json")

    if args.check and not ok:
        print("Snapshot drift detected. Run refresh_snapshot_baselines.ps1 intentionally to update baselines.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
