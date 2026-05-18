from __future__ import annotations

import collections
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VM_LITE_PATH = REPO_ROOT / "runtime" / "tinsel1_vm_lite.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "scheduler_event_snapshots.json"
SCENE_SET = ["BAR.SCN", "LIBRARY.SCN", "OBJECTS.SCN", "DW.SCN", "CLIMAX.SCN"]
MAX_SCRIPTS_PER_SCENE = 60
MAX_STEPS = 1200
MAX_PATHS = 16
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


def _scene_scheduler_summary(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))
    scripts = scripts[:MAX_SCRIPTS_PER_SCENE]

    all_libcalls = []
    scheduler_libcalls = []
    film_scheduler_with_args = 0

    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
        for event in trace["events"]:
            if event.get("event") != "libcall":
                continue

            libcall_name = event.get("libcall_name")
            all_libcalls.append(libcall_name)

            if libcall_name in SCHEDULER_LIBCALLS:
                scheduler_libcalls.append(libcall_name)
                if libcall_name in FILM_SCHEDULER_LIBCALLS and event.get("film_args"):
                    film_scheduler_with_args += 1

    return {
        "script_handles_found": len(VM.collect_script_handles(scene_path, idx_by_name)),
        "scripts_traced": len(scripts),
        "libcall_events_total": len(all_libcalls),
        "scheduler_event_count": len(scheduler_libcalls),
        "film_scheduler_events_with_film_args": film_scheduler_with_args,
        "scheduler_histogram": dict(sorted(collections.Counter(scheduler_libcalls).items())),
    }


class SchedulerEventSnapshotTests(unittest.TestCase):
    def test_scheduler_event_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        idx_rows = VM.read_index(dataset / "INDEX")
        idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            actual = _scene_scheduler_summary(dataset, scene_name, idx_by_name)
            expected_scene = expected.get(scene_name)
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual}
                continue
            if actual != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual}

        if mismatches:
            self.fail("Scheduler-event snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
