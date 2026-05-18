#!/usr/bin/env python3
"""One-command entrypoint for the Discworld extractor workflow.

Defaults are chosen for this workspace layout:
- repo root: discworld_full_repo_package
- game data: ../clean-game/DISCWLD (or ../clean-game)
- output: outputs/latest_run
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _resolve_default_input(repo_root: Path) -> Path:
    workspace_root = repo_root.parent
    candidates = [
        workspace_root / "clean-game" / "DISCWLD",
        workspace_root / "clean-game",
        repo_root / "sample_data",
    ]

    for candidate in candidates:
        if (candidate / "INDEX").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate default input with INDEX file. "
        "Tried: " + ", ".join(str(p) for p in candidates)
    )


def _default_output(repo_root: Path) -> Path:
    return repo_root / "outputs" / "latest_run"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    extractor = repo_root / "extractor" / "discworld_extract.py"

    parser = argparse.ArgumentParser(
        description="Convenience runner for extractor/discworld_extract.py"
    )
    parser.add_argument(
        "--input",
        help="Path containing INDEX and SCN files. Default auto-detects clean-game.",
    )
    parser.add_argument(
        "--output",
        help="Output directory. Default: outputs/latest_run",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete output directory before running.",
    )
    parser.add_argument(
        "--mode",
        default="all",
        choices=[
            "chunks",
            "images",
            "scenegraph",
            "pcode",
            "films",
            "visual",
            "vm",
            "scheduler",
            "timelines",
            "all",
        ],
        help="Extraction mode to run.",
    )
    parser.add_argument(
        "--scenes",
        nargs="*",
        default=["BAR.SCN", "CLIMAX.SCN", "FINALE.SCN"],
        help="Scene names passed through to extractor modes that need scenes.",
    )
    parser.add_argument("--image-limit", type=int, default=20)
    parser.add_argument("--max-images-per-scene", type=int, default=50)
    parser.add_argument("--max-scripts-per-file", type=int, default=60)
    parser.add_argument("--max-steps", type=int, default=1200)
    parser.add_argument("--max-paths", type=int, default=32)
    parser.add_argument("--zip", action="store_true")

    args = parser.parse_args()

    try:
        input_dir = Path(args.input).resolve() if args.input else _resolve_default_input(repo_root)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output).resolve() if args.output else _default_output(repo_root)

    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)

    cmd = [
        sys.executable,
        str(extractor),
        "--input",
        str(input_dir),
        "--output",
        str(output_dir),
        "--mode",
        args.mode,
        "--image-limit",
        str(args.image_limit),
        "--max-images-per-scene",
        str(args.max_images_per_scene),
        "--max-scripts-per-file",
        str(args.max_scripts_per_file),
        "--max-steps",
        str(args.max_steps),
        "--max-paths",
        str(args.max_paths),
    ]

    if args.scenes:
        cmd.append("--scenes")
        cmd.extend(args.scenes)

    if args.zip:
        cmd.append("--zip")

    print("Running:", " ".join(cmd))
    print("Input:", input_dir)
    print("Output:", output_dir)

    result = subprocess.run(cmd, cwd=str(repo_root))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
