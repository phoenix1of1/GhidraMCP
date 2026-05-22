from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional


TRUSTED_AUTO_POSITION_SOURCES = {
    'placement_snapshot',
    'timeline_actor_state',
    'timeline_args',
    'timeline_film_replay',
    'timeline_motion',
    'timeline_neighbor_carry',
    'timeline_offset',
    'timeline_prefix_known_non_tiny',
    'timeline_overedge_cluster_carry',
    'timeline_bootstrap_carry',
    'timeline_scroll_prefix',
    'timeline_talk_family_carry',
    'timeline_waittime_family_carry',
    'timeline_waitframe_prefix',
    'timeline_talk_anchor',
    'timeline_talkat_anchor',
    'trace_stack_top',
}


def parse_int(value: Any, default: int = 0) -> int:
    if value in ('', None):
        return default
    try:
        return int(value)
    except Exception:
        return default


def load_generated_scene_positions(
    timeline_path: Path,
    trusted_sources: Optional[set[str]],
) -> tuple[dict[int, dict[str, Any]], list[Optional[dict[str, Any]]], Counter[str], Counter[str]]:
    positions: dict[int, dict[str, Any]] = {}
    ordered_positions: list[Optional[dict[str, Any]]] = []
    trusted_confidence_counts: Counter[str] = Counter()
    trusted_source_counts: Counter[str] = Counter()
    with timeline_path.open('r', encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            if (row.get('libcall') or '').upper() != 'PLAY':
                continue
            position = {
                'x': parse_int(row.get('x_used'), -1),
                'y': parse_int(row.get('y_used'), -1),
                'position_source': row.get('position_source', ''),
                'placement_confidence': (row.get('placement_confidence') or 'unknown').lower(),
            }
            is_trusted = trusted_sources is None or position['position_source'] in trusted_sources
            ordered_positions.append(position if is_trusted else None)
            seq = parse_int(row.get('event_seq'), -1)
            if is_trusted and seq >= 0:
                positions[seq] = position
                trusted_confidence_counts[position['placement_confidence']] += 1
                trusted_source_counts[position['position_source']] += 1
    return positions, ordered_positions, trusted_confidence_counts, trusted_source_counts


def classify_skip(event: dict[str, Any], generated: Optional[dict[str, Any]]) -> str:
    if generated is not None:
        return 'trusted_generated_negative_xy'
    nominal_x = parse_int(event.get('x'), -1)
    nominal_y = parse_int(event.get('y'), -1)
    if nominal_x == 0 and nominal_y == 0:
        return 'nominal_zero_zero_without_trusted_generated'
    if nominal_x < 0 or nominal_y < 0:
        return 'nominal_negative_without_trusted_generated'
    return 'nominal_nonnegative_but_unplaced'


def analyze(base: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    play_composite_root = base / 'play_composite_export'
    play_first_root = base / 'play_first_export'
    summary_path = play_composite_root / 'play_composite_export_summary.csv'
    with summary_path.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))

    residual_rows: list[dict[str, Any]] = []
    cause_counts: Counter[str] = Counter()
    scene_counts: Counter[str] = Counter()
    scene_cause_counts: dict[str, Counter[str]] = {}
    trusted_generated_confidence_counts: Counter[str] = Counter()
    trusted_generated_source_counts: Counter[str] = Counter()
    scene_trusted_confidence_counts: dict[str, Counter[str]] = {}
    negative_generated_by_source: Counter[str] = Counter()
    negative_generated_by_confidence: Counter[str] = Counter()

    for row in rows:
        scene = row.get('scene', '')
        expected_skips = parse_int(row.get('skipped_negative_xy_count'), 0)
        scene_position_timeline = Path(row['position_timeline']) if row.get('position_timeline') else None
        position_timeline_mode = row.get('position_timeline_mode', '')
        if scene_position_timeline and scene_position_timeline.exists():
            trusted_sources = None if position_timeline_mode == 'curated_generated_csv' else TRUSTED_AUTO_POSITION_SOURCES
            generated_positions, ordered_generated_positions, scene_conf_counts, scene_source_counts = load_generated_scene_positions(
                scene_position_timeline,
                trusted_sources=trusted_sources,
            )
            trusted_generated_confidence_counts.update(scene_conf_counts)
            trusted_generated_source_counts.update(scene_source_counts)
            scene_trusted_confidence_counts[scene] = scene_conf_counts
        else:
            generated_positions, ordered_generated_positions = {}, []
            scene_trusted_confidence_counts[scene] = Counter()

        if expected_skips <= 0:
            continue

        stem = Path(scene).stem.lower()
        manifest_path = play_first_root / stem / 'manifest.json'
        if not manifest_path.exists():
            continue

        play_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

        resolved_events = [event for event in play_manifest.get('events', []) if event.get('preview_png')]
        scene_residuals = 0
        scene_cause_counter: Counter[str] = Counter()
        for play_index, event in enumerate(resolved_events):
            seq = parse_int(event.get('seq'), -1)
            generated = generated_positions.get(seq)
            if generated is None and play_index < len(ordered_generated_positions):
                generated = ordered_generated_positions[play_index]

            if generated is not None:
                x_used = parse_int(generated.get('x'), -1)
                y_used = parse_int(generated.get('y'), -1)
                position_source = generated.get('position_source', '')
                placement_confidence = generated.get('placement_confidence', 'unknown')
                position_resolution = 'generated_scene_space_timeline'
            else:
                x_used = parse_int(event.get('x'), -1)
                y_used = parse_int(event.get('y'), -1)
                position_source = 'nominal_play_args'
                placement_confidence = 'untrusted_or_nominal'
                position_resolution = 'nominal_fallback'

            if x_used >= 0 and y_used >= 0:
                continue

            cause = classify_skip(event, generated)
            scene_residuals += 1
            scene_counts[scene] += 1
            cause_counts[cause] += 1
            scene_cause_counter[cause] += 1
            if generated is not None:
                negative_generated_by_source[position_source] += 1
                negative_generated_by_confidence[placement_confidence] += 1
            residual_rows.append({
                'scene': scene,
                'seq': seq,
                'film_handle': event.get('film_handle', ''),
                'source_script': event.get('source', ''),
                'script_handle': event.get('script_handle', ''),
                'ip': event.get('ip', ''),
                'args_display': event.get('args_display', ''),
                'nominal_x': parse_int(event.get('x'), -1),
                'nominal_y': parse_int(event.get('y'), -1),
                'x_used': x_used,
                'y_used': y_used,
                'position_source': position_source,
                'placement_confidence': placement_confidence,
                'position_resolution': position_resolution,
                'position_timeline_mode': position_timeline_mode,
                'residual_cause': cause,
                'preview_png': event.get('preview_png', ''),
            })

        if scene_residuals != expected_skips:
            raise RuntimeError(
                f'{scene}: reconstructed {scene_residuals} skipped rows, expected {expected_skips}. '
                'The residual analysis no longer matches playcomposite behavior.'
            )
        scene_cause_counts[scene] = scene_cause_counter

    summary = {
        'base': str(base),
        'residual_skip_count': len(residual_rows),
        'scene_count_with_residual_skips': len(scene_counts),
        'residual_cause_counts': dict(cause_counts.most_common()),
        'scene_skip_counts': dict(scene_counts.most_common()),
        'trusted_generated_confidence_counts': dict(trusted_generated_confidence_counts.most_common()),
        'trusted_generated_source_counts': dict(trusted_generated_source_counts.most_common()),
        'negative_generated_by_source': dict(negative_generated_by_source.most_common()),
        'negative_generated_by_confidence': dict(negative_generated_by_confidence.most_common()),
        'scene_residual_cause_counts': {
            scene: dict(counter.most_common())
            for scene, counter in sorted(scene_cause_counts.items())
        },
        'scene_trusted_generated_confidence_counts': {
            scene: dict(counter.most_common())
            for scene, counter in sorted(scene_trusted_confidence_counts.items())
        },
        'largest_scene_bucket': next(iter(scene_counts.most_common(1)), None),
        'largest_cause_bucket': next(iter(cause_counts.most_common(1)), None),
    }

    promotion_candidates: list[dict[str, Any]] = []
    for source, count in trusted_generated_source_counts.items():
        negatives = negative_generated_by_source.get(source, 0)
        if count >= 2 and negatives == 0:
            promotion_candidates.append(
                {
                    'source': source,
                    'trusted_rows': count,
                    'negative_rows': negatives,
                    'suggested_action': 'candidate_for_confidence_promotion',
                }
            )
    summary['confidence_promotion_candidates'] = promotion_candidates

    return residual_rows, summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        'scene',
        'seq',
        'film_handle',
        'source_script',
        'script_handle',
        'ip',
        'args_display',
        'nominal_x',
        'nominal_y',
        'x_used',
        'y_used',
        'position_source',
        'placement_confidence',
        'position_resolution',
        'position_timeline_mode',
        'residual_cause',
        'preview_png',
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description='Analyze remaining skipped PLAY composites from an existing full playcomposite artifact.')
    parser.add_argument(
        '--base',
        type=Path,
        default=Path('outputs/full_playcomposite_pipeline'),
        help='Base output directory containing play_first_export and play_composite_export.',
    )
    parser.add_argument(
        '--csv',
        type=Path,
        default=None,
        help='Optional explicit residual CSV output path. Defaults to <base>/play_composite_export/play_composite_residual_skip_report.csv',
    )
    parser.add_argument(
        '--json',
        type=Path,
        default=None,
        help='Optional explicit JSON summary output path. Defaults to <base>/play_composite_export/play_composite_residual_skip_summary.json',
    )
    args = parser.parse_args()

    base = args.base.resolve()
    csv_path = args.csv.resolve() if args.csv else base / 'play_composite_export' / 'play_composite_residual_skip_report.csv'
    json_path = args.json.resolve() if args.json else base / 'play_composite_export' / 'play_composite_residual_skip_summary.json'

    residual_rows, summary = analyze(base)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(csv_path, residual_rows)
    json_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({
        'csv': str(csv_path),
        'json': str(json_path),
        **summary,
    }, indent=2))


if __name__ == '__main__':
    main()