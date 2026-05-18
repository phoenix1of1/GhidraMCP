# Scratch Polygon Record Decode Report

## Scope

Target: decode the scratch polygon record built by `0x37298` at `0x1B228`, and confirm how it is linked into `polygon_table[0x100]`.

## Main result

Confirmed pipeline:

```text
0x37298
  -> writes generated corner fields into 0x1B228 region
  -> calls 0x370B0 to initialize derived polygon fields
  -> stores 0x1B228 into 0x1B218
  -> returns 0x100 in EAX
```

This strongly supports:

```text
polygon_table[0x100] = 0x1B228
```

or an equivalent fixed scratch-polygon slot mechanism.

## Relevant addresses

| Address | Meaning |
|---:|---|
| `0x37298` | scratch polygon builder region |
| `0x370B0` | runtime polygon initializer / derived-field calculator |
| `0x1B218` | scratch polygon pointer/table slot storage |
| `0x1B228` | scratch polygon record base |
| `0x100` | returned scratch polygon index |

## Observed writes in builder

Using base:

```text
base = 0x1B228
```

observed direct writes include:

| Address | Base offset | Interpretation |
|---:|---:|---|
| `0x1B234` | `+0x0C` | generated X/corner component |
| `0x1B236` | `+0x0E` | generated X/corner component |
| `0x1B238` | `+0x10` | generated X/corner component |
| `0x1B23A` | `+0x12` | generated Y/corner component |
| `0x1B23C` | `+0x14` | generated Y/corner component |
| `0x1B23E` | `+0x16` | generated Y/corner component |
| `0x1B240` | `+0x18` | generated Y/corner component |
| `0x1B242` | `+0x1A` | generated Y/corner component |

The builder writes enough corner source data for `0x370B0` to compute bounding boxes and line coefficients.

## Polygon initializer `0x370B0`

`0x370B0` reads corner fields and computes derived runtime polygon data, including:

- bounding rectangle fields
- per-side bounds
- line-equation coefficients

This matches the previously recovered runtime polygon layout used by point-in-polygon tests.

## Confirmed link to scratch slot

Observed sequence:

```asm
mov ebx, 0x1B228
mov eax, 0x1B228
call 0x370B0
mov [0x1B218], ebx
mov eax, 0x100
ret
```

Interpretation:

```c
Polygon *scratch = (Polygon *)0x1B228;
init_runtime_polygon(scratch);
polygon_table[0x100] = scratch;
return 0x100;
```

## Extractor model

```c
int build_scratch_play_polygon(...) {
    Polygon *p = &scratch_polygon;

    p->corner_fields = derive_from_runtime_context(...);
    init_runtime_polygon(p);

    polygon_table[0x100] = p;
    return 0x100;
}
```

## Confidence

| Finding | Confidence |
|---|---|
| scratch polygon base is `0x1B228` | confirmed |
| `0x370B0` initializes derived polygon fields | strong |
| return value `0x100` is the scratch polygon index | confirmed |
| `0x1B218` links/publishes the scratch polygon pointer | strong |
| exact table aliasing between `0x1B218` and `polygon_table[0x100]` | strong |
| exact upstream source-corner formula | partially decoded |

## Next target

Decode the upstream corner-generation formula feeding `0x1B228`, so final snapped `PLAY` coordinates can be computed rather than only annotated.
