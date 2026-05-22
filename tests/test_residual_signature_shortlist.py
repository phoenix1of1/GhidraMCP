from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "analyze_residual_signature_shortlist.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("residual_signature_shortlist_module", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load residual signature shortlist module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class ResidualSignatureShortlistTest(unittest.TestCase):
    def test_relaxed_tail_family_surfaces_cross_scene_pattern(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            play_export = base / "play_composite_export"
            scene_timeline = base / "scene_timeline"
            scheduler = base / "scheduler"
            play_export.mkdir(parents=True)
            scene_timeline.mkdir(parents=True)
            scheduler.mkdir(parents=True)

            with (play_export / "play_composite_residual_skip_report.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["scene", "seq", "script_handle", "ip", "film_handle"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "scene": "INTROSHA.SCN",
                            "seq": "100",
                            "script_handle": "0xAAA",
                            "ip": "300",
                            "film_handle": "0xF1",
                        },
                        {
                            "scene": "OVEREDGE.SCN",
                            "seq": "200",
                            "script_handle": "0xBBB",
                            "ip": "400",
                            "film_handle": "0xF2",
                        },
                    ]
                )

            with (scheduler / "scheduler_trace_events.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["file", "script_handle", "ip", "visible_stack"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "file": "INTROSHA.SCN",
                            "script_handle": "0xAAA",
                            "ip": "300",
                            "visible_stack": "imm:0 | imm:0 | imm:16 | imm:1 | film:0xF1 | imm:-1 | imm:-1",
                        },
                        {
                            "file": "OVEREDGE.SCN",
                            "script_handle": "0xBBB",
                            "ip": "400",
                            "visible_stack": "imm:0 | imm:0 | imm:6 | imm:1 | film:0xF2 | imm:-1 | imm:-1",
                        },
                    ]
                )

            for scene_name, ip in (("INTROSHA", "300"), ("OVEREDGE", "400")):
                with (scene_timeline / f"{scene_name}_timeline.csv").open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["ip", "libcall"])
                    writer.writeheader()
                    writer.writerows(
                        [
                            {"ip": "100", "libcall": "BACKGROUND"},
                            {"ip": "200", "libcall": "PLAY"},
                            {"ip": "250", "libcall": "WAITTIME"},
                            {"ip": ip, "libcall": "PLAY"},
                        ]
                    )

            _rows, summary = MODULE.analyze(base)

        family = next(
            row
            for row in summary["top_family_signatures"]
            if row["family_kind"] == "tail2"
            and row["family_signature"] == "tail2=PLAY>WAITTIME|stack_prefix_imm=4"
        )
        self.assertEqual(family["count"], 2)
        self.assertEqual(family["scene_count"], 2)
        self.assertEqual(family["scenes"], ["INTROSHA.SCN", "OVEREDGE.SCN"])


if __name__ == "__main__":
    unittest.main()