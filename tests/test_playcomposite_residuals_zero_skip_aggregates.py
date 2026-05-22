from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "analyze_playcomposite_residuals.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("analyze_playcomposite_residuals_module", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load playcomposite residual analyzer module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class PlaycompositeResidualsZeroSkipAggregatesTest(unittest.TestCase):
    def test_zero_skip_scene_still_contributes_trusted_aggregates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            play_export = base / "play_composite_export"
            play_export.mkdir(parents=True)

            timeline_path = base / "scene_timeline.csv"
            with timeline_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["libcall", "event_seq", "x_used", "y_used", "position_source", "placement_confidence"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "libcall": "PLAY",
                            "event_seq": "0",
                            "x_used": "100",
                            "y_used": "50",
                            "position_source": "timeline_talk_anchor",
                            "placement_confidence": "high",
                        },
                        {
                            "libcall": "PLAY",
                            "event_seq": "1",
                            "x_used": "102",
                            "y_used": "52",
                            "position_source": "timeline_talk_anchor",
                            "placement_confidence": "high",
                        },
                        {
                            "libcall": "PLAY",
                            "event_seq": "2",
                            "x_used": "-1",
                            "y_used": "-1",
                            "position_source": "fallback_visual_validation",
                            "placement_confidence": "low",
                        },
                    ]
                )

            with (play_export / "play_composite_export_summary.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["scene", "skipped_negative_xy_count", "position_timeline", "position_timeline_mode"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "scene": "TEST.SCN",
                        "skipped_negative_xy_count": "0",
                        "position_timeline": str(timeline_path),
                        "position_timeline_mode": "generated_scene_space_timeline",
                    }
                )

            residual_rows, summary = MODULE.analyze(base)

        self.assertEqual(residual_rows, [])
        self.assertEqual(summary["residual_skip_count"], 0)
        self.assertEqual(summary["trusted_generated_confidence_counts"], {"high": 2})
        self.assertEqual(summary["trusted_generated_source_counts"], {"timeline_talk_anchor": 2})

        candidates = summary["confidence_promotion_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source"], "timeline_talk_anchor")
        self.assertEqual(candidates[0]["trusted_rows"], 2)
        self.assertEqual(candidates[0]["negative_rows"], 0)


if __name__ == "__main__":
    unittest.main()
