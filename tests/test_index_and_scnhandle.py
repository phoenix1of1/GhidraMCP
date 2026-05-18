from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_PATH = REPO_ROOT / "extractor" / "discworld_extract.py"


def _load_extractor_module():
    spec = importlib.util.spec_from_file_location("discworld_extract_module", EXTRACTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load extractor module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXTRACTOR = _load_extractor_module()


def _resolve_dataset_dir() -> Path:
    env_input = os.environ.get("DISCWORLD_TEST_INPUT")
    if env_input:
        candidate = Path(env_input).resolve()
        if (candidate / "INDEX").exists():
            return candidate

    candidates = [
        REPO_ROOT.parent / "clean-game" / "DISCWLD",
        REPO_ROOT.parent / "clean-game",
        REPO_ROOT / "sample_data",
    ]

    for candidate in candidates:
        if (candidate / "INDEX").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate test dataset with INDEX file. "
        "Tried: " + ", ".join(str(p) for p in candidates)
    )


class ScnHandleTests(unittest.TestCase):
    def test_decode_known_example(self):
        handle = (7 << 23) | 0x00123456
        decoded = EXTRACTOR.decode_scnhandle(handle)
        self.assertEqual(decoded["file_index"], 7)
        self.assertEqual(decoded["local_offset"], 0x00123456)

    def test_roundtrip_boundaries(self):
        pairs = [
            (0, 0),
            (1, 1),
            (149, 0x00100000),
            (0x1FF, 0x007FFFFF),
        ]
        for file_index, local_offset in pairs:
            handle = EXTRACTOR.encode_scnhandle(file_index, local_offset)
            decoded = EXTRACTOR.decode_scnhandle(handle)
            self.assertEqual(decoded["file_index"], file_index)
            self.assertEqual(decoded["local_offset"], local_offset)

    def test_encode_rejects_out_of_range_values(self):
        with self.assertRaises(ValueError):
            EXTRACTOR.encode_scnhandle(-1, 0)
        with self.assertRaises(ValueError):
            EXTRACTOR.encode_scnhandle(0x200, 0)
        with self.assertRaises(ValueError):
            EXTRACTOR.encode_scnhandle(0, -1)
        with self.assertRaises(ValueError):
            EXTRACTOR.encode_scnhandle(0, 0x00800000)


class IndexParserTests(unittest.TestCase):
    def test_index_parses_expected_record_count(self):
        dataset = _resolve_dataset_dir()
        rows = EXTRACTOR.read_index(dataset / "INDEX")
        self.assertEqual(len(rows), 149)

    def test_index_contains_core_scenes(self):
        dataset = _resolve_dataset_dir()
        rows = EXTRACTOR.read_index(dataset / "INDEX")
        filenames = {row["filename"].upper() for row in rows}

        required = {
            "BAR.SCN",
            "LIBRARY.SCN",
            "OBJECTS.SCN",
            "DW.SCN",
            "CLIMAX.SCN",
        }
        missing = sorted(required - filenames)
        self.assertEqual(missing, [])

    def test_index_row_shape_is_stable(self):
        dataset = _resolve_dataset_dir()
        rows = EXTRACTOR.read_index(dataset / "INDEX")

        self.assertTrue(rows, "INDEX should produce at least one row")
        for row in rows:
            self.assertIn("index", row)
            self.assertIn("filename", row)
            self.assertIn("size_flags", row)
            self.assertIn("record_offset", row)
            self.assertRegex(row["size_flags"], r"^0x[0-9A-F]{8}$")
            self.assertEqual(row["record_offset"] % 20, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
