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
        choices=["scn", "pcode", "bitmap", "scheduler", "placement", "contracts", "branch", "inventory", "hotspot", "dialogue", "timing", "cfg", "libsig", "ir", "all"],
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
        refresh = {"scn", "pcode", "bitmap", "scheduler", "placement", "contracts", "branch", "inventory", "hotspot", "dialogue", "timing", "cfg", "libsig", "ir"}

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
    }

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

    if args.check and not ok:
        print("Snapshot drift detected. Run refresh_snapshot_baselines.ps1 intentionally to update baselines.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
