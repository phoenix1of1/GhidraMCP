from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "triage_waittime_family_frontier.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("waittime_frontier_triage_module", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load waittime frontier triage module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class WaittimeFrontierTriageTest(unittest.TestCase):
    def test_rejected_examples_are_reported_when_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            export_dir = base / "play_composite_export"
            export_dir.mkdir(parents=True)

            rows = [
                {
                    "scene": "BAR.SCN",
                    "seq": "10",
                    "ip": "100",
                    "film_handle": "0x1",
                    "family_tail1": "tail1=PLAY>WAITFRAME|stack_prefix_imm=2",
                    "family_tail2": "",
                },
                {
                    "scene": "CLIMAX.SCN",
                    "seq": "11",
                    "ip": "101",
                    "film_handle": "0x2",
                    "family_tail1": "tail1=PLAY>WAITFRAME|stack_prefix_imm=2",
                    "family_tail2": "",
                },
                {
                    "scene": "DW.SCN",
                    "seq": "12",
                    "ip": "102",
                    "film_handle": "0x3",
                    "family_tail1": "tail1=PLAY>WAITFRAME|stack_prefix_imm=2",
                    "family_tail2": "",
                },
            ]

            with (export_dir / "residual_signature_shortlist.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["scene", "seq", "ip", "film_handle", "family_tail1", "family_tail2"],
                )
                writer.writeheader()
                writer.writerows(rows)

            _candidates, summary = MODULE.triage(
                base=base,
                max_scene_count=2,
                require_tokens=["TALK", "TALKAT"],
                exclude_families=set(),
            )

        self.assertEqual(summary["candidate_count"], 0)
        self.assertIn("too_broad_scene_count", summary["rejected_counts"])
        self.assertGreater(summary["rejected_counts"]["too_broad_scene_count"], 0)
        self.assertIn("too_broad_scene_count", summary["rejected_examples"])
        sample = summary["rejected_examples"]["too_broad_scene_count"][0]
        self.assertEqual(sample["family_signature"], "tail1=PLAY>WAITFRAME|stack_prefix_imm=2")
        self.assertEqual(sample["scene_count"], 3)
        self.assertEqual(sample["scenes"], ["BAR.SCN", "CLIMAX.SCN", "DW.SCN"])

    def test_recommended_one_off_probes_surface_tight_play_families(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            export_dir = base / "play_composite_export"
            export_dir.mkdir(parents=True)

            rows = [
                {
                    "scene": "BAR.SCN",
                    "seq": "20",
                    "ip": "200",
                    "film_handle": "0x10",
                    "family_tail1": "tail1=PLAY>WAITFRAME|stack_prefix_imm=2",
                    "family_tail2": "",
                },
                {
                    "scene": "CLIMAX.SCN",
                    "seq": "21",
                    "ip": "201",
                    "film_handle": "0x11",
                    "family_tail1": "tail1=PLAY>WAITFRAME|stack_prefix_imm=2",
                    "family_tail2": "",
                },
                {
                    "scene": "LIBRARY.SCN",
                    "seq": "22",
                    "ip": "202",
                    "film_handle": "0x12",
                    "family_tail1": "tail1=PLAY|stack_prefix_imm=2",
                    "family_tail2": "",
                },
            ]

            with (export_dir / "residual_signature_shortlist.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["scene", "seq", "ip", "film_handle", "family_tail1", "family_tail2"],
                )
                writer.writeheader()
                writer.writerows(rows)

            _candidates, summary = MODULE.triage(
                base=base,
                max_scene_count=2,
                require_tokens=["TALK", "TALKAT"],
                exclude_families=set(),
            )

        self.assertEqual(summary["candidate_count"], 0)
        recommendations = summary["recommended_one_off_probes"]
        self.assertEqual(len(recommendations), 2)
        self.assertEqual(recommendations[0]["family_signature"], "tail1=PLAY|stack_prefix_imm=2")
        self.assertEqual(recommendations[1]["family_signature"], "tail1=PLAY>WAITFRAME|stack_prefix_imm=2")


if __name__ == "__main__":
    unittest.main()
