from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "playcomposite_waitframe_prefix_probe"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline_known_non_tiny", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class KnownNonTinyPrefixCasesTest(unittest.TestCase):
    def _assert_case(
        self,
        scene_name: str,
        expected_film: str,
        expected_xy: tuple[int, int],
    ) -> None:
        vm_lite_csv = OUTPUT_ROOT / "vm_lite_trace" / "vm_lite_film_events.csv"
        timeline_csv = OUTPUT_ROOT / "scene_timeline" / f"{Path(scene_name).stem}_timeline.csv"
        scheduler_csv = OUTPUT_ROOT / "scheduler" / "scheduler_trace_events.csv"
        for path in (vm_lite_csv, timeline_csv, scheduler_csv):
            if not path.exists():
                self.skipTest(f"Required probe artifact not available: {path}")

        timeline, manifest = BUILDER.build_timeline(
            vm_lite_csv,
            scene_name=scene_name,
            timeline_csv=timeline_csv,
            scheduler_csv=scheduler_csv,
            include_motion_anchor=True,
        )

        rows = [
            row for row in timeline
            if row.get("libcall") == "PLAY"
            and row.get("position_source") == "timeline_prefix_known_non_tiny"
            and row.get("film") == expected_film
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((int(row["x_used"]), int(row["y_used"])), expected_xy)
        self.assertGreaterEqual(int(manifest.get("timeline_prefix_known_non_tiny_events", 0)), 1)

    def test_introsha_known_case(self):
        self._assert_case(
            scene_name="INTROSHA.SCN",
            expected_film="0x29037050",
            expected_xy=(263, 87),
        )

    def test_overedge_known_case(self):
        self._assert_case(
            scene_name="OVEREDGE.SCN",
            expected_film="0x20009D24",
            expected_xy=(0, 200),
        )


if __name__ == "__main__":
    unittest.main()
