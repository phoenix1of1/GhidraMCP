from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "playcomposite_confidence_probe"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline_bootstrap", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class SingletonBootstrapCarryCasesTest(unittest.TestCase):
    def _build_scene(self, scene_name: str):
        stem = Path(scene_name).stem
        vm_lite_csv = OUTPUT_ROOT / "vm_lite_trace" / "vm_lite_film_events.csv"
        timeline_csv = OUTPUT_ROOT / "scene_timeline" / f"{stem}_timeline.csv"
        scheduler_csv = OUTPUT_ROOT / "scheduler" / "scheduler_trace_events.csv"
        for path in (vm_lite_csv, timeline_csv, scheduler_csv):
            if not path.exists():
                self.skipTest(f"Required probe artifact not available: {path}")

        return BUILDER.build_timeline(
            vm_lite_csv,
            scene_name=scene_name,
            timeline_csv=timeline_csv,
            scheduler_csv=scheduler_csv,
            include_motion_anchor=True,
        )

    def test_cutbarn_bootstrap_carry(self):
        timeline, manifest = self._build_scene("CUTBARN.SCN")
        rows = [
            row
            for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_bootstrap_carry"
            and row.get("film") == "0x23846B7C"
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((int(row["x_used"]), int(row["y_used"])), (114, 38))
        self.assertGreaterEqual(int(manifest.get("timeline_bootstrap_carry_events", 0)), 1)

    def test_introsha_bootstrap_carry(self):
        timeline, manifest = self._build_scene("INTROSHA.SCN")
        rows = [
            row
            for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_bootstrap_carry"
            and row.get("film") == "0x29037014"
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((int(row["x_used"]), int(row["y_used"])), (263, 87))
        self.assertGreaterEqual(int(manifest.get("timeline_bootstrap_carry_events", 0)), 1)

    def test_square2_bootstrap_carry(self):
        timeline, manifest = self._build_scene("SQUARE2.SCN")
        rows = [
            row
            for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_bootstrap_carry"
            and row.get("film") in {"0x178542F0", "0x178546E8"}
        ]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual((int(row["x_used"]), int(row["y_used"])), (8, 550))
        self.assertGreaterEqual(int(manifest.get("timeline_bootstrap_carry_events", 0)), 2)

    def test_square3_bootstrap_carry(self):
        timeline, manifest = self._build_scene("SQUARE3.SCN")
        rows = [
            row
            for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_bootstrap_carry"
            and row.get("film") in {"0x1804DA68", "0x1804DE60"}
        ]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual((int(row["x_used"]), int(row["y_used"])), (8, 550))
        self.assertGreaterEqual(int(manifest.get("timeline_bootstrap_carry_events", 0)), 2)


if __name__ == "__main__":
    unittest.main()
