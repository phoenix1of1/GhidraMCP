#!/usr/bin/env python3
"""Compile BAR.SCN film-event animations into reusable full-colour asset packs.

This utility consumes the existing BAR ANI_SCRIPT-aware playback export and repacks
PLAY/STAND/BACKGROUND film animations by film handle. It is intentionally a packaging
compiler, not a new decoder.
"""
from __future__ import annotations

import argparse, json, shutil, csv
from pathlib import Path
from collections import defaultdict


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def compile_assets(src_dir: Path, out_dir: Path, include_background: bool = False) -> dict:
    manifest_path = src_dir / "bar_ani_script_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    data = json.loads(manifest_path.read_text())
    events = data.get("events", [])

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    packs = []
    rows = []
    grouped = defaultdict(list)
    for ev in events:
        kind = ev.get("libcall", "UNKNOWN")
        if kind == "BACKGROUND" and not include_background:
            continue
        if kind not in {"PLAY", "STAND", "BACKGROUND", "TOPPLAY", "SPLAY"}:
            continue
        grouped[ev.get("film_handle")].append(ev)

    for film_handle, film_events in sorted(grouped.items()):
        clean = film_handle.replace("0x", "").upper()
        pack_name = f"film_{clean}"
        pack_dir = out_dir / "characters" / "bar" / pack_name
        frames_dir = pack_dir / "frames"
        strips_dir = pack_dir / "strips"
        gifs_dir = pack_dir / "gifs"
        frames_dir.mkdir(parents=True, exist_ok=True)
        strips_dir.mkdir(exist_ok=True)
        gifs_dir.mkdir(exist_ok=True)

        # Prefer the first occurrence as canonical; record all occurrences as aliases.
        ev0 = sorted(film_events, key=lambda e: e.get("seq", 999999))[0]
        event_key = f"event_{ev0['seq']:03d}_{ev0['libcall']}_{clean}"
        src_event_frames = src_dir / "frames" / event_key
        frame_files = sorted(src_event_frames.glob("*.png"))
        copied_frames = 0
        for fp in frame_files:
            if copy_if_exists(fp, frames_dir / fp.name):
                copied_frames += 1

        strip_src = src_dir / ev0.get("strip", "")
        gif_src = src_dir / ev0.get("gif", "")
        strip_rel = None
        gif_rel = None
        if strip_src.exists():
            strip_rel = f"strips/{pack_name}_strip.png"
            copy_if_exists(strip_src, pack_dir / strip_rel)
        if gif_src.exists():
            gif_rel = f"gifs/{pack_name}.gif"
            copy_if_exists(gif_src, pack_dir / gif_rel)

        pack_manifest = {
            "pack_type": "discworld_tinsel1_full_colour_character_animation",
            "scene": "BAR.SCN",
            "asset_id": pack_name,
            "film_handle": film_handle,
            "canonical_event": {
                "seq": ev0.get("seq"),
                "libcall": ev0.get("libcall"),
                "frate": ev0.get("frate"),
                "numreels": ev0.get("numreels"),
                "expanded_frames": ev0.get("expanded_frames"),
                "notes": ev0.get("notes", []),
            },
            "all_event_occurrences": [
                {"seq": e.get("seq"), "libcall": e.get("libcall"), "expanded_frames": e.get("expanded_frames")}
                for e in sorted(film_events, key=lambda e: e.get("seq", 999999))
            ],
            "frames_dir": "frames/",
            "frame_count_exported": copied_frames,
            "strip_png": strip_rel,
            "gif": gif_rel,
            "colour_status": "full_colour_png_from_decoded_palette_and_bitmap_renderer",
            "runtime_limitations": [
                "actor identity not fully named; grouped by film handle",
                "exact in-scene placement/timing not guaranteed",
            ],
        }
        (pack_dir / "manifest.json").write_text(json.dumps(pack_manifest, indent=2))
        packs.append(pack_manifest)
        rows.append({
            "asset_id": pack_name,
            "film_handle": film_handle,
            "canonical_libcall": ev0.get("libcall"),
            "event_count": len(film_events),
            "frame_count_exported": copied_frames,
            "strip_png": strip_rel or "",
            "gif": gif_rel or "",
        })

    top_manifest = {
        "compiler": "bar_character_asset_compiler.py",
        "source": str(src_dir),
        "scene": "BAR.SCN",
        "pack_count": len(packs),
        "total_frames": sum(p["frame_count_exported"] for p in packs),
        "grouping": "film_handle",
        "status": "full-colour actor/character-style asset packs generated from BAR film events",
        "packs": [{
            "asset_id": p["asset_id"],
            "film_handle": p["film_handle"],
            "frame_count_exported": p["frame_count_exported"],
            "gif": f"characters/bar/{p['asset_id']}/{p['gif']}" if p.get("gif") else None,
            "manifest": f"characters/bar/{p['asset_id']}/manifest.json",
        } for p in packs]
    }
    (out_dir / "manifest.json").write_text(json.dumps(top_manifest, indent=2))
    with (out_dir / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["asset_id","film_handle","canonical_libcall","event_count","frame_count_exported","strip_png","gif"])
        w.writeheader(); w.writerows(rows)
    (out_dir / "README.md").write_text(f"""# BAR.SCN Character/Actor Asset Pack\n\nThis pack groups full-colour BAR.SCN animation assets by film handle.\n\n- Packs: {len(packs)}\n- Total exported frames: {top_manifest['total_frames']}\n- Grouping: film handle, because exact actor identity is not fully named yet.\n\nEach `characters/bar/film_<handle>/` folder contains:\n\n- `manifest.json`\n- `frames/*.png`\n- `strips/*.png`\n- `gifs/*.gif`\n\nThese are suitable for validation, sprite-sheet construction, and later actor identity mapping.\n""")
    return top_manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="/mnt/data/bar_ani_script_playback")
    ap.add_argument("--output", default="/mnt/data/bar_character_asset_pack")
    ap.add_argument("--include-background", action="store_true")
    args = ap.parse_args()
    manifest = compile_assets(Path(args.source), Path(args.output), args.include_background)
    print(json.dumps({"pack_count": manifest["pack_count"], "total_frames": manifest["total_frames"]}, indent=2))

if __name__ == "__main__":
    main()
