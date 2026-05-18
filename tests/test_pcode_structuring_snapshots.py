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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_structuring_snapshots.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
MAX_INS = 800
REGION_SIGNATURE_LIMIT = 60


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


def _build_scene_summary(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts, films = SCANNER.collect_script_handles(scene_path, idx_by_name)
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
        file_index, offset = SCANNER.handle_to_file_offset(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        result = SCANNER.disassemble(data, offset, max_ins=MAX_INS)
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
    sequence_head = region_sequence[:REGION_SIGNATURE_LIMIT]
    return {
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
        "top_region_signatures_sha256": hashlib.sha256("|".join(top_region_signatures).encode("utf-8")).hexdigest(),
        "region_signature_sequence_head": sequence_head,
        "region_signature_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class PcodeStructuringSnapshotTests(unittest.TestCase):
    def test_pcode_structuring_snapshots_match_baseline(self):
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
            self.fail("Pcode structuring snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
