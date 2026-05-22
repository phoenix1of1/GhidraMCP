from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "bar_play_placement_timeline_contract_snapshots.json"
DEFAULT_VM_LITE_CSV = REPO_ROOT.parent / "discworld_all_generated_csvs" / "vm_lite_film_events.csv"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline_module", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load BAR placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class BarPlayPlacementTimelineContractSnapshotsTest(unittest.TestCase):
    def test_bar_play_placement_timeline_contract_snapshot(self):
        if not DEFAULT_VM_LITE_CSV.exists():
            self.skipTest(f"vm-lite CSV not available: {DEFAULT_VM_LITE_CSV}")

        timeline, manifest = BUILDER.build_timeline(DEFAULT_VM_LITE_CSV)
        play_film_handles = sorted({row["film"] for row in timeline if row.get("libcall") == "PLAY"})

        first_events = []
        for row in timeline[:5]:
            first_events.append(
                {
                    "output_frame": int(row["output_frame"]),
                    "event_seq": int(row["event_seq"]),
                    "libcall": row["libcall"],
                    "film": row["film"],
                    "x_used": int(row["x_used"]),
                    "y_used": int(row["y_used"]),
                    "position_source": row["position_source"],
                }
            )

        actual = {
            "BAR.SCN": {
                "event_count_total": int(manifest["event_count_total"]),
                "background_events": int(manifest["background_events"]),
                "play_events": int(manifest["play_events"]),
                "nominal_seeded_events": int(manifest["nominal_seeded_events"]),
                "fallback_events": int(manifest["fallback_events"]),
                "decoded_nonzero_events": int(manifest.get("decoded_nonzero_events", 0)),
                "decoded_zero_events": int(manifest.get("decoded_zero_events", 0)),
                "block_snap_applied_events": int(manifest.get("block_snap_applied_events", 0)),
                "play_unique_films": len(play_film_handles),
                "play_film_handles": play_film_handles,
                "first_events": first_events,
            }
        }

        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
