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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "timing_wait_semantics_contracts.json"
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
TIMING_WAIT_CALLS = {"WAITFRAME", "WAITTIME", "EVENT"}
TIMING_DIALOGUE_CALLS = {"CONVERSATION", "CONVTOPIC", "ADDTOPIC", "TALK", "TALKAT", "TALKATS"}
TIMING_PLAY_CALLS = {"PLAY", "TOPPLAY", "SPLAY", "STAND", "SWALK", "WALK"}
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

    wait_sequence: list[str] = []
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
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
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
                local_scheduler_sequence.append(name)

            if name not in TIMING_WAIT_CALLS:
                continue

            has_timing = True
            wait_sequence.append(name)
            wait_histogram[name] += 1

            depth = int(event.get("stack_depth") or 0)
            stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
            stack_depth_max = max(stack_depth_max, depth)
            max_path_depth_at_timing_event = max(max_path_depth_at_timing_event, _path_depth(event.get("path")))

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
    return {
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


class TimingWaitSemanticsContractTests(unittest.TestCase):
    def test_timing_wait_semantics_contract_snapshots_match_baseline(self):
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
            self.fail("Timing/wait semantics contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
