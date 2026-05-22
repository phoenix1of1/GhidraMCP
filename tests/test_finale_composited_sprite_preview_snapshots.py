from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TIMELINE_CSV = REPO_ROOT.parent / "discworld_all_generated_csvs" / "finale_scene_space_playback_timeline_full.csv"
CHAR_PACK_MANIFEST = REPO_ROOT / "finale_character_asset_pack" / "manifest.json"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "finale_composited_sprite_preview_snapshots.json"


class FinaleCompositedSpritePreviewSnapshotsTest(unittest.TestCase):
    def test_finale_preview_snapshot_contract(self):
        if not TIMELINE_CSV.exists():
            self.skipTest(f"Timeline CSV not available: {TIMELINE_CSV}")
        if not CHAR_PACK_MANIFEST.exists():
            self.skipTest(f"Character pack manifest not available: {CHAR_PACK_MANIFEST}")

        import csv

        with TIMELINE_CSV.open("r", encoding="utf-8", newline="") as f:
            timeline = list(csv.DictReader(f))

        play_events = [row for row in timeline if row.get("libcall") == "PLAY"]
        source_counts: dict[str, int] = {}
        for row in play_events:
            source = str(row.get("position_source") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

        pack_manifest = json.loads(CHAR_PACK_MANIFEST.read_text(encoding="utf-8"))
        film_to_pack = {p["film_handle"]: p for p in pack_manifest.get("packs", [])}

        rendered = 0
        missing = 0
        for row in play_events:
            film = row.get("film") or ""
            pack = film_to_pack.get(film)
            if not pack:
                missing += 1
                continue
            frame_dir = REPO_ROOT / "finale_character_asset_pack" / pack["asset_id"] / "frames"
            frame_files = list(frame_dir.glob("*.png")) if frame_dir.exists() else []
            if frame_files:
                rendered += 1
            else:
                missing += 1

        actual = {
            "FINALE.SCN": {
                "events_composited": len(play_events),
                "character_assets_available": True,
                "rendered_sprite_count": rendered,
                "missing_asset_count": missing,
                "position_source_counts": dict(sorted(source_counts.items())),
                "output_preview": "finale_composited_sprite_preview.png",
            }
        }

        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
