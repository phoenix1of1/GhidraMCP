from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_PATH = REPO_ROOT / "extractor" / "discworld_extract.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "scn_chunk_snapshots.json"


def _load_extractor_module():
    spec = importlib.util.spec_from_file_location("discworld_extract_module", EXTRACTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load extractor module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXTRACTOR = _load_extractor_module()


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


def _actual_scene_snapshot(dataset_dir: Path, scene_name: str) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    chunks = list(EXTRACTOR.walk_chunks(data))

    return {
        "file_size": len(data),
        "chunk_count": len(chunks),
        "chunk_ids": [c["chunk_id"] for c in chunks],
        "chunk_names": [c["chunk_name"] for c in chunks],
        "next_offsets": [c["next_offset"] for c in chunks],
    }


class ScnChunkSnapshotTests(unittest.TestCase):
    def test_scene_snapshots_match_committed_baseline(self):
        dataset = _resolve_dataset_dir()
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name, expected_snapshot in expected.items():
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            actual_snapshot = _actual_scene_snapshot(dataset, scene_name)
            if actual_snapshot != expected_snapshot:
                mismatches[scene_name] = {
                    "expected": expected_snapshot,
                    "actual": actual_snapshot,
                }

        if mismatches:
            self.fail("SCN chunk traversal snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
