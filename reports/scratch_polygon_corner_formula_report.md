# Scratch Polygon Corner-Generation Formula

## Scope

Target: decode the upstream formula that feeds the scratch runtime polygon at `0x1B228`, built by `0x37298` and later published as polygon index `0x100`.

## Result

The scratch polygon is generated as a small axis-aligned placement rectangle around a runtime coordinate pair. The routine writes four corner coordinates into the scratch polygon record before calling the polygon-initialization helper that derives bounds and line-equation data.

## Model

```text
runtime placement center / target coordinate
  -> expand by small placement radius
  -> write cx[4] / cy[4]
  -> initialize polygon derived fields
  -> publish as polygon_table[0x100]
```

## Scratch Polygon Corner Layout

The scratch polygon at `0x1B228` uses the same runtime polygon field layout already recovered:

| Offset | Field |
|---:|---|
| `+0x0A` | `cx[0]` |
| `+0x0C` | `cx[1]` |
| `+0x0E` | `cx[2]` |
| `+0x10` | `cx[3]` |
| `+0x12` | `cy[0]` |
| `+0x14` | `cy[1]` |
| `+0x16` | `cy[2]` |
| `+0x18` | `cy[3]` |

Coordinates are stored in the runtime high-word/fixed-style representation:

```c
stored = coord << 16;
coord  = stored >> 16;
```

## Corner Formula

The current recovered formula is:

```c
left   = target_x - radius_x;
right  = target_x + radius_x;
top    = target_y - radius_y;
bottom = target_y + radius_y;

cx[0] = left;
cy[0] = top;

cx[1] = right;
cy[1] = top;

cx[2] = right;
cy[2] = bottom;

cx[3] = left;
cy[3] = bottom;
```

The generated polygon is therefore an axis-aligned rectangular scratch polygon, not an arbitrary quadrilateral.

## Runtime Use

The generated rectangle is passed through the same polygon initialization path used for normal runtime polygons, producing:

- polygon bounding box
- per-side bounding rectangles
- line-equation coefficients

Then the pointer is published as the scratch polygon slot:

```text
polygon_table[0x100] -> 0x1B228
```

and the index `0x100` is returned to the PLAY placement pipeline.

## Extractor Impact

The playback model can now describe PLAY placement as:

```json
{
  "placement_pipeline": [
    "build_axis_aligned_scratch_polygon",
    "publish_polygon_table_slot_0x100",
    "adjust_against_BLOCK_polygon_corners"
  ],
  "scratch_polygon_shape": "axis_aligned_rectangle",
  "scratch_polygon_index": 256,
  "coordinates_are_fixed_high_word": true
}
```

## Remaining Unknown

The remaining unresolved part is the exact source and values of:

```text
target_x
target_y
radius_x
radius_y
```

The next target should be:

```text
Trace the source of target_x/target_y/radius_x/radius_y used by 0x37298.
```
