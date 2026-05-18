#!/usr/bin/env python3
"""Emit deterministic scene decomp artifacts for review workflows."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path


def _load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_output(repo_root: Path) -> Path:
    return repo_root / "outputs" / "decomp" / "latest_scene_bundles"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    refresh_mod = _load_module(
        "refresh_snapshot_baselines_module",
        repo_root / "scripts" / "refresh_snapshot_baselines.py",
    )

    parser = argparse.ArgumentParser(description="Emit scene decomp bundle artifacts")
    parser.add_argument("--input", help="Dataset path containing INDEX and SCN files")
    parser.add_argument(
        "--output",
        help="Output directory for emitted pseudo bundles (default: outputs/decomp/latest_scene_bundles)",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete output directory before emission",
    )
    args = parser.parse_args()

    try:
        dataset_dir = refresh_mod._resolve_dataset_dir(repo_root, args.input)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output).resolve() if args.output else _default_output(repo_root)
    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    vm_mod = refresh_mod._load_module(
        "tinsel1_vm_lite_module_emit",
        repo_root / "runtime" / "tinsel1_vm_lite.py",
    )
    scanner_mod = refresh_mod._load_module(
        "tinsel1_pcode_scanner_module_emit",
        repo_root / "runtime" / "tinsel1_pcode_scanner.py",
    )

    bundle_payload = refresh_mod._build_pcode_scene_decomp_bundle_snapshots(vm_mod, scanner_mod, dataset_dir)
    delivery_payload = refresh_mod._build_pcode_decomp_delivery_manifest_snapshots(bundle_payload)

    scene_manifest = {}
    for scene_name in refresh_mod.DELIVER_CONTRACT_SCENES:
        scene_bundle = bundle_payload.get(scene_name, {})
        scene_delivery = delivery_payload.get(scene_name, {})
        text_lines = refresh_mod._render_bundle_text(scene_name, scene_bundle)

        artifact_file = scene_delivery.get("artifact_file") or f"{scene_name.split('.', 1)[0].lower()}_decomp.pseudo"
        artifact_path = output_dir / artifact_file
        artifact_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")

        scene_manifest[scene_name] = {
            "artifact_file": artifact_file,
            "line_count": len(text_lines),
            "artifact_full_sha256": scene_delivery.get("artifact_full_sha256", ""),
            "bundle_text_digest": scene_delivery.get("bundle_text_digest", ""),
            "function_count": int(scene_delivery.get("function_count") or 0),
        }

    manifest = {
        "scope": "deterministic scene decomp artifacts",
        "dataset": str(dataset_dir),
        "output": str(output_dir),
        "scenes": scene_manifest,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("Emitted scene decomp artifacts")
    print("Dataset:", dataset_dir)
    print("Output:", output_dir)
    print("Scenes:", ", ".join(refresh_mod.DELIVER_CONTRACT_SCENES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
