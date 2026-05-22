from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bar_play_placement_timeline.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "finale_play_placement_timeline_diagnostic_snapshots.json"
DEFAULT_VM_LITE_CSV = REPO_ROOT.parent / "discworld_all_generated_csvs" / "vm_lite_film_events.csv"
DEFAULT_TIMELINE_CSV = REPO_ROOT / "outputs" / "bar_pipeline" / "scene_timeline" / "FINALE_timeline.csv"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("build_scene_play_placement_timeline_module", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load placement timeline builder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder_module()


class FinalePlayPlacementTimelineDiagnosticSnapshotsTest(unittest.TestCase):
    def test_finale_play_placement_timeline_diagnostic_snapshot(self):
        if not DEFAULT_VM_LITE_CSV.exists():
            self.skipTest(f"vm-lite CSV not available: {DEFAULT_VM_LITE_CSV}")
        if not DEFAULT_TIMELINE_CSV.exists():
            self.skipTest(f"scene timeline CSV not available: {DEFAULT_TIMELINE_CSV}")

        timeline, manifest = BUILDER.build_timeline(
            DEFAULT_VM_LITE_CSV,
            scene_name="FINALE.SCN",
            include_block_probe=True,
            timeline_csv=DEFAULT_TIMELINE_CSV,
            include_motion_anchor=True,
        )

        plays = [row for row in timeline if row.get("libcall") == "PLAY"]
        source_counts: dict[str, int] = {}
        for row in plays:
            key = str(row.get("position_source") or "")
            source_counts[key] = source_counts.get(key, 0) + 1

        probe_rows = [row for row in timeline if row.get("libcall") == "PLAY_PROBE"]
        probe_row = probe_rows[0] if probe_rows else None

        def _to_bool(value):
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes"}

        actual = {
            "FINALE.SCN": {
                "manifest_subset": {
                    "event_count_total": int(manifest["event_count_total"]),
                    "background_events": int(manifest["background_events"]),
                    "play_events": int(manifest["play_events"]),
                    "nominal_seeded_events": int(manifest["nominal_seeded_events"]),
                    "fallback_events": int(manifest["fallback_events"]),
                    "decoded_nonzero_events": int(manifest.get("decoded_nonzero_events", 0)),
                    "decoded_zero_events": int(manifest.get("decoded_zero_events", 0)),
                    "block_snap_applied_events": int(manifest.get("block_snap_applied_events", 0)),
                    "block_probe_added": bool(manifest.get("block_probe_added", False)),
                    "timeline_args_events": int(manifest.get("timeline_args_events", 0)),
                    "timeline_offset_events": int(manifest.get("timeline_offset_events", 0)),
                    "timeline_motion_events": int(manifest.get("timeline_motion_events", 0)),
                    "timeline_actor_state_events": int(manifest.get("timeline_actor_state_events", 0)),
                },
                "play_source_counts": dict(sorted(source_counts.items())),
                "probe_row": {
                    "output_frame": int(probe_row["output_frame"]),
                    "event_seq": int(probe_row["event_seq"]),
                    "libcall": probe_row["libcall"],
                    "film": probe_row["film"],
                    "event_frame": int(probe_row["event_frame"]),
                    "x_used": int(probe_row["x_used"]),
                    "y_used": int(probe_row["y_used"]),
                    "position_source": probe_row["position_source"],
                    "runtime_snap_applied": _to_bool(probe_row["runtime_snap_applied"]),
                    "source_png": probe_row["source_png"],
                }
                if probe_row
                else None,
            }
        }

        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
