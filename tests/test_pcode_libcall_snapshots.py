from __future__ import annotations

import collections
import importlib.util
import json
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = REPO_ROOT / "runtime" / "tinsel1_pcode_scanner.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_libcall_snapshots.json"
SCENE_SET = ["BAR.SCN", "LIBRARY.SCN", "OBJECTS.SCN", "DW.SCN", "CLIMAX.SCN"]


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


def _build_scene_summary(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts, films = SCANNER.collect_script_handles(scene_path, idx_by_name)

    libcall_names = []
    opcode_names = []
    scripts_scanned = 0

    for script in scripts:
        handle = script["handle"]
        file_index, offset = SCANNER.handle_to_file_offset(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        result = SCANNER.disassemble(data, offset, max_ins=800)
        scripts_scanned += 1
        libcall_names.extend(lc["libcall_name"] for lc in result["libcalls"])
        opcode_names.extend(ins["name"] for ins in result["instructions"])

    return {
        "script_handles_found": len(scripts),
        "scripts_scanned": scripts_scanned,
        "icon_films_found": len(films),
        "libcall_count": len(libcall_names),
        "libcall_histogram": dict(sorted(collections.Counter(libcall_names).items())),
        "opcode_count": len(opcode_names),
        "opcode_histogram": dict(sorted(collections.Counter(opcode_names).items())),
    }


class PcodeLibcallSnapshotTests(unittest.TestCase):
    def test_pcode_and_libcall_snapshots_match_baseline(self):
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
            self.fail("PCODE/libcall snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
