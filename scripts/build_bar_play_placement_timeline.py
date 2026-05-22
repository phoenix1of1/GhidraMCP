#!/usr/bin/env python3
"""Build a fuller BAR.SCN placement timeline from vm-lite film events.

This produces a deterministic timeline CSV compatible with the BAR composited
preview pipeline. Coordinate recovery is seeded from placement convergence
snapshots when available; remaining events use a stable fallback layout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERATED_CSV_DIR = REPO_ROOT.parent / "discworld_all_generated_csvs"
DEFAULT_VM_LITE_CSV = DEFAULT_GENERATED_CSV_DIR / "vm_lite_film_events.csv"
DEFAULT_OUTPUT_CSV = DEFAULT_GENERATED_CSV_DIR / "bar_scene_space_playback_timeline_full.csv"
DEFAULT_SCENE = "BAR.SCN"
DEFAULT_TIMELINE_DIR = REPO_ROOT / "outputs" / "bar_pipeline" / "scene_timeline"
PLACEMENT_SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "placement_convergence_snapshots.json"
SCENE_ROOT = REPO_ROOT.parent / "clean-game" / "DISCWLD"
POLY_RECORD_SIZE_T1 = 104
TALKAT_ANCHOR_MAX_AGE = 12
TALK_ANCHOR_MAX_AGE = 12
SCROLL_PREFIX_MAX_AGE = 10
CUTBARN_SCROLL_PREFIX_SCENE = "CUTBARN.SCN"
CUTBARN_SCROLL_PREFIX_SCRIPT = "0X23847917"
FILM_REPLAY_MAX_AGE = 6
CUTBARN_NEIGHBOR_CARRY_IP = 293569
CUTBARN_NEIGHBOR_CARRY_MAX_BACK = 2
WAITTIME_FAMILY_NEIGHBOR_CARRY_KEYS = {
    ("INTROSHA.SCN", "0X290373CE", 226342),
    ("INTROSHA.SCN", "0X290373CE", 226473),
    ("OVEREDGE.SCN", "0X20009D63", 40609),
}
WAITTIME_FAMILY_NEIGHBOR_CARRY_MAX_BACK = 2
TALK_FAMILY_NEIGHBOR_CARRY_KEYS = {
    ("ARCH.SCN", "0X1E01FEA4", 130734),
    ("INTROSHA.SCN", "0X290373CE", 226364),
    ("INTROSHA.SCN", "0X290373CE", 226456),
}
TALK_FAMILY_NEIGHBOR_CARRY_MAX_BACK = 2
OVEREDGE_CLUSTER_CARRY_KEYS = {
    ("OVEREDGE.SCN", "0X20009D63", 40322),
    ("OVEREDGE.SCN", "0X20009D63", 40339),
    ("OVEREDGE.SCN", "0X20009D63", 40573),
}
OVEREDGE_CLUSTER_CARRY_MAX_DISTANCE = 2
SINGLETON_BOOTSTRAP_CARRY_KEYS = {
    ("CUTBARN.SCN", "0X23847917", 293157),
    ("INTROSHA.SCN", "0X290373CE", 226278),
    ("SQUARE2.SCN", "0X178584AC", 361663),
    ("SQUARE2.SCN", "0X178584AC", 361675),
    ("SQUARE3.SCN", "0X180517A8", 333755),
    ("SQUARE3.SCN", "0X180517A8", 333767),
}
SINGLETON_BOOTSTRAP_CARRY_MAX_AHEAD = 3
KNOWN_NON_TINY_PREFIX_IPS = {
    ("INTROSHA.SCN", "0X290373CE", 226315),
    ("OVEREDGE.SCN", "0X20009EAF", 40639),
}
NON_TINY_PREFIX_MIN = 32
SCROLL_PREFIX_SENTINELS = {
    (0, 0),
    (0, 1),
    (1, 0),
    (6, 1),
    (320, 0),
    (640, 0),
}

PLACEMENT_SOURCE_CONFIDENCE = {
    "background": "high",
    "placement_snapshot": "high",
    "timeline_args": "high",
    "trace_stack_top": "medium",
    "timeline_actor_state": "high",
    "timeline_motion": "medium",
    "timeline_offset": "medium",
    "timeline_talkat_anchor": "high",
    "timeline_talk_anchor": "high",
    "timeline_scroll_prefix": "high",
    "timeline_waitframe_prefix": "high",
    "timeline_prefix_known_non_tiny": "high",
    "timeline_film_replay": "high",
    "timeline_neighbor_carry": "high",
    "timeline_waittime_family_carry": "high",
    "timeline_talk_family_carry": "high",
    "timeline_overedge_cluster_carry": "high",
    "timeline_bootstrap_carry": "high",
    "fallback_visual_validation": "low",
    "block_centroid_probe": "low",
}


def _placement_confidence_for_source(source: str) -> str:
    return PLACEMENT_SOURCE_CONFIDENCE.get(source, "unknown")


def _parse_hex_handle(text: str) -> str:
    token = text.strip()
    if token.lower().startswith("0x"):
        return token
    return ""


def _extract_film_handle(row: dict[str, str]) -> str:
    args = (row.get("film_args") or "").strip()
    if not args:
        return ""
    parts = [p.strip() for p in args.split("|") if p.strip()]
    if not parts:
        return ""
    for part in reversed(parts):
        handle = _parse_hex_handle(part)
        if handle:
            return handle
    return ""


def _load_runtime_nominals(scene_name: str) -> dict[int, tuple[int, int]]:
    if not PLACEMENT_SNAPSHOT_PATH.exists():
        return {}
    payload = json.loads(PLACEMENT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    bar = payload.get(scene_name) or {}
    out: dict[int, tuple[int, int]] = {}
    for case in bar.get("runtime_cases", []):
        event_ip = case.get("event_ip")
        x = case.get("nominal_x")
        y = case.get("nominal_y")
        if isinstance(event_ip, int) and isinstance(x, int) and isinstance(y, int) and x >= 0 and y >= 0:
            out[event_ip] = (x, y)
    return out


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


def _load_block_polygons(scene_path: Path) -> list[dict[str, object]]:
    if not scene_path.exists():
        return []
    data = scene_path.read_bytes()
    chunks = _read_chunks(data)
    if 0x3334000E not in chunks:
        return []
    scene_payload, _ = chunks[0x3334000E]
    vals = struct.unpack_from("<8I", data, scene_payload)
    num_poly = vals[1]
    h_poly = vals[6]
    start = h_poly & 0x007FFFFF
    polys: list[dict[str, object]] = []
    for i in range(num_poly):
        off = start + i * POLY_RECORD_SIZE_T1
        if off + POLY_RECORD_SIZE_T1 > len(data):
            break
        row = struct.unpack_from("<26i", data, off)
        if row[0] != 2:
            continue
        polys.append({"index": i, "x": list(row[1:5]), "y": list(row[5:9])})
    return polys


def _point_in_polygon(px: int, py: int, poly: dict[str, object]) -> bool:
    xs = poly["x"]
    ys = poly["y"]
    inside = False
    j = len(xs) - 1
    for i in range(len(xs)):
        xi, yi = xs[i], ys[i]
        xj, yj = xs[j], ys[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _block_candidates(block_poly: dict[str, object]) -> list[tuple[int, int]]:
    xs = block_poly["x"]
    ys = block_poly["y"]
    cx = sum(xs) / 4.0
    cy = sum(ys) / 4.0
    out: list[tuple[int, int]] = []
    for x, y in zip(xs, ys):
        out.append((x + (4 if x >= cx else -4), y + (4 if y >= cy else -4)))
    return out


def _apply_block_snap(x: int, y: int, block_polys: list[dict[str, object]]) -> tuple[int, int, bool]:
    if not block_polys:
        return x, y, False
    if not any(_point_in_polygon(x, y, p) for p in block_polys):
        return x, y, False

    candidates: list[tuple[int, int, int]] = []
    for poly in block_polys:
        for cx, cy in _block_candidates(poly):
            if any(_point_in_polygon(cx, cy, p) for p in block_polys):
                continue
            dist = abs(cx - x) + abs(cy - y)
            candidates.append((dist, cx, cy))
    if not candidates:
        return x, y, False
    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
    _, nx, ny = candidates[0]
    return nx, ny, True


def _extract_xy_from_stack_top(stack_top: str) -> tuple[int, int] | None:
    if not stack_top:
        return None
    tokens = [t.strip() for t in stack_top.split("|") if t.strip()]
    film_index = -1
    for i, token in enumerate(tokens):
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_index = i
    if film_index < 0:
        return None
    values: list[int] = []
    for token in tokens[film_index + 1 :]:
        if token.startswith("imm:"):
            try:
                values.append(int(token[4:]))
            except ValueError:
                continue
    if len(values) < 2:
        return None
    return values[0], values[1]


def _extract_imm_arg(args_display: str, name: str) -> int | None:
    m = re.search(rf"{re.escape(name)}=imm:([-0-9]+)", args_display or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_motion_xy(args_display: str, libcall: str) -> tuple[int, int] | None:
    x = _extract_imm_arg(args_display, "x")
    y = _extract_imm_arg(args_display, "y")
    if x is not None and y is not None and x >= 0 and y >= 0:
        return x, y

    libcall = libcall.upper()
    if libcall == "STAND":
        alt_x = _extract_imm_arg(args_display, "y")
        alt_y = _extract_imm_arg(args_display, "direction")
        if alt_x is not None and alt_y is not None and alt_x >= 0 and alt_y >= 0:
            return alt_x, alt_y

    if libcall in {"SWALK", "WALK"}:
        alt_x = _extract_imm_arg(args_display, "direction_or_x2")
        if alt_x is None:
            alt_x = _extract_imm_arg(args_display, "x2")
        alt_y = _extract_imm_arg(args_display, "y2")
        if alt_x is not None and alt_y is not None and alt_x >= 0 and alt_y >= 0:
            return alt_x, alt_y

    return None


def _extract_talkat_anchor(args_display: str) -> tuple[int, int] | None:
    anchor_x = _extract_imm_arg(args_display, "string_id")
    anchor_y = _extract_imm_arg(args_display, "x")
    maybe_string_id = _extract_imm_arg(args_display, "y")
    if anchor_x is None or anchor_y is None or maybe_string_id is None:
        return None
    if anchor_x < 0 or anchor_y < 0:
        return None
    if maybe_string_id < 1000:
        return None
    return anchor_x, anchor_y


def _extract_talk_anchor_from_visible_stack(stack_top: str) -> tuple[int, int] | None:
    if not stack_top:
        return None

    tokens = [token.strip() for token in stack_top.split("|") if token.strip()]
    if len(tokens) < 4:
        return None

    film_index = -1
    for index, token in enumerate(tokens):
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_index = index
    if film_index < 2 or film_index + 1 >= len(tokens):
        return None

    string_token = tokens[film_index + 1]
    if not string_token.startswith("imm:"):
        return None
    try:
        string_id = int(string_token[4:])
    except ValueError:
        return None
    if string_id < 1000:
        return None

    imm_values: list[int] = []
    for token in tokens[:film_index]:
        if not token.startswith("imm:"):
            continue
        try:
            imm_values.append(int(token[4:]))
        except ValueError:
            continue
    if len(imm_values) < 2:
        return None

    anchor_x, anchor_y = imm_values[-2], imm_values[-1]
    if anchor_x <= 0 or anchor_y < 0:
        return None
    if anchor_x > 640 or anchor_y > 400:
        return None
    return anchor_x, anchor_y


def _load_scheduler_talk_anchors(
    scheduler_csv: Path | None,
    scene_name: str,
) -> dict[int, tuple[int, int]]:
    if scheduler_csv is None or not scheduler_csv.exists():
        return {}

    anchors: dict[int, tuple[int, int]] = {}
    with scheduler_csv.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("file") or "").upper() != scene_name:
                continue
            if (row.get("libcall") or "").upper() != "TALK":
                continue
            try:
                ip = int(row.get("ip") or 0)
            except ValueError:
                continue
            anchor = _extract_talk_anchor_from_visible_stack(row.get("visible_stack") or "")
            if anchor is not None:
                anchors[ip] = anchor
    return anchors


def _load_scheduler_rows_by_script_ip(
    scheduler_csv: Path | None,
    scene_name: str,
) -> dict[tuple[str, int], dict[str, str]]:
    if scheduler_csv is None or not scheduler_csv.exists():
        return {}

    rows: dict[tuple[str, int], dict[str, str]] = {}
    with scheduler_csv.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("file") or "").upper() != scene_name:
                continue
            script_handle = (row.get("script_handle") or "").strip().upper()
            if not script_handle:
                continue
            try:
                ip = int(row.get("ip") or 0)
            except ValueError:
                continue
            rows[(script_handle, ip)] = row
    return rows


def _extract_scroll_prefix_anchor_from_visible_stack(stack_top: str) -> tuple[int, int] | None:
    if not stack_top:
        return None

    tokens = [token.strip() for token in stack_top.split("|") if token.strip()]
    if len(tokens) < 4:
        return None

    film_index = -1
    for index, token in enumerate(tokens):
        if token.startswith("film:") or token.startswith("cdfilm:"):
            film_index = index
            break
    if film_index < 2:
        return None

    values: list[int] = []
    for token in tokens[:film_index]:
        if not token.startswith("imm:"):
            continue
        try:
            values.append(int(token[4:]))
        except ValueError:
            continue
    if len(values) < 2:
        return None

    # Read prefix values as xy pairs in push order; keep the first plausible pair.
    for pair_index in range(0, len(values) - 1, 2):
        x, y = values[pair_index], values[pair_index + 1]
        if x < 0 or y < 0:
            continue
        if x > 640 or y > 400:
            continue
        if (x, y) in SCROLL_PREFIX_SENTINELS:
            continue
        return x, y
    return None


def _load_timeline_play_candidates(timeline_csv: Path | None) -> list[dict[str, object]]:
    if timeline_csv is None or not timeline_csv.exists():
        return []

    with timeline_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    candidates: list[dict[str, object]] = []
    current_offset = (0, 0)

    for row in rows:
        libcall = (row.get("libcall") or "").upper()
        args_display = row.get("args_display") or ""
        if libcall == "OFFSET":
            ox = _extract_imm_arg(args_display, "x")
            oy = _extract_imm_arg(args_display, "y")
            if ox is not None and oy is not None:
                current_offset = (ox, oy)
            continue

        if libcall != "PLAY":
            continue

        x = _extract_imm_arg(args_display, "x")
        y = _extract_imm_arg(args_display, "y")
        source = "none"
        use_xy: tuple[int, int] | None = None
        if x is not None and y is not None:
            if x >= 0 and y >= 0 and (x != 0 or y != 0):
                use_xy = (x, y)
                source = "timeline_args"
            elif x == 0 and y == 0 and current_offset != (0, 0):
                use_xy = current_offset
                source = "timeline_offset"

        candidates.append(
            {
                "film": row.get("film_args") or row.get("film"),
                "xy": use_xy,
                "source": source,
            }
        )
    return candidates


def _load_timeline_play_candidates_with_motion(
    timeline_csv: Path | None,
    scene_name: str,
    scheduler_talk_anchors: dict[int, tuple[int, int]] | None = None,
    scheduler_rows_by_script_ip: dict[tuple[str, int], dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    if timeline_csv is None or not timeline_csv.exists():
        return []

    with timeline_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    candidates: list[dict[str, object]] = []
    current_offset = (0, 0)
    current_motion: tuple[int, int] | None = None
    current_motion_idx = -999999
    current_dialogue_anchor: tuple[int, int] | None = None
    current_dialogue_idx = -999999
    current_dialogue_source = "none"
    last_scroll_idx = -999999
    # Actor-scoped state: actor_id -> (x, y, row_index)
    actor_positions: dict[int, tuple[int, int, int]] = {}

    def _best_actor_anchor(now_idx: int, max_age: int = 24) -> tuple[int, int] | None:
        eligible = [
            (idx, x, y)
            for (_actor, (x, y, idx)) in actor_positions.items()
            if now_idx - idx <= max_age
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda t: t[0], reverse=True)
        _idx, x, y = eligible[0]
        return x, y

    for idx, row in enumerate(rows):
        libcall = (row.get("libcall") or "").upper()
        args_display = row.get("args_display") or ""

        if libcall in {"SWALK", "WALK", "STAND"}:
            actor = _extract_imm_arg(args_display, "actor")
            motion_xy = _extract_motion_xy(args_display, libcall)
            if motion_xy is not None:
                mx, my = motion_xy
                current_motion = (mx, my)
                current_motion_idx = idx
                if actor is not None and actor >= 0:
                    actor_positions[actor] = (mx, my, idx)

        if libcall == "SCROLL":
            last_scroll_idx = idx

        if libcall == "TALKAT":
            talkat_anchor = _extract_talkat_anchor(args_display)
            if talkat_anchor is not None:
                current_dialogue_anchor = talkat_anchor
                current_dialogue_idx = idx
                current_dialogue_source = "timeline_talkat_anchor"

        if libcall == "TALK" and scheduler_talk_anchors:
            try:
                row_ip = int(row.get("ip") or 0)
            except ValueError:
                row_ip = 0
            talk_anchor = scheduler_talk_anchors.get(row_ip)
            if talk_anchor is not None:
                current_dialogue_anchor = talk_anchor
                current_dialogue_idx = idx
                current_dialogue_source = "timeline_talk_anchor"

        if libcall == "OFFSET":
            ox = _extract_imm_arg(args_display, "x")
            oy = _extract_imm_arg(args_display, "y")
            if ox is not None and oy is not None:
                current_offset = (ox, oy)
            continue

        if libcall != "PLAY":
            continue

        x = _extract_imm_arg(args_display, "x")
        y = _extract_imm_arg(args_display, "y")
        source = "none"
        use_xy: tuple[int, int] | None = None
        if x is not None and y is not None:
            if x >= 0 and y >= 0 and (x != 0 or y != 0):
                use_xy = (x, y)
                source = "timeline_args"
            elif x == 0 and y == 0 and current_offset != (0, 0):
                use_xy = current_offset
                source = "timeline_offset"
            elif x < 0 or y < 0 or (x == 0 and y == 0):
                actor_xy = _best_actor_anchor(idx, max_age=24)
                if actor_xy is not None:
                    use_xy = actor_xy
                    source = "timeline_actor_state"
                elif current_motion is not None and (idx - current_motion_idx) <= 24:
                    use_xy = current_motion
                    source = "timeline_motion"
                elif current_dialogue_anchor is not None and (idx - current_dialogue_idx) <= TALK_ANCHOR_MAX_AGE:
                    use_xy = current_dialogue_anchor
                    source = current_dialogue_source
                elif (
                    scheduler_rows_by_script_ip
                    and (idx - last_scroll_idx) <= SCROLL_PREFIX_MAX_AGE
                    and scene_name.upper() == CUTBARN_SCROLL_PREFIX_SCENE
                    and (row.get("script_handle") or "").upper() == CUTBARN_SCROLL_PREFIX_SCRIPT
                ):
                    try:
                        row_ip = int(row.get("ip") or 0)
                    except ValueError:
                        row_ip = 0
                    scheduler_row = scheduler_rows_by_script_ip.get((CUTBARN_SCROLL_PREFIX_SCRIPT, row_ip))
                    if scheduler_row is not None:
                        scroll_prefix_anchor = _extract_scroll_prefix_anchor_from_visible_stack(
                            scheduler_row.get("visible_stack") or ""
                        )
                        if scroll_prefix_anchor is not None:
                            use_xy = scroll_prefix_anchor
                            source = "timeline_scroll_prefix"
                if scheduler_rows_by_script_ip and use_xy is None and idx >= 2:
                    prev_libcall = (rows[idx - 1].get("libcall") or "").upper()
                    prev_prev_libcall = (rows[idx - 2].get("libcall") or "").upper()
                    if prev_prev_libcall == "PLAYSAMPLE" and prev_libcall == "WAITFRAME":
                        script_key = (row.get("script_handle") or "").upper()
                        try:
                            row_ip = int(row.get("ip") or 0)
                        except ValueError:
                            row_ip = 0
                        scheduler_row = scheduler_rows_by_script_ip.get((script_key, row_ip))
                        if scheduler_row is not None:
                            waitframe_prefix_anchor = _extract_scroll_prefix_anchor_from_visible_stack(
                                scheduler_row.get("visible_stack") or ""
                            )
                            if waitframe_prefix_anchor is not None:
                                use_xy = waitframe_prefix_anchor
                                source = "timeline_waitframe_prefix"
                if scheduler_rows_by_script_ip and use_xy is None:
                    script_key = (row.get("script_handle") or "").upper()
                    try:
                        row_ip = int(row.get("ip") or 0)
                    except ValueError:
                        row_ip = 0
                    known_key = (scene_name.upper(), script_key, row_ip)
                    if known_key in KNOWN_NON_TINY_PREFIX_IPS:
                        scheduler_row = scheduler_rows_by_script_ip.get((script_key, row_ip))
                        if scheduler_row is not None:
                            known_prefix_anchor = _extract_scroll_prefix_anchor_from_visible_stack(
                                scheduler_row.get("visible_stack") or ""
                            )
                            if known_prefix_anchor is not None:
                                xk, yk = known_prefix_anchor
                                if xk >= NON_TINY_PREFIX_MIN or yk >= NON_TINY_PREFIX_MIN:
                                    use_xy = known_prefix_anchor
                                    source = "timeline_prefix_known_non_tiny"

        candidates.append(
            {
                "film": row.get("film_args") or row.get("film"),
                "xy": use_xy,
                "source": source,
            }
        )
        if source == "timeline_talk_anchor":
            current_dialogue_anchor = None
            current_dialogue_idx = -999999
            current_dialogue_source = "none"
    return candidates


def _fallback_xy(index: int) -> tuple[int, int]:
    # Stable inspection-friendly placement for events missing decoded coordinates.
    return 80 + (index % 6) * 90, 180 - (index // 6) * 30


def build_timeline(
    vm_lite_csv: Path,
    scene_name: str = DEFAULT_SCENE,
    include_block_probe: bool = False,
    timeline_csv: Path | None = None,
    scheduler_csv: Path | None = None,
    include_motion_anchor: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    with vm_lite_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    scene_name = scene_name.upper()
    if not scene_name.endswith(".SCN"):
        scene_name = f"{scene_name}.SCN"
    bar_rows = [r for r in rows if (r.get("file") or "").upper() == scene_name]
    background_rows = [r for r in bar_rows if (r.get("libcall_name") or "").upper() == "BACKGROUND"]
    play_rows = [r for r in bar_rows if (r.get("libcall_name") or "").upper() == "PLAY"]
    play_rows.sort(key=lambda r: int(r.get("ip") or 0))

    runtime_nominals = _load_runtime_nominals(scene_name)
    block_polys = _load_block_polygons(SCENE_ROOT / scene_name)
    if include_motion_anchor:
        scheduler_talk_anchors = _load_scheduler_talk_anchors(scheduler_csv, scene_name)
        scheduler_rows_by_script_ip = _load_scheduler_rows_by_script_ip(scheduler_csv, scene_name)
        timeline_candidates = _load_timeline_play_candidates_with_motion(
            timeline_csv,
            scene_name=scene_name,
            scheduler_talk_anchors=scheduler_talk_anchors,
            scheduler_rows_by_script_ip=scheduler_rows_by_script_ip,
        )
    else:
        timeline_candidates = _load_timeline_play_candidates(timeline_csv)

    out: list[dict[str, object]] = []
    output_frame = 0
    event_seq = 0

    if background_rows:
        bg = sorted(background_rows, key=lambda r: int(r.get("ip") or 0))[0]
        bg_film = _extract_film_handle(bg)
        out.append(
            {
                "output_frame": output_frame,
                "event_seq": event_seq,
                "libcall": "BACKGROUND",
                "film": bg_film,
                "event_frame": 0,
                "x_used": 0,
                "y_used": 0,
                "position_source": "background",
                "placement_confidence": _placement_confidence_for_source("background"),
                "runtime_snap_applied": False,
                "source_png": "",
            }
        )
        output_frame += 1
        event_seq += 1

    nominal_count = 0
    fallback_count = 0
    decoded_nonzero_count = 0
    decoded_zero_count = 0
    block_snap_count = 0
    timeline_args_count = 0
    timeline_offset_count = 0
    timeline_motion_count = 0
    timeline_actor_state_count = 0
    timeline_talk_anchor_count = 0
    timeline_talkat_anchor_count = 0
    timeline_scroll_prefix_count = 0
    timeline_film_replay_count = 0
    timeline_neighbor_carry_count = 0
    timeline_waittime_family_carry_count = 0
    timeline_talk_family_carry_count = 0
    timeline_overedge_cluster_carry_count = 0
    timeline_bootstrap_carry_count = 0
    timeline_waitframe_prefix_count = 0
    timeline_prefix_known_non_tiny_count = 0
    # CUTBARN-specific replay bridge: film -> (x, y, play_index)
    film_recent_positions: dict[str, tuple[int, int, int]] = {}
    # Keep ordered play decisions to support narrowly scoped adjacent-carry probes.
    play_history: list[tuple[str, int, int]] = []
    for i, row in enumerate(play_rows):
        ip = int(row.get("ip") or 0)
        film = _extract_film_handle(row)
        script_handle = (row.get("script_handle") or "").strip().upper()
        timeline_xy = None
        timeline_source = "none"
        if i < len(timeline_candidates):
            timeline_xy = timeline_candidates[i].get("xy")
            timeline_source = str(timeline_candidates[i].get("source") or "none")

        parsed = _extract_xy_from_stack_top((row.get("stack_top") or "").strip())
        if parsed is not None:
            if parsed[0] == 0 and parsed[1] == 0:
                decoded_zero_count += 1
            else:
                decoded_nonzero_count += 1

        if isinstance(timeline_xy, tuple):
            x, y = timeline_xy
            position_source = timeline_source
            nominal_count += 1
            if timeline_source == "timeline_args":
                timeline_args_count += 1
            elif timeline_source == "timeline_offset":
                timeline_offset_count += 1
            elif timeline_source == "timeline_motion":
                timeline_motion_count += 1
            elif timeline_source == "timeline_actor_state":
                timeline_actor_state_count += 1
            elif timeline_source == "timeline_talk_anchor":
                timeline_talk_anchor_count += 1
            elif timeline_source == "timeline_talkat_anchor":
                timeline_talkat_anchor_count += 1
            elif timeline_source == "timeline_scroll_prefix":
                timeline_scroll_prefix_count += 1
            elif timeline_source == "timeline_waitframe_prefix":
                timeline_waitframe_prefix_count += 1
            elif timeline_source == "timeline_prefix_known_non_tiny":
                timeline_prefix_known_non_tiny_count += 1
        elif parsed is not None and parsed[0] >= 0 and parsed[1] >= 0 and (parsed != (0, 0) or ip in runtime_nominals):
            x, y = parsed
            position_source = "trace_stack_top"
            nominal_count += 1
        elif ip in runtime_nominals:
            x, y = runtime_nominals[ip]
            position_source = "placement_snapshot"
            nominal_count += 1
        elif (
            scene_name == CUTBARN_SCROLL_PREFIX_SCENE
            and script_handle == CUTBARN_SCROLL_PREFIX_SCRIPT
            and film in film_recent_positions
            and (i - film_recent_positions[film][2]) <= FILM_REPLAY_MAX_AGE
        ):
            x, y, _seen_idx = film_recent_positions[film]
            position_source = "timeline_film_replay"
            nominal_count += 1
            timeline_film_replay_count += 1
        elif (
            scene_name == CUTBARN_SCROLL_PREFIX_SCENE
            and script_handle == CUTBARN_SCROLL_PREFIX_SCRIPT
            and ip == CUTBARN_NEIGHBOR_CARRY_IP
        ):
            neighbor_xy: tuple[int, int] | None = None
            for back in range(1, min(CUTBARN_NEIGHBOR_CARRY_MAX_BACK, len(play_history)) + 1):
                prev_source, prev_x, prev_y = play_history[-back]
                if prev_source == "fallback_visual_validation":
                    continue
                neighbor_xy = (prev_x, prev_y)
                break
            if neighbor_xy is not None:
                x, y = neighbor_xy
                position_source = "timeline_neighbor_carry"
                nominal_count += 1
                timeline_neighbor_carry_count += 1
            else:
                x, y = _fallback_xy(i)
                position_source = "fallback_visual_validation"
                fallback_count += 1
        elif (scene_name, script_handle, ip) in WAITTIME_FAMILY_NEIGHBOR_CARRY_KEYS:
            neighbor_xy: tuple[int, int] | None = None
            for back in range(1, min(WAITTIME_FAMILY_NEIGHBOR_CARRY_MAX_BACK, len(play_history)) + 1):
                prev_source, prev_x, prev_y = play_history[-back]
                if prev_source == "fallback_visual_validation":
                    continue
                neighbor_xy = (prev_x, prev_y)
                break
            if neighbor_xy is not None:
                x, y = neighbor_xy
                position_source = "timeline_waittime_family_carry"
                nominal_count += 1
                timeline_waittime_family_carry_count += 1
            else:
                x, y = _fallback_xy(i)
                position_source = "fallback_visual_validation"
                fallback_count += 1
        elif (scene_name, script_handle, ip) in TALK_FAMILY_NEIGHBOR_CARRY_KEYS:
            neighbor_xy: tuple[int, int] | None = None
            for back in range(1, min(TALK_FAMILY_NEIGHBOR_CARRY_MAX_BACK, len(play_history)) + 1):
                prev_source, prev_x, prev_y = play_history[-back]
                if prev_source == "fallback_visual_validation":
                    continue
                neighbor_xy = (prev_x, prev_y)
                break
            if neighbor_xy is not None:
                x, y = neighbor_xy
                position_source = "timeline_talk_family_carry"
                nominal_count += 1
                timeline_talk_family_carry_count += 1
            else:
                x, y = _fallback_xy(i)
                position_source = "fallback_visual_validation"
                fallback_count += 1
        elif (scene_name, script_handle, ip) in OVEREDGE_CLUSTER_CARRY_KEYS:
            neighbor_xy: tuple[int, int] | None = None
            for back in range(1, min(OVEREDGE_CLUSTER_CARRY_MAX_DISTANCE, len(play_history)) + 1):
                prev_source, prev_x, prev_y = play_history[-back]
                if prev_source == "fallback_visual_validation":
                    continue
                neighbor_xy = (prev_x, prev_y)
                break
            if neighbor_xy is None:
                for ahead in range(1, OVEREDGE_CLUSTER_CARRY_MAX_DISTANCE + 1):
                    future_idx = i + ahead
                    if future_idx >= len(timeline_candidates):
                        break
                    future_candidate = timeline_candidates[future_idx]
                    future_xy = future_candidate.get("xy")
                    future_source = str(future_candidate.get("source") or "")
                    if not isinstance(future_xy, tuple):
                        continue
                    if future_source in {"none", "fallback_visual_validation"}:
                        continue
                    neighbor_xy = future_xy
                    break
            if neighbor_xy is not None:
                x, y = neighbor_xy
                position_source = "timeline_overedge_cluster_carry"
                nominal_count += 1
                timeline_overedge_cluster_carry_count += 1
            else:
                x, y = _fallback_xy(i)
                position_source = "fallback_visual_validation"
                fallback_count += 1
        elif (scene_name, script_handle, ip) in SINGLETON_BOOTSTRAP_CARRY_KEYS:
            neighbor_xy: tuple[int, int] | None = None
            for ahead in range(1, SINGLETON_BOOTSTRAP_CARRY_MAX_AHEAD + 1):
                future_idx = i + ahead
                if future_idx >= len(timeline_candidates):
                    break
                future_candidate = timeline_candidates[future_idx]
                future_xy = future_candidate.get("xy")
                future_source = str(future_candidate.get("source") or "")
                if not isinstance(future_xy, tuple):
                    continue
                if future_source in {"none", "fallback_visual_validation"}:
                    continue
                neighbor_xy = future_xy
                break
            if neighbor_xy is not None:
                x, y = neighbor_xy
                position_source = "timeline_bootstrap_carry"
                nominal_count += 1
                timeline_bootstrap_carry_count += 1
            else:
                x, y = _fallback_xy(i)
                position_source = "fallback_visual_validation"
                fallback_count += 1
        else:
            x, y = _fallback_xy(i)
            position_source = "fallback_visual_validation"
            fallback_count += 1

        x, y, snapped = _apply_block_snap(x, y, block_polys)
        if snapped:
            block_snap_count += 1

        out.append(
            {
                "output_frame": output_frame,
                "event_seq": event_seq,
                "libcall": "PLAY",
                "film": film,
                "event_frame": 0,
                "x_used": x,
                "y_used": y,
                "position_source": position_source,
                "placement_confidence": _placement_confidence_for_source(position_source),
                "runtime_snap_applied": snapped,
                "source_png": "",
            }
        )
        output_frame += 1
        event_seq += 1

        if position_source != "fallback_visual_validation" and film:
            film_recent_positions[film] = (x, y, i)
        play_history.append((position_source, x, y))

    block_probe_added = False
    if include_block_probe and block_polys:
        # Add a deterministic synthetic probe from the first BLOCK polygon centroid.
        p = block_polys[0]
        cx = int(sum(p["x"]) / 4)
        cy = int(sum(p["y"]) / 4)
        nx, ny, snapped = _apply_block_snap(cx, cy, block_polys)
        out.append(
            {
                "output_frame": output_frame,
                "event_seq": event_seq,
                "libcall": "PLAY_PROBE",
                "film": "probe:block_centroid",
                "event_frame": 0,
                "x_used": nx,
                "y_used": ny,
                "position_source": "block_centroid_probe",
                "placement_confidence": _placement_confidence_for_source("block_centroid_probe"),
                "runtime_snap_applied": snapped,
                "source_png": "",
            }
        )
        output_frame += 1
        event_seq += 1
        block_probe_added = True
        if snapped:
            block_snap_count += 1

    placement_confidence_counts = Counter()
    for event in out:
        confidence = str(event.get("placement_confidence") or "unknown")
        placement_confidence_counts[confidence] += 1

    manifest = {
        "scene": scene_name,
        "source": str(vm_lite_csv),
        "event_count_total": len(out),
        "background_events": 1 if background_rows else 0,
        "play_events": len(play_rows),
        "nominal_seeded_events": nominal_count,
        "fallback_events": fallback_count,
        "decoded_nonzero_events": decoded_nonzero_count,
        "decoded_zero_events": decoded_zero_count,
        "block_snap_applied_events": block_snap_count,
        "block_probe_added": block_probe_added,
        "timeline_args_events": timeline_args_count,
        "timeline_offset_events": timeline_offset_count,
        "timeline_motion_events": timeline_motion_count,
        "timeline_actor_state_events": timeline_actor_state_count,
        "timeline_talk_anchor_events": timeline_talk_anchor_count,
        "timeline_talkat_anchor_events": timeline_talkat_anchor_count,
        "timeline_scroll_prefix_events": timeline_scroll_prefix_count,
        "timeline_film_replay_events": timeline_film_replay_count,
        "timeline_neighbor_carry_events": timeline_neighbor_carry_count,
        "timeline_waittime_family_carry_events": timeline_waittime_family_carry_count,
        "timeline_talk_family_carry_events": timeline_talk_family_carry_count,
        "timeline_overedge_cluster_carry_events": timeline_overedge_cluster_carry_count,
        "timeline_bootstrap_carry_events": timeline_bootstrap_carry_count,
        "timeline_waitframe_prefix_events": timeline_waitframe_prefix_count,
        "timeline_prefix_known_non_tiny_events": timeline_prefix_known_non_tiny_count,
        "placement_confidence_counts": dict(placement_confidence_counts),
        "limitations": [
            "Coordinates are decoded from PLAY stack_top immediates when available and meaningful.",
            "When provided, timeline CSV PLAY args, dialogue anchors, and OFFSET state can override unresolved PLAY positions.",
            "Zero-valued decoded coordinates are treated as unresolved unless corroborated by placement snapshots.",
            "Remaining unresolved PLAY coordinates use deterministic fallback layout pending fuller runtime decode.",
            "BLOCK snap uses recovered 4-corner/4-pixel candidate model and Manhattan nearest choice.",
        ],
    }
    return out, manifest


def write_outputs(timeline: list[dict[str, object]], manifest: dict[str, object], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "output_frame",
        "event_seq",
        "libcall",
        "film",
        "event_frame",
        "x_used",
        "y_used",
        "position_source",
        "placement_confidence",
        "runtime_snap_applied",
        "source_png",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(timeline)

    manifest_path = output_csv.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_VM_LITE_CSV))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--scene", default=DEFAULT_SCENE)
    parser.add_argument("--include-block-probe", action="store_true")
    parser.add_argument("--timeline-csv", default=None)
    parser.add_argument("--include-motion-anchor", action="store_true")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if not source.exists():
        raise FileNotFoundError(f"vm-lite events CSV not found: {source}")

    timeline_csv = Path(args.timeline_csv) if args.timeline_csv else None
    if timeline_csv is None:
        candidate = DEFAULT_TIMELINE_DIR / f"{args.scene.replace('.SCN', '').upper()}_timeline.csv"
        if candidate.exists():
            timeline_csv = candidate

    timeline, manifest = build_timeline(
        source,
        scene_name=args.scene,
        include_block_probe=args.include_block_probe,
        timeline_csv=timeline_csv,
        include_motion_anchor=args.include_motion_anchor,
    )
    write_outputs(timeline, manifest, output)
    print(json.dumps({"output_csv": str(output), **manifest}, indent=2))


if __name__ == "__main__":
    main()
