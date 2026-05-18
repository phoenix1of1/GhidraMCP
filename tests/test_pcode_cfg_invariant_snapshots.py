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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_cfg_invariant_snapshots.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
CFG_EVENT_NAMES = {"jump", "conditional_jump"}
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
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
        events = trace.get("events", [])
        states = trace.get("final_states", [])

        local_cfg_sequence: list[str] = []
        for event in events:
            max_path_depth = max(max_path_depth, _path_depth(event.get("path")))
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
            max_path_depth = max(max_path_depth, _path_depth(state.get("path")))

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
    return {
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


class PcodeCfgInvariantSnapshotTests(unittest.TestCase):
    def test_pcode_cfg_invariant_snapshots_match_baseline(self):
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
            self.fail("Pcode CFG invariant snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
