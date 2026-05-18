from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REFRESH_PATH = REPO_ROOT / "scripts" / "refresh_snapshot_baselines.py"
VM_LITE_PATH = REPO_ROOT / "runtime" / "tinsel1_vm_lite.py"
SCANNER_PATH = REPO_ROOT / "runtime" / "tinsel1_pcode_scanner.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_emitter_output_snapshots.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]


def _load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REFRESH = _load_module("refresh_snapshot_baselines_module", REFRESH_PATH)
VM = _load_module("tinsel1_vm_lite_module", VM_LITE_PATH)
SCANNER = _load_module("tinsel1_pcode_scanner_module", SCANNER_PATH)


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


class PcodeEmitterOutputSnapshotTests(unittest.TestCase):
    def test_pcode_emitter_output_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        actual_all = REFRESH._build_pcode_emitter_output_snapshots(VM, SCANNER, dataset)

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")

            actual_scene = actual_all.get(scene_name)
            expected_scene = expected.get(scene_name)
            if actual_scene is None:
                mismatches[scene_name] = {"error": "missing actual scene snapshot"}
                continue
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual_scene}
                continue
            if actual_scene != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual_scene}

        if mismatches:
            self.fail("Pcode emitter output snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
