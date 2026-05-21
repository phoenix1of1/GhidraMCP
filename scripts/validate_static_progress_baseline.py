from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out


def run_ghidra_script(base_url: str, program: str, script_path: Path) -> str:
    payload = {
        "script_name": script_path.name,
        "script_path": str(script_path),
        "program_name": program,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=base_url.rstrip("/") + "/run_ghidra_script",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    return str(parsed.get("console_output", ""))


def has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate static recovery baseline invariants.")
    parser.add_argument("--python", type=str, default=sys.executable)
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8089")
    parser.add_argument("--program", type=str, default="dwb_le_relocated_image.bin")
    parser.add_argument("--pipeline-base", type=Path, default=Path("outputs/full_playcomposite_pipeline"))
    args = parser.parse_args()

    cycle_rc, cycle_out = run_cmd(
        [
            args.python,
            "scripts/run_safe_waittime_cycle.py",
            "--python",
            args.python,
            "--base",
            str(args.pipeline_base),
        ],
        cwd=REPO_ROOT,
    )

    verdict_out = run_ghidra_script(
        args.base_url,
        args.program,
        REPO_ROOT / "ghidra_scripts" / "copilot_constraint_trust_verdict.py",
    )
    slice_out = run_ghidra_script(
        args.base_url,
        args.program,
        REPO_ROOT / "ghidra_scripts" / "copilot_slice_38a30_esi_ebx_origins.py",
    )
    dual_out = run_ghidra_script(
        args.base_url,
        args.program,
        REPO_ROOT / "ghidra_scripts" / "copilot_dual_recipe_intersection_38840_38910.py",
    )

    result: dict[str, Any] = {
        "safety_cycle": {
            "command_exit_code": cycle_rc,
            "no_safe_candidate": has(cycle_out, r'"status"\s*:\s*"no_safe_candidate"'),
            "diagnostics_skipped": has(cycle_out, r'"action"\s*:\s*"diagnostics_skipped"'),
        },
        "trust_verdict": {
            "update_consumer_trusted": has(verdict_out, r"update_consumer => TRUSTED"),
            "case_stub_trusted": has(verdict_out, r"case_stub => TRUSTED"),
            "dispatcher_unstable": has(verdict_out, r"dispatcher_jump => UNSTABLE"),
            "lane_38a32_unstable": has(verdict_out, r"38a32_wait_lane => UNSTABLE"),
            "case_fp_a44650c2": has(verdict_out, r"SIG_FP_PASS1\s+a44650c2"),
            "dispatcher_fp_a79ab56c": has(verdict_out, r"SIG_FP_PASS1\s+a79ab56c"),
        },
        "provenance_invariants": {
            "slice_cross_pass_stable": has(slice_out, r"CROSS_PASS_STABLE\s+True"),
            "slice_fp_6cfdb45e": has(slice_out, r"SIG_FP\s+6cfdb45e"),
            "slice_no_esi_defs": has(slice_out, r"ESI_DEFS\s+0"),
            "slice_no_ebx_defs": has(slice_out, r"EBX_DEFS\s+0"),
            "dual_both_stable": has(dual_out, r"BOTH_STABLE\s+True"),
            "dual_intersection_esi_edi_zero": has(
                dual_out,
                r"INTERSECTION_COUNTS\s+INS\s+44\s+EDGES\s+11\s+ESI\s+0\s+EDI\s+0",
            ),
        },
    }

    checks = []
    for section in result.values():
        if isinstance(section, dict):
            for k, v in section.items():
                if isinstance(v, bool):
                    checks.append(v)
    result["all_checks_pass"] = all(checks)

    print(json.dumps(result, indent=2))
    return 0 if result["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
