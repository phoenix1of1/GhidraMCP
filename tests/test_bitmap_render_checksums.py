from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = REPO_ROOT / "extractor" / "tinsel1_renderer.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "bitmap_render_checksums.json"


def _load_renderer_module():
    spec = importlib.util.spec_from_file_location("tinsel1_renderer_module", RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load renderer module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = _load_renderer_module()


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


def _image_checksum_snapshot(scene_obj, rec) -> dict:
    indexed_pixels, stats = scene_obj.render_wrt_nonzero(rec)
    palette = scene_obj.palette(rec.palette_offset)

    rgba = bytearray()
    for pixel_index in indexed_pixels:
        rgba.extend(palette[pixel_index])

    return {
        "index": rec.index,
        "width": rec.width,
        "height": rec.height,
        "indexed_sha256": hashlib.sha256(bytes(indexed_pixels)).hexdigest(),
        "rgba_sha256": hashlib.sha256(bytes(rgba)).hexdigest(),
        "consumed_index_bytes": stats.consumed_index_bytes,
    }


class BitmapRenderChecksumTests(unittest.TestCase):
    def test_bitmap_render_checksums_match_snapshot(self):
        dataset = _resolve_dataset_dir()
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name, expected_entries in expected.items():
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            scene = RENDERER.Tinsel1Scene(scene_path)
            records = scene.image_records()

            actual_entries = []
            for expected_entry in expected_entries:
                image_index = expected_entry["index"]
                self.assertLess(image_index, len(records), f"Image index out of bounds for {scene_name}: {image_index}")
                rec = records[image_index]
                actual_entries.append(_image_checksum_snapshot(scene, rec))

            if actual_entries != expected_entries:
                mismatches[scene_name] = {
                    "expected": expected_entries,
                    "actual": actual_entries,
                }

        if mismatches:
            self.fail("Bitmap render checksum snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
