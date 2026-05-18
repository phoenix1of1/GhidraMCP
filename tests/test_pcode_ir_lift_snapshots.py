from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = REPO_ROOT / "runtime" / "tinsel1_pcode_scanner.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_ir_lift_snapshots.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
MAX_INS = 800


def _load_scanner_module():
    spec = importlib.util.spec_from_file_location("tinsel1_pcode_scanner_module", SCANNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load pcode scanner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCANNER = _load_scanner_module()


def _resolve_dataset_dir() -> Path:
    env_input = os.environ.get("DISCWORLD_TEST_INPUT")
    if env_input:
        candidate = Path(env_input).resolve()
        if (candidate / "INDEX").exists():
            return candidate

    candidates = [
        REPO_ROOT.parent / "clean-game" / "DISCWLD",
        REPO_ROOT.parent / "clean-game",
        REPO_ROOT / "sample_data",
    ]

    for candidate in candidates:
        if (candidate / "INDEX").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate test dataset with INDEX file. "
        "Tried: " + ", ".join(str(p) for p in candidates)
    )


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


def _build_scene_summary(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts, films = SCANNER.collect_script_handles(scene_path, idx_by_name)
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
        file_index, offset = SCANNER.handle_to_file_offset(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        result = SCANNER.disassemble(data, offset, max_ins=MAX_INS)
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
    return {
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
        "ir_block_terminator_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class PcodeIrLiftSnapshotTests(unittest.TestCase):
    def test_pcode_ir_lift_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        idx_rows = SCANNER.read_index(dataset / "INDEX")
        idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")

            actual = _build_scene_summary(dataset, scene_name, idx_by_name)
            expected_scene = expected.get(scene_name)
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual}
                continue
            if actual != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual}

        if mismatches:
            self.fail("Pcode IR lift snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
