from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "evaluate_confidence_promotions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_confidence_promotions_module", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load confidence promotion evaluator module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class ConfidencePromotionEvaluatorTest(unittest.TestCase):
    def test_evaluator_applies_thresholds(self):
        payload = {
            "confidence_promotion_candidates": [
                {"source": "src_good", "trusted_rows": 3, "negative_rows": 0},
                {"source": "src_low_volume", "trusted_rows": 1, "negative_rows": 0},
                {"source": "src_negative", "trusted_rows": 5, "negative_rows": 1},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "summary.json"
            summary_path.write_text(json.dumps(payload), encoding="utf-8")

            result = MODULE.evaluate(
                summary_path=summary_path,
                min_trusted_rows=2,
                require_zero_negative=True,
            )

        promoted_sources = {row["source"] for row in result["promoted"]}
        deferred_sources = {row["source"] for row in result["deferred"]}

        self.assertEqual(promoted_sources, {"src_good"})
        self.assertEqual(deferred_sources, {"src_low_volume", "src_negative"})
        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(result["deferred_count"], 2)


if __name__ == "__main__":
    unittest.main()
