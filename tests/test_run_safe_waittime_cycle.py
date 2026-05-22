from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_safe_waittime_cycle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_safe_waittime_cycle_module", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load safe waittime cycle module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class RunSafeWaittimeCycleHelpersTest(unittest.TestCase):
    def test_select_candidate_strategy(self):
        candidates = [
            {"family_signature": "A", "scene_count": 2, "count": 5},
            {"family_signature": "B", "scene_count": 1, "count": 3},
            {"family_signature": "C", "scene_count": 1, "count": 1},
        ]

        smallest = MODULE._select_candidate(candidates, "smallest")
        largest = MODULE._select_candidate(candidates, "largest")

        self.assertEqual([item["family_signature"] for item in smallest], ["C", "B", "A"])
        self.assertEqual([item["family_signature"] for item in largest], ["A", "B", "C"])

    def test_probe_registry_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry_path = Path(tmp_dir) / "probe_registry.json"

            registry = MODULE._load_probe_registry(registry_path)
            self.assertEqual(registry["version"], 1)
            self.assertEqual(registry["one_off_probes"], {})
            self.assertFalse(MODULE._was_one_off_probed(registry, "tail1=PLAY|stack_prefix_imm=2"))

            MODULE._record_one_off_probe_result(
                registry,
                "tail1=PLAY|stack_prefix_imm=2",
                {
                    "status": "diagnostic_ran",
                    "diagnostic_exit_code": 0,
                    "rows_analyzed": 1,
                    "carry_viability_counts": {"carry_not_viable": 1},
                    "nearest_anchor_type_counts": {"none": 1},
                },
            )
            MODULE._save_probe_registry(registry_path, registry)

            reloaded = MODULE._load_probe_registry(registry_path)
            self.assertTrue(MODULE._was_one_off_probed(reloaded, "tail1=PLAY|stack_prefix_imm=2"))
            entry = reloaded["one_off_probes"]["tail1=PLAY|stack_prefix_imm=2"]
            self.assertEqual(entry["attempts"], 1)
            self.assertEqual(entry["last_status"], "diagnostic_ran")
            self.assertEqual(entry["last_rows_analyzed"], 1)
            self.assertEqual(entry["last_carry_viability_counts"], {"carry_not_viable": 1})

            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("one_off_probes", payload)

    def test_queue_log_append_writes_structured_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            queue_log = Path(tmp_dir) / "QUEUE.md"
            queue_log.write_text("# Queue\n", encoding="utf-8")

            MODULE._append_queue_log_entry(
                queue_log,
                {
                    "status": "diagnostic_ran",
                    "selected_source": "one_off_probe",
                    "selected_family": "tail1=PLAY|stack_prefix_imm=2",
                    "diagnostic_exit_code": 0,
                    "rows_analyzed": 1,
                    "carry_viability_counts": {"carry_not_viable": 1},
                    "nearest_anchor_type_counts": {"none": 1},
                    "triage_summary": "C:/tmp/triage.json",
                    "diagnostic_summary": "C:/tmp/diag.json",
                },
            )

            text = queue_log.read_text(encoding="utf-8")
            self.assertIn("## Cycle Log", text)
            self.assertIn("### Outcome", text)
            self.assertIn("selected_source", text)
            self.assertIn("tail1=PLAY|stack_prefix_imm=2", text)


if __name__ == "__main__":
    unittest.main()
