# Discworld PC / Tinsel 1 Reverse Engineering Master Specification (Authoritative Edition)

## Scope

Reverse engineering notes for the DOS Discworld game using the Tinsel 1 engine.

Validated against:
- Original `.SCN` resource files
- `INDEX`
- `DWB.EXE`
- ScummVM Tinsel source
- Runtime tracing and reconstructed LE image analysis

Status:
- Extraction pipeline: highly validated
- Runtime/playback pipeline: partially reconstructed, still provisional in some scheduler/timing areas

---

# 1. Core Architecture

```text
INDEX
  -> SCN/GRA containers
      -> chunk chains
          -> FILM/FRAME/IMAGE graph
              -> renderer

PCODE VM
  -> libcall dispatcher
      -> scheduler/runtime systems
```

---

# 2. SCN Container Format

```c
struct Chunk {
    uint32 chunk_id;
    uint32 next_chunk_offset;
    uint8  payload[];
};
```

Traversal:

```c
offset = next_chunk_offset;
```

Terminal chunk:

```text
0x33340004
next = 0
```

Validated across 79 scene/resource files.

---

# 3. Important Chunk IDs

| Chunk | Meaning |
|---|---|
| `0x33340005` | palettes |
| `0x33340006` | images |
| `0x33340008` | films |
| `0x3334000A` | PCODE |
| `0x3334000B` | entrances |
| `0x3334000C` | polygons |
| `0x3334000D` | tagged actors |
| `0x3334000E` | scene struct |
| `0x33340012` | object registry |

---

# 4. INDEX Records

```c
struct INDEX_RECORD {
    char filename[12];
    uint32 size_flags;
    uint32 reserved;
};
```

---

# 5. SCNHANDLE Encoding

```c
file_index   = handle >> 23;
local_offset = handle & 0x007FFFFF;
```

Resolved in executable:

```text
0x24FEC
```

---

# 6. Palette Format

```c
struct PALETTE {
    int32 count;
    uint32 colors[count];
};
```

RGB packing:

```c
R = c & 0xFF;
G = (c >> 8) & 0xFF;
B = (c >> 16) & 0xFF;
```

---

# 7. Image Records

```c
struct IMAGE_RECORD {
    int16  width;
    uint16 height;
    int16  anim_x;
    int16  anim_y;
    uint32 bitmap_handle;
    uint32 palette_handle;
};
```

Size:

```text
16 bytes
```

---

# 8. Bitmap Rendering

Tinsel 1 PC render path:

```text
DrawObject() -> WrtNonZero()
```

Characteristics:
- 4x4 tile renderer
- negative tile indexes = transparent tiles
- palette-indexed rendering validated

---

# 9. Scene / Actor Structures

## Scene

```c
struct SCENE {
    uint32 numEntrance;
    uint32 numPoly;
    uint32 numTaggedActor;
    uint32 defRefer;
    uint32 hSceneScript;
    uint32 hEntrance;
    uint32 hPoly;
    uint32 hTaggedActor;
};
```

## Entrance

```c
struct ENTRANCE {
    uint32 entrance_number;
    uint32 script_handle;
};
```

## Tagged Actor

```c
struct TAGGED_ACTOR {
    int32 masking;
    uint32 actor_id;
    uint32 actor_script;
};
```

---

# 10. Object Registry

`OBJECTS.SCN`

```c
struct InventoryObject {
    uint32 id;
    uint32 icon_film;
    uint32 script;
    uint32 attributes;
};
```

Observed:
- 151 inventory objects

---

# 11. FILM Graph

```text
FILM
  -> reels
      -> MULTI_INIT
          -> FRAME
              -> IMAGE handles
```

## FILM

```c
struct FILM {
    int32 frate;
    int32 numreels;
};
```

## MULTI_INIT_T1

```c
struct MULTI_INIT_T1 {
    uint32 hMulFrame;
    int32 flags;
    int32 id;
    int32 x;
    int32 y;
    int32 z;
};
```

---

# 12. ANI_SCRIPT Commands

| Value | Meaning |
|---:|---|
| 0 | END |
| 1 | JUMP |
| 2 | HFLIP |
| 3 | VFLIP |
| 4 | HVFLIP |
| 5 | ADJUSTX |
| 6 | ADJUSTY |
| 7 | ADJUSTXY |
| 8 | NOSLEEP |
| 9 | CALL |
| 10 | HIDE |
| 11 | STOP |

---

# 13. PCODE VM

Interpreter loop:

```text
0x33B90
```

Libcall dispatcher:

```text
0x32F54
```

DW1 libcall table:

```text
0x35638
```

Important context offsets:

| Offset | Meaning |
|---|---|
| `+0x0C` | code ptr |
| `+0x20` | operand stack |
| `+0x228` | instruction ptr |
| `+0x22C` | stop/yield flag |

---

