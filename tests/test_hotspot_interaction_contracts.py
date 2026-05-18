from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VM_LITE_PATH = REPO_ROOT / "runtime" / "tinsel1_vm_lite.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "hotspot_interaction_contracts.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
POLY_RECORD_SIZE_T1 = 104
HOTSPOT_POLY_TYPES = {5: "EXIT", 6: "TAG"}
HOTSPOT_LIBCALLS = {
    "CONVERSATION",
    "CONVTOPIC",
    "TALK",
    "TALKAT",
    "PRINTOBJ",
    "PRINTTAG",
    "SHOWSTRING",
    "SETTAG",
    "KILLTAG",
    "TAGACTOR",
    "UNTAGACTOR",
}
HOTSPOT_DISPATCH_TARGETS = {
    "TALK",
    "TALKAT",
    "PLAY",
    "INVENTORY",
    "ININVENTORY",
    "INWHICHINV",
    "WHICHINVENTORY",
}
MAX_STEPS = 1200
MAX_PATHS = 16


def _load_vm_lite_module():
    spec = importlib.util.spec_from_file_location("tinsel1_vm_lite_module", VM_LITE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load vm-lite module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VM = _load_vm_lite_module()


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


def _read_chunks(data: bytes) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    off = 0
    while off < len(data):
        if off + 8 > len(data):
            break
        cid = int.from_bytes(data[off:off + 4], "little")
        nxt = int.from_bytes(data[off + 4:off + 8], "little")
        end = nxt if nxt else len(data)
        out[cid] = (off + 8, end)
        if nxt == 0:
            break
        off = nxt
    return out


def _parse_scene_polygons(data: bytes) -> list[dict]:
    chunks = _read_chunks(data)
    if 0x3334000E not in chunks or 0x3334000C not in chunks:
        return []
    scene_payload, _ = chunks[0x3334000E]
    vals = [int.from_bytes(data[scene_payload + i * 4:scene_payload + i * 4 + 4], "little") for i in range(8)]
    num_poly = vals[1]
    h_poly = vals[6]
    start = h_poly & 0x007FFFFF

    polys = []
    for i in range(num_poly):
        off = start + i * POLY_RECORD_SIZE_T1
        if off + POLY_RECORD_SIZE_T1 > len(data):
            break
        row = [int.from_bytes(data[off + j * 4:off + j * 4 + 4], "little", signed=True) for j in range(26)]
        polys.append(
            {
                "index": i,
                "type": row[0],
                "x": list(row[1:5]),
                "y": list(row[5:9]),
                "h_tagtext": row[11],
                "id": row[16],
            }
        )
    return polys


def _path_depth(path_name: str | None) -> int:
    if not path_name:
        return 0
    return str(path_name).count(".br")


def _scene_snapshot(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

    polys = _parse_scene_polygons(data)
    hotspot_polys = [p for p in polys if p.get("type") in HOTSPOT_POLY_TYPES]
    hotspot_polygon_histogram = collections.Counter(HOTSPOT_POLY_TYPES[p["type"]] for p in hotspot_polys)
    hotspot_with_tagtext_count = sum(1 for p in hotspot_polys if int(p.get("h_tagtext") or 0) != 0)
    hotspot_with_id_count = sum(1 for p in hotspot_polys if int(p.get("id") or 0) != 0)

    all_hotspot_x = [x for p in hotspot_polys for x in p.get("x", [])]
    all_hotspot_y = [y for p in hotspot_polys for y in p.get("y", [])]
    hotspot_bounds = {
        "min_x": min(all_hotspot_x) if all_hotspot_x else None,
        "max_x": max(all_hotspot_x) if all_hotspot_x else None,
        "min_y": min(all_hotspot_y) if all_hotspot_y else None,
        "max_y": max(all_hotspot_y) if all_hotspot_y else None,
    }

    hotspot_sequence: list[str] = []
    all_libcall_sequence: list[str] = []
    hotspot_sources = collections.Counter()
    hotspot_histogram = collections.Counter()
    stack_depth_min: int | None = None
    stack_depth_max = 0
    max_path_depth_at_hotspot_event = 0
    max_paths_started_for_hotspot_scripts = 0
    scripts_with_hotspot_events = 0

    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
        has_hotspot = False
        for event in trace.get("events", []):
            if event.get("event") != "libcall":
                continue

            name = event.get("libcall_name")
            if not name:
                continue
            all_libcall_sequence.append(name)

            if name not in HOTSPOT_LIBCALLS:
                continue

            has_hotspot = True
            hotspot_sequence.append(name)
            hotspot_histogram[name] += 1
            hotspot_sources[script.get("source", "unknown")] += 1

            depth = int(event.get("stack_depth") or 0)
            stack_depth_min = depth if stack_depth_min is None else min(stack_depth_min, depth)
            stack_depth_max = max(stack_depth_max, depth)
            max_path_depth_at_hotspot_event = max(max_path_depth_at_hotspot_event, _path_depth(event.get("path")))

        if has_hotspot:
            scripts_with_hotspot_events += 1
            max_paths_started_for_hotspot_scripts = max(
                max_paths_started_for_hotspot_scripts,
                int(trace.get("paths_started") or 1),
            )

    hotspot_transitions = collections.Counter()
    for i in range(len(hotspot_sequence) - 1):
        hotspot_transitions[f"{hotspot_sequence[i]}->{hotspot_sequence[i + 1]}"] += 1

    hotspot_to_dispatch_transitions = collections.Counter()
    for i in range(len(all_libcall_sequence) - 1):
        left = all_libcall_sequence[i]
        right = all_libcall_sequence[i + 1]
        if left in HOTSPOT_LIBCALLS and right in HOTSPOT_DISPATCH_TARGETS:
            hotspot_to_dispatch_transitions[f"{left}->{right}"] += 1

    sequence_head = hotspot_sequence[:30]
    return {
        "scripts_traced": len(scripts),
        "scripts_with_hotspot_events": scripts_with_hotspot_events,
        "hotspot_event_count": len(hotspot_sequence),
        "hotspot_polygon_count": len(hotspot_polys),
        "hotspot_polygon_histogram": dict(sorted(hotspot_polygon_histogram.items())),
        "hotspot_with_tagtext_count": hotspot_with_tagtext_count,
        "hotspot_with_id_count": hotspot_with_id_count,
        "hotspot_bounds": hotspot_bounds,
        "hotspot_libcall_histogram": dict(sorted(hotspot_histogram.items())),
        "hotspot_source_histogram": dict(sorted(hotspot_sources.items())),
        "hotspot_transition_histogram": dict(sorted(hotspot_transitions.items())),
        "hotspot_to_dispatch_transition_histogram": dict(sorted(hotspot_to_dispatch_transitions.items())),
        "stack_depth_min": 0 if stack_depth_min is None else stack_depth_min,
        "stack_depth_max": stack_depth_max,
        "max_path_depth_at_hotspot_event": max_path_depth_at_hotspot_event,
        "max_paths_started_for_hotspot_scripts": max_paths_started_for_hotspot_scripts,
        "hotspot_sequence_head": sequence_head,
        "hotspot_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class HotspotInteractionContractTests(unittest.TestCase):
    def test_hotspot_interaction_contract_snapshots_match_baseline(self):
        dataset = _resolve_dataset_dir()
        idx_rows = VM.read_index(dataset / "INDEX")
        idx_by_name = {row["filename"].lower(): row["index"] for row in idx_rows}
        expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        mismatches = {}
        for scene_name in SCENE_SET:
            scene_path = dataset / scene_name
            self.assertTrue(scene_path.exists(), f"Missing scene file: {scene_name}")
            actual = _scene_snapshot(dataset, scene_name, idx_by_name)
            expected_scene = expected.get(scene_name)
            if expected_scene is None:
                mismatches[scene_name] = {"error": "missing expected scene snapshot", "actual": actual}
                continue
            if actual != expected_scene:
                mismatches[scene_name] = {"expected": expected_scene, "actual": actual}

        if mismatches:
            self.fail("Hotspot interaction contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
