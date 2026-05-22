import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = WORKSPACE_ROOT / "scripts" / "build_bar_play_placement_timeline.py"

spec = importlib.util.spec_from_file_location("build_bar_play_placement_timeline", SCRIPT_PATH)
assert spec and spec.loader
BUILDER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILDER)


class ClimaxTalkatExperimentalGateTests(unittest.TestCase):
    def test_default_off_keeps_baseline_age_limit(self) -> None:
        row = {"script_handle": "0x0406d43c", "ip": "447558"}
        with patch.dict(os.environ, {BUILDER.EXPERIMENT_CLIMAX_TALKAT_AGE_ENV: "0"}, clear=False):
            limit = BUILDER._dialogue_anchor_age_limit("CLIMAX.SCN", row, "timeline_talkat_anchor")
        self.assertEqual(limit, BUILDER.TALK_ANCHOR_MAX_AGE)

    def test_opt_in_extends_allowlisted_climax_keys_only(self) -> None:
        row = {"script_handle": "0x0406d43c", "ip": "447558"}
        with patch.dict(os.environ, {BUILDER.EXPERIMENT_CLIMAX_TALKAT_AGE_ENV: "1"}, clear=False):
            limit = BUILDER._dialogue_anchor_age_limit("CLIMAX.SCN", row, "timeline_talkat_anchor")
        self.assertEqual(limit, BUILDER.EXPERIMENT_CLIMAX_TALKAT_MAX_AGE)

    def test_opt_in_does_not_extend_non_allowlisted_or_talk(self) -> None:
        non_allowlisted = {"script_handle": "0x0406d43c", "ip": "447559"}
        allowlisted = {"script_handle": "0x0406d43c", "ip": "447558"}
        with patch.dict(os.environ, {BUILDER.EXPERIMENT_CLIMAX_TALKAT_AGE_ENV: "1"}, clear=False):
            talkat_limit = BUILDER._dialogue_anchor_age_limit("CLIMAX.SCN", non_allowlisted, "timeline_talkat_anchor")
            talk_limit = BUILDER._dialogue_anchor_age_limit("CLIMAX.SCN", allowlisted, "timeline_talk_anchor")
        self.assertEqual(talkat_limit, BUILDER.TALK_ANCHOR_MAX_AGE)
        self.assertEqual(talk_limit, BUILDER.TALK_ANCHOR_MAX_AGE)


if __name__ == "__main__":
    unittest.main()
