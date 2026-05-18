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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "scheduler_side_effect_contracts.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
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
CORE_CALLS = ["PLAY", "WAITFRAME", "WAITTIME", "CONTROL", "TALK", "PLAYSAMPLE"]


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


def _scene_contract_snapshot(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

    scheduler_names: list[str] = []
    contracts: dict[str, dict] = {}
    scripts_with_scheduler_events = 0

    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=1200, max_paths=16)
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

    for call in CORE_CALLS:
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
    return {
        "scripts_traced": len(scripts),
        "scripts_with_scheduler_events": scripts_with_scheduler_events,
        "scheduler_event_count": len(scheduler_names),
        "core_call_counts": {call: contracts[call]["count"] for call in CORE_CALLS},
        "libcall_contracts": {key: contracts[key] for key in sorted(contracts.keys())},
        "transition_histogram": dict(sorted(transitions.items())),
        "sequence_head": sequence_head,
        "sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class SchedulerSideEffectContractTests(unittest.TestCase):
    def test_scheduler_side_effect_contract_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        idx_rows = VM.read_index(dataset / "INDEX")
        idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            actual = _scene_contract_snapshot(dataset, scene_name, idx_by_name)
            expected_scene = expected.get(scene_name)
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual}
                continue
            if actual != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual}

        if mismatches:
            self.fail("Scheduler side-effect contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
