from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REFRESH_PATH = REPO_ROOT / "scripts" / "refresh_snapshot_baselines.py"
RENDERER_PATH = REPO_ROOT / "extractor" / "tinsel1_renderer.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "sprite_lossless_contract_snapshots.json"
SCENE_SET = ["BAR.SCN", "LIBRARY.SCN", "OBJECTS.SCN", "DW.SCN", "CLIMAX.SCN"]


def _load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REFRESH = _load_module("refresh_snapshot_baselines_module_sprite", REFRESH_PATH)
RENDERER = _load_module("tinsel1_renderer_module_sprite", RENDERER_PATH)


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


class SpriteLosslessContractSnapshotTests(unittest.TestCase):
    def test_sprite_lossless_contract_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        actual_all = REFRESH._build_sprite_lossless_contract_snapshots(RENDERER, dataset)

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
            self.fail("Sprite lossless contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
