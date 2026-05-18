from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VM_LITE_PATH = REPO_ROOT / "runtime" / "tinsel1_vm_lite.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "branch_convergence_contracts.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
MAX_STEPS = 1200
MAX_PATHS = 16


def _load_vm_lite_module():
    spec = importlib.util.spec_from_file_location("tinsel1_vm_lite_module", VM_LITE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load vm-lite module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VM = _load_vm_lite_module()


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


def _path_depth(path_name: str | None) -> int:
    if not path_name:
        return 0
    return str(path_name).count(".br")


def _scene_snapshot(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

    max_branch_fanout = 0
    max_path_depth = 0
    truncated_paths_max_steps = 0
    truncated_paths_max_paths = 0
    branch_opcode_histogram = collections.Counter()

    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
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

            max_path_depth = max(max_path_depth, _path_depth(event.get("path")))

        for state in states:
            max_path_depth = max(max_path_depth, _path_depth(state.get("path")))
            if int(state.get("steps") or 0) >= MAX_STEPS:
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
    return {
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


class BranchConvergenceContractTests(unittest.TestCase):
    def test_branch_convergence_contract_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        idx_rows = VM.read_index(dataset / "INDEX")
        idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            actual = _scene_snapshot(dataset, scene_name, idx_by_name)
            expected_scene = expected.get(scene_name)
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual}
                continue
            if actual != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual}

        if mismatches:
            self.fail("Branch convergence contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
