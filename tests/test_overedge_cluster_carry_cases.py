from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "playcomposite_confidence_probe"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline_overedge_cluster", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class OveredgeClusterCarryCasesTest(unittest.TestCase):
    def test_overedge_cluster_carry_rows(self):
        vm_lite_csv = OUTPUT_ROOT / "vm_lite_trace" / "vm_lite_film_events.csv"
        timeline_csv = OUTPUT_ROOT / "scene_timeline" / "OVEREDGE_timeline.csv"
        scheduler_csv = OUTPUT_ROOT / "scheduler" / "scheduler_trace_events.csv"
        for path in (vm_lite_csv, timeline_csv, scheduler_csv):
            if not path.exists():
                self.skipTest(f"Required probe artifact not available: {path}")

        timeline, manifest = BUILDER.build_timeline(
            vm_lite_csv,
            scene_name="OVEREDGE.SCN",
            timeline_csv=timeline_csv,
            scheduler_csv=scheduler_csv,
            include_motion_anchor=True,
        )

        rows = [
            row
            for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_overedge_cluster_carry"
            and row.get("film") in {"0x20009324", "0x2000975C"}
        ]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual((int(row["x_used"]), int(row["y_used"])), (323, 64))
        self.assertGreaterEqual(int(manifest.get("timeline_overedge_cluster_carry_events", 0)), 3)


if __name__ == "__main__":
    unittest.main()
