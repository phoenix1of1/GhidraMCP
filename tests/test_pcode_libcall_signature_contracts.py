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
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "pcode_libcall_signature_contracts.json"
SCENE_SET = ["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"]
MAX_STEPS = 1200
MAX_PATHS = 16
MAX_CALLS = 30
ARG_SHAPE_WINDOW = 6


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


def _path_depth(path_name: str | None) -> int:
    if not path_name:
        return 0
    return str(path_name).count(".br")


def _stack_token_kind(token: str) -> str:
    token = str(token or "")
    if token.startswith("imm:"):
        return "imm"
    if token.startswith("global:"):
        return "global"
    if token.startswith("local:"):
        return "local"
    if token.startswith("film:"):
        return "film"
    if token.startswith("cdfilm:"):
        return "cdfilm"
    if token.startswith("underflow"):
        return "underflow"
    return "expr"


def _arg_shape(stack_top: list, window: int = ARG_SHAPE_WINDOW) -> str:
    if not stack_top:
        return "empty"
    suffix = stack_top[-window:]
    return ">".join(_stack_token_kind(token) for token in suffix)


def _scene_snapshot(dataset_dir: Path, scene_name: str, idx_by_name: dict) -> dict:
    scene_path = dataset_dir / scene_name
    data = scene_path.read_bytes()
    scripts = VM.collect_script_handles(scene_path, idx_by_name)
    scripts = sorted(scripts, key=lambda s: (s.get("source", ""), s.get("handle", 0)))[:60]

    signatures: dict[str, dict] = {}
    predecessor_hist = collections.Counter()
    libcall_sequence: list[str] = []

    scripts_with_libcalls = 0
    max_path_depth_at_libcall = 0
    max_paths_started_for_libcall_scripts = 0

    for script in scripts:
        handle = script["handle"]
        file_index, offset = VM.split_handle(handle)
        if file_index != idx_by_name.get(scene_name.lower(), -1) or offset >= len(data):
            continue

        trace = VM.execute_script(data, offset, max_steps=MAX_STEPS, max_paths=MAX_PATHS)
        local_sequence: list[str] = []

        for event in trace.get("events", []):
            if event.get("event") != "libcall":
                continue

            name = event.get("libcall_name")
            if not name:
                continue

            local_sequence.append(name)
            libcall_sequence.append(name)
            max_path_depth_at_libcall = max(max_path_depth_at_libcall, _path_depth(event.get("path")))

            signature = signatures.setdefault(
                name,
                {
                    "occurrence_count": 0,
                    "stack_depth_min": None,
                    "stack_depth_max": 0,
                    "observed_arg_count_histogram": collections.Counter(),
                    "arg_shape_histogram": collections.Counter(),
                },
            )

            signature["occurrence_count"] += 1
            depth = int(event.get("stack_depth") or 0)
            signature["stack_depth_min"] = (
                depth if signature["stack_depth_min"] is None else min(signature["stack_depth_min"], depth)
            )
            signature["stack_depth_max"] = max(signature["stack_depth_max"], depth)

            stack_top = event.get("stack_top") or []
            arg_count_candidate = len(stack_top)
            signature["observed_arg_count_histogram"][str(arg_count_candidate)] += 1
            signature["arg_shape_histogram"][_arg_shape(stack_top)] += 1

        if local_sequence:
            scripts_with_libcalls += 1
            max_paths_started_for_libcall_scripts = max(
                max_paths_started_for_libcall_scripts,
                int(trace.get("paths_started") or 1),
            )

        for i in range(1, len(local_sequence)):
            predecessor_hist[f"{local_sequence[i - 1]}->{local_sequence[i]}"] += 1

    ranked_calls = sorted(
        signatures.keys(),
        key=lambda name: (-signatures[name]["occurrence_count"], name),
    )[:MAX_CALLS]

    libcall_contracts = {}
    for name in ranked_calls:
        signature = signatures[name]
        top_shapes = [shape for shape, _ in signature["arg_shape_histogram"].most_common(6)]
        libcall_contracts[name] = {
            "occurrence_count": signature["occurrence_count"],
            "stack_depth_min": 0 if signature["stack_depth_min"] is None else signature["stack_depth_min"],
            "stack_depth_max": signature["stack_depth_max"],
            "observed_arg_count_histogram": {
                key: signature["observed_arg_count_histogram"][key]
                for key in sorted(signature["observed_arg_count_histogram"].keys(), key=int)
            },
            "top_arg_shapes": top_shapes,
            "top_arg_shapes_sha256": hashlib.sha256("|".join(top_shapes).encode("utf-8")).hexdigest(),
        }

    sequence_head = libcall_sequence[:30]
    return {
        "scripts_traced": len(scripts),
        "scripts_with_libcalls": scripts_with_libcalls,
        "libcall_event_count": len(libcall_sequence),
        "unique_libcall_count": len(signatures),
        "max_path_depth_at_libcall": max_path_depth_at_libcall,
        "max_paths_started_for_libcall_scripts": max_paths_started_for_libcall_scripts,
        "libcalls_ranked": ranked_calls,
        "libcall_signatures": {name: libcall_contracts[name] for name in sorted(libcall_contracts.keys())},
        "libcall_predecessor_transition_histogram": dict(sorted(predecessor_hist.items())),
        "libcall_sequence_head": sequence_head,
        "libcall_sequence_head_sha256": hashlib.sha256("|".join(sequence_head).encode("utf-8")).hexdigest(),
    }


class PcodeLibcallSignatureContractTests(unittest.TestCase):
    def test_pcode_libcall_signature_contract_snapshots_match_baseline(self):
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
            self.fail("Pcode libcall signature contract snapshot mismatch:\n" + json.dumps(mismatches, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
