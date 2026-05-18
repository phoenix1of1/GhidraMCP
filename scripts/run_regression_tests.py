#!/usr/bin/env python3
"""One-command regression test runner for deterministic extractor checks."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _resolve_dataset_dir(repo_root: Path, explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).resolve()
        if (candidate / "INDEX").exists():
            return candidate
        raise FileNotFoundError(f"Provided --input has no INDEX file: {candidate}")

    candidates = [
        repo_root.parent / "clean-game" / "DISCWLD",
        repo_root.parent / "clean-game",
        repo_root / "sample_data",
    ]

    for candidate in candidates:
        if (candidate / "INDEX").exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate default test input with INDEX file. "
        "Tried: " + ", ".join(str(p) for p in candidates)
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    tests_dir = repo_root / "tests"

    parser = argparse.ArgumentParser(description="Run deterministic regression tests")
    parser.add_argument(
        "--input",
        help="Dataset path containing INDEX and SCN files. Optional auto-detect if omitted.",
    )
    args = parser.parse_args()

    try:
        dataset_dir = _resolve_dataset_dir(repo_root, args.input)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Running regression tests")
    print("Dataset:", dataset_dir)

    cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(tests_dir), "-p", "test_*.py", "-v"]
    env = dict(os.environ)
    env["DISCWORLD_TEST_INPUT"] = str(dataset_dir)
    result = subprocess.run(cmd, cwd=str(repo_root), env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
