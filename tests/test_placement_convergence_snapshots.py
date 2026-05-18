from __future__ import annotations

import importlib.util
import json
import os
import struct
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VM_LITE_PATH = REPO_ROOT / "runtime" / "tinsel1_vm_lite.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "placement_convergence_snapshots.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
POLY_RECORD_SIZE_T1 = 104


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
        cid, nxt = struct.unpack_from("<II", data, off)
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
    vals = struct.unpack_from("<8I", data, scene_payload)
    num_poly = vals[1]
    h_poly = vals[6]
    start = h_poly & 0x007FFFFF

    polys = []
    for i in range(num_poly):
        off = start + i * POLY_RECORD_SIZE_T1
        if off + POLY_RECORD_SIZE_T1 > len(data):
            break
        row = struct.unpack_from("<26i", data, off)
        polys.append({"index": i, "type": row[0], "x": list(row[1:5]), "y": list(row[5:9])})
    return polys


def _point_in_polygon(x: int, y: int, poly: dict) -> bool:
    xs = poly["x"]
    ys = poly["y"]
    inside = False
    j = len(xs) - 1
    for i in range(len(xs)):
        xi, yi = xs[i], ys[i]
        xj, yj = xs[j], ys[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def _block_candidates(block_poly: dict) -> list[dict]:
    xs = block_poly["x"]
    ys = block_poly["y"]
    cx = sum(xs) / 4.0
    cy = sum(ys) / 4.0
    out = []
    for corner, (x, y) in enumerate(zip(xs, ys)):
        out.append(
            {
                "corner": corner,
                "x": x + (4 if x >= cx else -4),
                "y": y + (4 if y >= cy else -4),
            }
        )
    return out


def _parse_play_xy(stack_top: list[str]) -> tuple[int, int] | None:
    film_index = -1
    for i in range(len(stack_top) - 1, -1, -1):
        token = str(stack_top[i])
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_index = i
            break
    if film_index < 0:
        return None

    values: list[int] = []
    for token in stack_top[film_index + 1 :]:
        token = str(token)
        if token.startswith("imm:"):
            try:
                values.append(int(token[4:]))
            except ValueError:
                continue
    if len(values) < 2:
        return None

    x, y = values[0], values[1]
    if x < 0 or y < 0:
        return None
    if x > 4096 or y > 4096:
        return None
    return x, y


def _resolve_case(x: int, y: int, block_polys: list[dict], non_block_polys: list[dict]) -> dict:
    inside_block = any(_point_in_polygon(x, y, p) for p in block_polys)

    candidates = []
    if inside_block:
        for block in block_polys:
            for cand in _block_candidates(block):
                cx, cy = cand["x"], cand["y"]
                if any(_point_in_polygon(cx, cy, p) for p in block_polys):
                    continue
                dist = abs(cx - x) + abs(cy - y)
                candidates.append((dist, cx, cy, block["index"], cand["corner"]))

    if candidates:
        candidates.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4]))
        dist, adj_x, adj_y, src_block, src_corner = candidates[0]
    else:
        dist, adj_x, adj_y, src_block, src_corner = 0, x, y, None, None

    selected_poly = None
    for poly in non_block_polys:
        if _point_in_polygon(adj_x, adj_y, poly):
            selected_poly = poly["index"]
            break

    return {
        "nominal_x": x,
        "nominal_y": y,
        "inside_block": inside_block,
        "candidate_count": len(candidates),
        "selected_polygon_index": selected_poly,
        "adjusted_x": adj_x,
        "adjusted_y": adj_y,
        "chosen_manhattan_distance": dist,
        "candidate_source_block_index": src_block,
        "candidate_corner": src_corner,
    }


def _scene_snapshot(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    polys = _parse_scene_polygons(data)
    block_polys = [p for p in polys if p["type"] == 2]
    non_block_polys = [p for p in polys if p["type"] != 2]

    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

    runtime_cases = []
    seen_coords = set()
    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=1200, max_paths=8)
        for event in trace["events"]:
            if event.get("event") != "libcall" or event.get("libcall_name") != "PLAY":
                continue
            xy = _parse_play_xy(event.get("stack_top") or [])
            if xy is None or xy in seen_coords:
                continue
            seen_coords.add(xy)
            case = {"event_ip": event.get("ip"), **_resolve_case(xy[0], xy[1], block_polys, non_block_polys)}
            runtime_cases.append(case)
            if len(runtime_cases) >= 12:
                break
        if len(runtime_cases) >= 12:
            break

    block_probe_case = None
    if block_polys:
        block = block_polys[0]
        cx = round(sum(block["x"]) / 4)
        cy = round(sum(block["y"]) / 4)
        block_probe_case = {
            "source_block_index": block["index"],
            "source": "block_centroid_probe",
            **_resolve_case(cx, cy, block_polys, non_block_polys),
        }

    return {
        "scene_has_block_polygons": len(block_polys) > 0,
        "block_polygon_count": len(block_polys),
        "runtime_case_count": len(runtime_cases),
        "runtime_cases": runtime_cases,
        "block_probe_case": block_probe_case,
    }


class PlacementConvergenceSnapshotTests(unittest.TestCase):
    def test_play_placement_convergence_snapshots_match_baseline(self):
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
            self.fail("Placement convergence snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
