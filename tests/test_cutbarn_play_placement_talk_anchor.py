from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "playfirst_unresolved_probe"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline_module_cutbarn", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class CutbarnTalkAnchorPlacementTest(unittest.TestCase):
    def test_cutbarn_recovers_talk_anchor_positions(self):
        vm_lite_csv = OUTPUT_ROOT / "vm_lite_trace" / "vm_lite_film_events.csv"
        timeline_csv = OUTPUT_ROOT / "scene_timeline" / "CUTBARN_timeline.csv"
        scheduler_csv = OUTPUT_ROOT / "scheduler" / "scheduler_trace_events.csv"
        for path in (vm_lite_csv, timeline_csv, scheduler_csv):
            if not path.exists():
                self.skipTest(f"Required CUTBARN probe artifact not available: {path}")

        timeline, manifest = BUILDER.build_timeline(
            vm_lite_csv,
            scene_name="CUTBARN.SCN",
            timeline_csv=timeline_csv,
            scheduler_csv=scheduler_csv,
            include_motion_anchor=True,
        )

        play_rows = [row for row in timeline if row.get("libcall") == "PLAY"]
        anchored = [row for row in play_rows if row.get("position_source") == "timeline_talk_anchor"]
        scroll_prefix_rows = [row for row in play_rows if row.get("position_source") == "timeline_scroll_prefix"]
        replay_rows = [row for row in play_rows if row.get("position_source") == "timeline_film_replay"]
        neighbor_rows = [row for row in play_rows if row.get("position_source") == "timeline_neighbor_carry"]

        expected = [
            ("0x23846D14", 114, 38),
            ("0x23846E90", 114, 38),
            ("0x23847190", 114, 36),
            ("0x23847280", 114, 86),
        ]
        actual = [(row["film"], int(row["x_used"]), int(row["y_used"])) for row in anchored[:4]]

        self.assertEqual(actual, expected)
        self.assertGreaterEqual(int(manifest.get("timeline_talk_anchor_events", 0)), 4)

        expected_scroll_prefix = {
            ("0x238473F0", 304, 0),
            ("0x238463F4", 9, 72),
        }
        actual_scroll_prefix = {
            (row["film"], int(row["x_used"]), int(row["y_used"]))
            for row in scroll_prefix_rows
        }
        self.assertEqual(actual_scroll_prefix, expected_scroll_prefix)
        self.assertEqual(int(manifest.get("timeline_scroll_prefix_events", 0)), 2)

        expected_replay = {
            ("0x238463F4", 9, 72),
        }
        actual_replay = {
            (row["film"], int(row["x_used"]), int(row["y_used"]))
            for row in replay_rows
        }
        self.assertEqual(actual_replay, expected_replay)
        self.assertEqual(int(manifest.get("timeline_film_replay_events", 0)), 1)

        expected_neighbor = {
            ("0x23846608", 304, 0),
        }
        actual_neighbor = {
            (row["film"], int(row["x_used"]), int(row["y_used"]))
            for row in neighbor_rows
        }
        self.assertEqual(actual_neighbor, expected_neighbor)
        self.assertEqual(int(manifest.get("timeline_neighbor_carry_events", 0)), 1)


if __name__ == "__main__":
    unittest.main()