# 14. Scheduler ABI

Libcall handlers return:

```text
signed stack delta in EAX
```

Meaning:

```text
-N     consume N args
1-N    consume N args, return 1 value
```

Key calls:
- BACKGROUND
- PLAY
- STAND
- WALK / SWALK
- WAITFRAME
- WAITTIME
- EVENT
- TALK
- PLAYSAMPLE

---

# 15. PLAY Placement Pipeline

Recovered model:

```text
PCODE PLAY args
  -> scheduler/play cluster
      -> select_polygon_for_play_placement()
          -> scratch polygon index
      -> adjust_play_position_against_block_polygon()
          -> final coordinates
```

## Important Helpers

| Address | Meaning |
|---|---|
| `0x37298` | select_polygon_for_play_placement |
| `0x35B68` | adjust_play_position_against_block_polygon |
| `0x35B14` | find polygon containing point |
| `0x35938` | point-in-polygon test |

## Polygon Table

```text
0x1AE18 = runtime polygon pointer table
```

## BLOCK Polygon Logic

Runtime polygon type:

```text
BLOCK == 1
```

Behavior:
1. build 4 corner candidates
2. nudge by 4 pixels
3. validate against BLOCK polygons
4. choose nearest valid candidate

Distance metric:

```text
Manhattan distance
```

Scratch polygon index observed:

```text
0x100
```

---

# 16. Scratch Polygon Reconstruction

Scratch polygon memory:

```text
0x1B228
```

Published through:

```text
polygon_table[0x100]
```

Scratch rectangle formula:

```c
left   = target_x - footprint_x_extent;
right  = target_x + footprint_x_extent;
top    = target_y - footprint_y_extent;
bottom = target_y + footprint_y_extent;
```

Rectangle corners:

```c
(cx[0], cy[0]) = (left,  top);
(cx[1], cy[1]) = (right, top);
(cx[2], cy[2]) = (right, bottom);
(cx[3], cy[3]) = (left,  bottom);
```

---

# 17. RuntimeMoverPlacementState

Recovered working model:

```c
struct RuntimeMoverPlacementState {
    uint32 mover_id_or_handle;        // +0x00
    uint32 mover_runtime_ptr_or_ref;  // +0x04
    int32  current_x;                 // +0x08
    int32  current_y;                 // +0x0C
    int32  source_x;                  // +0x10
    int32  source_y;                  // +0x14
    int32  placement_flags_or_mode;   // +0x18
    int32  placement_aux_or_layer;    // +0x1C
    int32  placement_status;          // +0x20
    int32  target_x;                  // +0x24
    int32  target_y;                  // +0x28
    int32  entity_footprint_x_extent; // +0x2C
    int32  entity_footprint_y_extent; // +0x30
};
```

Confidence:
- target/footprint fields: strong
- earlier semantic labels: provisional

---

# 18. VM-lite Tracing

Implemented:
- opcode fetch
- stack tracking
- branch exploration
- film tracing
- scheduler tracing

Observed:
- 690 scripts
- 6449 trace events
- 2898 libcall events

---

# 19. Timeline / Playback Prototypes

Implemented:
- scene timelines
- film manifests
- visual asset export
- BAR playback prototype
- ANI_SCRIPT-aware frame strips
- scene-space playback viewer

BAR results:
- 14 film events
- 276 expanded animation frames
- 0 render failures

---

# 20. Character Asset Compiler

Implemented:
- full-colour actor/film asset packs
- PNG frames
- animation strips
- GIF previews

BAR export:
- 13 compiled packs
- 264 PNG frames
- 13 GIF previews

---

# 21. Unified CLI

Implemented:

```text
discworld_extract.py
```

Modes:
- chunks
- images
- scenegraph
- pcode
- films
- visual
- vm
- scheduler
- timelines
- all

---

# 22. Validation Status

Validated:
- SCN traversal
- INDEX parsing
- SCNHANDLE encoding
- image/palette decoding
- bitmap rendering
- FILM graph resolution
- PCODE/libcall discovery
- asset export pipeline

Still provisional:
- exact scheduler side effects
- deterministic timing
- exact runtime placement
- some RuntimeMoverPlacementState labels

---

# 23. Generated RE Tooling

Generated:
- Ghidra import package
- IDA import package
- symbol JSON
- runtime structure headers
- labeled CFG packs

Important caveat:
- many DW1 libcall targets are label entries inside shared code clusters, not standalone functions.

---

# 24. Current Project Status

Approximate completion:
- extraction pipeline: ~95%
- runtime-faithful playback: ~70–80%
- full gameplay/runtime emulation: much lower

Strongly solved:
- formats
- rendering
- film graph
- VM location
- scheduler discovery
- placement pipeline reconstruction

Remaining frontier:
- runtime-faithful scheduler behavior
- exact placement/timing convergence
- deterministic VM execution
