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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "inventory_interaction_contracts.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
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
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
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
                _path_depth(event.get("path")),
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
    return {
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
        "inventory_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class InventoryInteractionContractTests(unittest.TestCase):
    def test_inventory_interaction_contract_snapshots_match_baseline(self):
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
            self.fail("Inventory interaction contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
