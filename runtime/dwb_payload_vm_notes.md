# DWB Payload VM Notes (Relocated Image)

Program: `dwb_le_relocated_image.bin` (rebased to `0x00010000`)

## Confirmed Core Functions

- `0x00033b90` `tinsel_pcode_interpreter_loop`
- `0x00032f54` `tinsel_pcode_libcall_dispatch`
- `0x00032ab8` `tinsel_script_attach_code_pointer`
- `0x00024fec` `tinsel_resolve_resource_pointer`
- `0x00039858` `tinsel_find_chunk_record_by_tag`
- `0x0002563c` `GetGlobalTickCounter`
- `0x00035938` `CheckBackgroundPointInside`
- `0x00035b68` `SelectPlayEventTargetPoint`
- `0x000362f4` `ProcessWaitframeWaittimeState`
- `0x00035f48` `ComputeStandTargetPointAndSegment`
- `0x00031b84` `UpdateActorMovementAndTarget`
- `0x00024c50` `ProcessMainSchedulerTickLoop`

## Interpreter Context Offsets (confirmed by disassembly)

- `+0x220`: stack top index
- `+0x224`: frame/base index
- `+0x228`: instruction pointer
- `+0x22c`: stop flag (loop exits when non-zero)
- `+0x230`: wait-state mode flag (set/cleared by opcode handlers near `0x3455e`)
- `+0x234`: wait-state captured value written after `CALL 0x00027e08`

## Confirmed Opcode Handler Evidence

### `OP_LIBCALL` variants

All call `tinsel_pcode_libcall_dispatch` (`0x32f54`) and then `tinsel_script_attach_code_pointer` (`0x32ab8`):

- `0x34162`: 32-bit immediate operand (IP += 4)
- `0x341a1`: 8-bit signed immediate operand (IP += 1)
- `0x341f8`: 16-bit signed immediate operand (IP += 2)

Interpreter labels added:

- `0x34162` `pcode_libcall_imm32_case`
- `0x341a1` `pcode_libcall_imm8_case`
- `0x341f8` `pcode_libcall_imm16_case`

Dispatcher prologue path at `0x32f54` includes:

- `CMP ECX,0x74`
- indirect jump through table at `0x25638`

### Flow/Call frame handler around `0x3409f`

Block at `0x3409f` manipulates frame bookkeeping slots (`+0x24/+0x28/+0x2c`), updates frame/base, reads next target from bytecode, and writes new `IP`.

### Wait-state toggles

Block near `0x3455e`:

- `MOV [ESI+0x230],0x1`
- `CALL 0x00027e08`
- `MOV [ESI+0x234],EAX`

Block near `0x34578`:

- `MOV [ESI+0x230],0x0`

Interpreter labels added:

- `0x3455e` `pcode_wait_state_enable_capture`
- `0x34578` `pcode_wait_state_disable`

## Timing Source Evidence

- `GetGlobalTickCounter` (`0x0002563c`) is a pure global read: returns `[0x000169a8]`
- `0x00027e08` calls `0x0002563c` and returns a derived value (`EAX - [0x00018210]` visible in current disassembly/decompilation)
- `0x00027e08` is called by both:
  - `tinsel_pcode_interpreter_loop` (`0x33b90`)
  - `0x0003c758`

These strongly suggest `0x27e08` is a runtime-relative tick/frame helper, but exact semantics still need one more cleanup pass due imperfect function boundaries.

## Libcall Dispatch Table Recovery

Generated artifacts:

- `outputs/dwb_payload_dump/dwb_libcall_table.json`
- `outputs/dwb_payload_dump/dwb_libcall_table.csv`
- `outputs/dwb_payload_dump/dwb_libcall_crosswalk.json`
- `outputs/dwb_payload_dump/dwb_libcall_crosswalk.csv`

High-value libcall entry labels applied in Ghidra:

- `0x0003596b` `libcall_background_idx11_entry`
- `0x00035b83` `libcall_event_idx31_entry`
- `0x00035d6b` `libcall_play_idx49_entry`
- `0x000360a3` `libcall_stand_idx72_entry`
- `0x00036334` `libcall_waittime_idx86_entry`
- `0x0003630a` `libcall_waitframe_idx100_entry`

Behavior notes from decompilation/disassembly:

- `CheckBackgroundPointInside` (`0x35938`) performs a bounded polygon/edge inclusion-style test and returns 0/1 for `(x,y)` against the current background region data.
  - current strongest interpretation: it first rejects against cached quad min/max bounds (`+0x2a/+0x2c/+0x2e/+0x30`), then uses the per-edge Y/X ranges and line terms (`+0x32/+0x3a/+0x42/+0x4a/+0x54/+0x64/+0x74`) prepared by `FUN_000370b0` to perform the real half-plane inclusion check
- `FUN_00035b14` (`0x35b14`) scans the `0x1ae18` background-region table and returns the first region index whose leading kind byte matches the requested selector byte in `BL` and whose geometry contains the candidate `(x,y)` point; it returns `-1` when no matching region is found.
- `SelectPlayEventTargetPoint` (`0x35b68`) computes four inward-offset corners for the chosen background region, scores them by Manhattan distance to the candidate `(x,y)`, and only accepts a corner when `FUN_00035b14` succeeds for both adjacent selector checks before writing the selected target coordinates through pointer args.
  - the helper is not movement-exclusive: a second noisy caller at `0x2fd08` loads a region id from a caller-local record at `+0x14`, passes stack locals as output pointers, and writes the returned point back into that record's `+0x00/+0x04` slots after the call
- `FUN_00037298` (`0x37298`) prepares the non-movement `SelectPlayEventTargetPoint` path by sampling two dispatch-chain bounds and seeding a global rectangular search window at `0x1b234..0x1b242`; current evidence fits an expanded min/max box used by the downstream target-selection flow.
- `FUN_000370b0` (`0x370b0`) consumes the shared quad buffer at `0x1b228` and precomputes reusable inclusion-test data for all four edges
  - first it caches the quad's min/max X/Y extents into local fields at `+0x2c/+0x2e/+0x30/+0x32`
  - then it iterates the four adjacent corner pairs and stores per-edge Y bounds plus `delta_y`, `delta_x`, and a cross-term constant at repeating slots (`+0x3c/+0x44/+0x4c/+0x54/+0x64/+0x70` pattern)
  - best current interpretation: this is shared quad edge-test preparation for downstream point-in-region or target-selection checks, not only a simple bounding-box cache
- Immediate pipeline confirmation:
  - in the movement path, `UpdateActorMovementAndTarget` calls `FUN_00037298` at `0x31ec8` and then calls `SelectPlayEventTargetPoint` at `0x31eec`
  - in the non-movement path, the noisy caller at `0x2fce3` calls `FUN_00037298` and then calls `SelectPlayEventTargetPoint` at `0x2fd08`
  - best current interpretation: the shared quad buffer and its derived edge-test terms are prepared specifically for immediate consumption by the `FUN_00035b14 -> CheckBackgroundPointInside -> SelectPlayEventTargetPoint` path, not as a long-lived global service for unrelated code
- `UpdateActorMovementAndTarget` (`0x31b84`) consumes those outputs and writes actor target fields (`param_1[2]` and `param_1[3]`) after `SelectPlayEventTargetPoint`, linking libcall behavior to runtime placement updates.
- `ProcessWaitframeWaittimeState` (`0x362f4`) handles wait-state globals (`0x1b370/0x1b374/0x1b378/0x1b37c`) and resolves actor references during WAITFRAME/WAITTIME processing.
- `ComputeStandTargetPointAndSegment` (`0x35f48`) computes a stand target point from scene geometry, choosing between nearest candidate point and line-projected point, and writes output `(x,y)` via pointer args.
- `ProcessMainSchedulerTickLoop` (`0x24c50`) invokes `ProcessWaitframeWaittimeState` once per scheduler iteration in the main game-loop tick path.

Additional internal label:

- `0x00027e20` `relative_tick_from_global_base` (core `GetGlobalTickCounter`-relative arithmetic site used by wait-state capture path)

## Actor Field Map (Evidence-backed, WIP)

From `UpdateActorMovementAndTarget` (`0x31b84`) assembly writebacks:

- `actor+0x08` (`param_1[2]`): target X (written at `0x31f06` after `SelectPlayEventTargetPoint`)
- `actor+0x0C` (`param_1[3]`): target Y (written at `0x31f0f` after `SelectPlayEventTargetPoint`)
- `actor+0x10` (`param_1[4]`) and `actor+0x14` (`param_1[5]`): paired movement/target slot copied/reset during movement state transitions
- `actor+0x1C` (`param_1[7]`) and `actor+0x20` (`param_1[8]`): second paired movement/target slot copied/reset during movement state transitions
- `actor+0x34` (`param_1[13]` byte): cleared to `0` immediately before target write + animation checks (likely movement phase/state byte)
- `actor+0x58` (`param_1[22]`) and `actor+0x5C` (`param_1[23]`): compared against current `(x,y)` for arrived-at-target checks

New labels in `UpdateActorMovementAndTarget` body:

- `0x00031eec` `call_select_play_event_target_point`
- `0x00031f06` `write_actor_target_x_from_play_event`
- `0x00031f0f` `write_actor_target_y_from_play_event`
- `0x00031f17` `post_target_write_anim_check`

Machine-readable export:

- `outputs/dwb_payload_dump/dwb_libcall_actor_field_writes.json`:
  - actor field hypotheses with confidence and evidence addresses
  - `libcall -> handler -> actor field write` mapping for BACKGROUND/EVENT/PLAY/STAND/WAITTIME/WAITFRAME
- `outputs/dwb_payload_dump/dwb_actor_field_access_matrix.json`:
  - per-field read/write direction with callsite addresses and containing function names
  - includes current/target/arrival fields used by `UpdateActorMovementAndTarget`

## Ghidra Type Application (Latest)

Applied via Ghidra MCP datatype/function endpoints:

- Created `ActorRuntimeStateLayout` as a sparse-offset struct (size `96` bytes)
- Bound `UpdateActorMovementAndTarget` (`0x31b84`) `param_1` to `ActorRuntimeStateLayout *`
- Bound helper `0x31b14` `param_1` to `ActorRuntimeStateLayout *`

Observed decompiler impact:

- `param_1[2]/param_1[3]` style accesses collapsed into named fields such as `nTarget_x`, `nTarget_y`, `nCurrent_x`, `nArrival_x`, etc.
- Remaining unknown slots now appear as explicit `field_0x..` members tied to a single actor type, which is a better base for iterative field renaming.

Important MCP schema note:

- For `/create_struct`, explicit offsets were only honored when each field used `field_offset` as a string value (for example `"field_offset":"88"`).
- Using numeric `offset` in our first attempt produced a packed 53-byte layout; recreated struct with `field_offset` produced the intended 96-byte sparse layout.

### ActorRuntimeStateLayout v1 naming pass

Additional fields overlaid and validated in movement/repath slice:

- `0x2c` `nPath_segment_id` (read in `UpdateActorMovementAndTarget` at `0x31c9a`, `0x31ced`)
- `0x48` `bArrival_block_byte` (zero-checked in `UpdateActorMovementAndTarget` at `0x31bee`, `0x31e44`)
- `0x54` `nRepath_retry_counter` (reset/increment/clip loop in `FUN_00031b14` at `0x31b5a`, `0x31b68`, `0x31b6f`, `0x31b77`)

Correction after disassembly-first validation:

- The prior `0x3c/0x40/0x44` naming was a decompiler artifact and is not a direct struct access.
- Real operands in `UpdateActorMovementAndTarget` are at `+0x27c`, `+0x280`, `+0x284` (see `0x31c6b`, `0x31c7d`, `0x31ba6`, `0x31c52`, `0x31d66`).
- These should be treated as higher-offset control state in a larger owner context, not as members of the compact actor runtime sub-struct.

### ActorRuntimeStateLayoutV2 (current canonical type)

- Created `ActorRuntimeStateLayoutV2` with explicit sparse offsets and size `96` bytes.
- Rebound `0x31b84` and `0x31b14` `param_1` to `ActorRuntimeStateLayoutV2 *`.
- Preserved evidence-backed members (`0x2c`, `0x48`, `0x54`, `0x49`, `0x50`, `0x58`, `0x5c`) while leaving `+0x27c/+0x280/+0x284` unresolved pending owner-struct reconstruction.

Machine-readable refresh:

- Regenerated `outputs/dwb_payload_dump/dwb_actor_field_access_matrix.json` after adding verified `0x2c/0x48/0x54` entries.

### Owner-structure reconstruction (current active typing)

- Created `ActorOwnerStateV1` (size `648` bytes) with:
  - embedded `actor` field at offset `0x00` of type `ActorRuntimeStateLayoutV2`
  - owner control fields `0x27c/0x280/0x284` as `nControl_state_27c`, `nControl_state_280`, `nControl_state_284`
  - owner-local fields `0x60/0x64/0x6c` as `nMovement_reset_latch`, `nFallback_motion_flag`, `nHelper_reset_guard`

Movement control refinement:

- `owner + 0x280` now has a stronger behavioral interpretation than the neighboring provisional control fields
  - in `UpdateActorMovementAndTarget`, when `owner + 0x27c == 1`, the function increments global `0x1ad6c`, compares it against `owner + 0x280`, and returns early until the threshold is reached
  - once the threshold is met, the global counter is reset to zero and normal movement processing resumes
  - best current interpretation: `owner + 0x280` is a per-owner wait-threshold in ticks, while `owner + 0x27c` remains the mode/enable gate for that delayed path

- Rebound movement slice parameters to `ActorOwnerStateV1 *`:
  - `UpdateActorMovementAndTarget` (`0x31b84`)
  - `FUN_00031b14` (`0x31b14`)

Decompiler readability gain:

- `+0x27c/+0x280/+0x284` now render as explicit owner control fields instead of opaque `field_0x..` accesses.
- Actor fields remain readable through `(param_1->actor).<field>` and preserve the validated actor-v2 offset map.

New machine-readable owner export:

- `outputs/dwb_payload_dump/dwb_owner_control_access_matrix.json`
  - includes validated accesses for `0x60`, `0x64`, `0x6c`, `0x27c`, `0x280`, `0x284`
  - captures both reads/writes and evidence addresses in the movement-owner slice

### Outer-hop caller context (DispatchCursorV1)

From clean disassembly at `0x0001f6a4`:

- `+0x08` repeatedly read as pointer argument for helper calls (`0x1f6f2`, `0x1f703`, `0x1f714`, `0x1f71f`, `0x1f734`, `0x1f755`)
- `+0x0c` read at entry and passed into `tinsel_resolve_resource_pointer` (`0x1f6ac` -> `0x24fec`)
- `+0x10` is stronger than a generic loop counter: `FUN_0001f6a4` uses it as an index into the resolved resource stream (`MOV EAX, [ESI + EAX*4]` at `0x1f6bb` / `0x1f6e6`), then increments or relative-adjusts it before looping
- best current interpretation for `+0x10` is a dispatch script/program counter rather than a plain ordinal index

Datatype created:

- `DispatchCursorV1` with `pOwner_ptr@0x08`, `nResource_selector@0x0c`, `nDispatch_script_pc@0x10`

Prototype caveat:

- Attempted typed prototype on `FUN_0001f6a4` was rolled back to `void` because MCP prototype application produced stack-parameter modeling inconsistent with observed entry register usage in this noisy/overlapping region.
- Keep `DispatchCursorV1` as evidence-backed datatype for future one-hop propagation when a cleaner call boundary is isolated.

New machine-readable caller export:

- `outputs/dwb_payload_dump/dwb_dispatch_cursor_access_matrix.json`
  - captures read/write evidence for `DispatchCursorV1` fields from disassembly

### Clean wrapper boundary for dispatch handoff

Clean caller evidence isolates `FUN_0001f864` as the first usable boundary outside noisy `FUN_0001f6a4`:

- `FUN_00038544` (`0x385ca`) passes `EAX = owner + 0x74` and `EDX = dword ptr [owner + 0x70]` into `FUN_0001f864`
- `FUN_0003869c` (`0x38740`) passes the same pair: `EAX = owner + 0x74`, `EDX = dword ptr [owner + 0x70]`
- both sites use the same enclosing owner object already modeled as `ActorOwnerStateV1`

Mid-function disassembly in `FUN_0001f864` gives the one reliable inner handoff:

- `0x1f890`: `MOV ECX,dword ptr [ECX + 0x4]`
- `0x1f8ac`: `CALL 0x0001f6a4`

Working interpretation for schema v1:

- `ActorOwnerStateV1 + 0x74` is the wrapper base passed to `FUN_0001f864`
- wrapper `+0x04` is the pointer handoff used to supply `DispatchCursorV1 *` to `FUN_0001f6a4`
- `DispatchCursorV1.pOwner_ptr@0x08` remains the direct pointer edge back to `ActorOwnerStateV1`
- `ActorOwnerStateV1` continues to embed `ActorRuntimeStateLayoutV2` at offset `0x00`

Caveat:

- entry bytes in `FUN_0001f864` remain partially overlapping/noisy, so only the clean caller setup and the mid-function `MOV ECX,[ECX + 0x4]` handoff are treated as schema evidence.

Live Ghidra application now in place:

- created `DispatchWrapperSlotV1` as a concrete datatype and applied a typed prototype to `FUN_0001f864`
- extended `ActorOwnerStateV1` with named owner-side dispatch fields:
  - `pDispatch_chain_head@0x70 : DispatchChainNodeV2 *`
  - `dispatchWrapper@0x74 : DispatchWrapperSlotV1`
  - `dwDispatch_resource_selector@0x88 : uint`
  - `dwDispatch_resource_selector_saved@0x8c : uint`
- current wrapper layout in Ghidra:
  - `dwUnknown_00@0x00 : uint`
  - `pDispatch_cursor@0x04 : DispatchCursorV1 *`
  - `dwUnknown_08@0x08 : uint`
  - `dwUnknown_0c@0x0c : uint`
  - `dwUnknown_10@0x10 : uint`
- current decompiler prototype renders as `char __regparm3 FUN_0001f864(DispatchWrapperSlotV1 *pWrapper)`
- clean owner-side callers now render the explicit outer cast:
  - `FUN_0001f864((DispatchWrapperSlotV1 *)(param_1 + 0x74));`
- owner-typed `FUN_0003869c` now resolves the embedded wrapper directly as:
  - `FUN_0001f864(&pOwner->dispatchWrapper);`
- `FUN_00038544` still stays on the raw pointer form because forcing an `ActorOwnerStateV1 *` prototype there degraded the decompile due to an additional implicit `BL` mode input.

Dispatch-field semantics strengthened from adjacent helpers:

- `+0x70` is no longer treated as a plain integer slot; current evidence supports `pDispatch_chain_head`
  - `FUN_00038658` waits until `owner + 0x70` becomes non-zero before dispatching
  - `FUN_00038544` and `FUN_0003869c` pass `owner + 0x70` alongside `dispatchWrapper` into `FUN_0001f864`
  - `FUN_00038544` also passes `owner + 0x70` into `FUN_00032278`
  - `FUN_00032278` treats its first parameter as a linked chain head (`node->next` at `+0x04`) and propagates state through the chain (`node + 0x10`, `node + 0x25`)
  - parallel helper `FUN_00031fe8` constructs the same kind of linked chain by repeatedly linking `*(node + 4)` from resource-derived entries, reinforcing the pointer/chain interpretation
- `+0x128` now has a stronger owner-side meaning as a dispatch-selector matrix base
  - `FUN_00038658` waits until `owner + 0x70` becomes non-zero, then indexes `owner + 0x128`
  - the row index comes from the embedded actor's `nMotion_or_wait_flag` at `owner + 0x50` and is scaled by `0x10`
  - the column index comes from the high byte of `owner + 0x49` and is scaled by `0x4`
  - the looked-up dword is passed directly as the selector argument to `FUN_00038544`
  - best current interpretation: `owner + 0x128` is a per-owner dispatch selector matrix keyed by motion/wait state row and facing column

Movement-state helper refinement:

- `FUN_00036a24` now has a stable role in the movement spine
  - both call sites are in `UpdateActorMovementAndTarget` (`0x31dc0`, `0x31f23`), and both compare its return value against the embedded actor field at `owner + 0x50`
  - internally it resolves per-segment metadata from the background resource table, uses the actor's path-segment id plus a Y-position input, and chooses a state band from resource fields at `+0x44/+0x48`
  - this tightens `actor + 0x50`: it is better treated as a motion/wait state id used as the selector-row key, not as a generic animation-id field

Nearby-blocker helper refinement:

- `FUN_00038a44` now looks more like a crowd/nearby-blocker scan than an arrival predicate
  - both `UpdateActorMovementAndTarget` and `FUN_000301a8` call it as a branch gate, but the helper itself first checks `actor + 0x38` and only enters the scan when that field is `-1`
  - in the scan path it walks up to six owner records at stride `0x290`, skips self and inactive records, and only accepts candidates whose `owner + 0x70` dispatch-chain pointer is non-zero
  - the acceptance test then compares candidate-projected coordinates plus min/max chain bounds derived from `FUN_00032304` and `FUN_0003232c`, which is consistent with a nearby overlap/blocking test rather than target-arrival logic
  - best current interpretation: `actor + 0x38` is a provisional nearby-blocker slot or sentinel, with `-1` meaning "no blocker currently linked"

Waypoint-advance helper refinement:

- `FUN_000301a8` now has a narrower movement-side contract
  - both `UpdateActorMovementAndTarget` call sites pass the current actor target and path-segment context, then compare the returned coordinates against the actor's current `(x,y)` before deciding whether to advance or bail out
  - early in the helper, two candidate segment ids are compared against a caller-supplied current segment pair at offsets `+0x1c/+0x20`; if both already match, the helper clears its out step-status flag instead of reporting a segment transition
  - best current interpretation: `FUN_000301a8` computes or verifies the next waypoint together with its segment-pair transition state, rather than being a generic geometry routine

Waypoint status reduction:

- `FUN_0002f12c` now has a stable role above `FUN_000301a8`
  - it is called from multiple `UpdateActorMovementAndTarget` sites and from the non-movement shared-target path
  - it first calls `FUN_00036bdc`, which translates the current region id through the resolved background metadata table and returns a one-byte navigation-class code from resource offset `+0x4c` (with region `-1` mapped to sentinel `0xffffff01`)
  - the control split is now stronger: only class `2` enters the waypoint-traversal loop, while any other classifier result is returned to the caller unchanged (so the `-1` sentinel path collapses to direct return value `1`)
  - the first two movement callers (`0x31c1e`, `0x31e74`) compare that returned class byte against `actor + 0x4c`, and a mismatch immediately calls `FUN_0003869c`
  - the third movement caller (`0x31f12`) first compares the motion/wait state returned by `FUN_00036a24` against `actor + 0x50`, then compares the `FUN_0002f12c` class byte against `actor + 0x4c`; if either selector changed, it calls `FUN_0003869c`
  - `FUN_0003869c` now has a stronger local contract: after resolving and reloading the dispatch resource, its epilogue writes the accepted motion/wait state back to `actor + 0x50` and the accepted navigation class back to `actor + 0x4c`
  - this closes the selector model: `actor + 0x50` and `actor + 0x4c` are a paired dispatch-cache key, with `FUN_0003869c` acting as the refresh-and-cache-writeback path when either the motion-state row or navigation-class selector changes
  - after that classification step, it repeatedly calls `FUN_000301a8` while the step-status remains `6`
  - when `FUN_000301a8` reports `5`, `FUN_0002f12c` returns terminal status `3`; when it reports `9`, it returns terminal status `9`
  - best current interpretation: `FUN_0002f12c` reduces multi-step waypoint traversal into a smaller set of caller-visible movement/target statuses, rather than directly selecting geometry itself

Dispatch chain datatype (current live typing):

- created `DispatchChainNodeV2` as the current evidence-backed node layout
- validated on `FUN_00032278`, which now decompiles as a linked-list walk over `pNode->pNext`
- current evidence-backed members:
  - `pNext@0x04 : DispatchChainNodeV2 *`
  - `nDelta_x_fixed16@0x08 : int`
  - `nDelta_y_fixed16@0x0c : int`
  - `dwDispatch_value_10@0x10 : uint`
  - `dwFlags_24@0x24 : uint` with the propagated byte flag currently observed as `*((byte *)&dwFlags_24 + 1)`
  - `pDispatch_cache_slot@0x28 : void *`
  - `nFrame_width_30@0x30 : int`
  - `nFrame_height_34@0x34 : int`
  - `dwNext_resource_handle_38@0x38 : uint`
  - `dwResource_handle_3c@0x3c : uint`
  - `dwDispatch_selector_48@0x48 : uint`
- propagated `ActorOwnerStateV1.pDispatch_chain_head` from `void *` to `DispatchChainNodeV2 *`
- strengthened semantics around the ordering keys:
  - `FUN_000326b0` writes `DispatchBuildDescriptorV1.dwNode_value_14` directly into `dwDispatch_value_10@0x10`
  - the resource-backed path writes `nDelta_y_fixed16@0x0c` as `(nTarget_y_10 - resolved_anchor_y) << 16`
  - the no-resource path writes `nDelta_y_fixed16@0x0c` as `nTarget_y_10 << 16`
  - `FUN_000321a8` propagates integer deltas through the chain by adding `x << 16` to `nDelta_x_fixed16@0x08` and `y << 16` to `nDelta_y_fixed16@0x0c`
  - `FUN_00032278` overwrites `dwDispatch_value_10@0x10` across the whole chain, so the value that drives sorted insertion is often assigned after build time rather than frozen in the original descriptor
  - current medium-confidence interpretation: `dwDispatch_value_10@0x10` is a packed ordering/control code rather than a plain phase id
    - direct propagated literals currently observed include `0x3de`, `0x3e3`, `0x3e4`, `0xb`, and `0xffffffff`
    - `FUN_0001f46c` computes `nPropagateValue` in `0x400`-sized bands plus a caller-supplied offset before calling `FUN_00032278`, which looks more like layered priority packing than a single enum/state slot
    - `FUN_00032388` now gives one concrete source for that caller-supplied offset: it walks the chain and returns `max((nDelta_y_fixed16 >> 16) + nFrame_height_34) - 1` across nodes with a nonzero resource handle
    - that makes the low bits of `dwDispatch_value_10@0x10` look like a bottom-edge or depth cutoff term layered beneath a coarser band
    - `FUN_000382f0` and `FUN_00038544` propagate `0xffffffff` when owner-side state indicates a special mode, which is strongest as a control sentinel rather than a normal draw band

Dispatch builder descriptor (current live typing):

- created `DispatchBuildDescriptorV1` as the shared 6-dword input consumed by `FUN_000326b0`
- current descriptor layout:
  - `dwResource_handle_00@0x00 : uint`
  - `dwBuild_flags_04@0x04 : uint`
  - `dwDispatch_selector_08@0x08 : uint`
  - `nTarget_x_0c@0x0c : int`
  - `nTarget_y_10@0x10 : int`
  - `dwNode_value_14@0x14 : uint`
- rebound `FUN_000326b0` to `DispatchChainNodeV2 * FUN_000326b0(DispatchBuildDescriptorV1 *pBuildDesc)`
- practical decompiler gains from the builder typing:
  - `FUN_000326b0` now renders node population through named `DispatchChainNodeV2` fields instead of raw `+0x..` writes
  - `FUN_00031fe8` now materializes an explicit `DispatchBuildDescriptorV1 local_28` and repeatedly relinks `pNext` while rebuilding the chain from `*(entry + 4)`
  - `FUN_00032820` now shows the static-call pattern `FUN_000326b0((DispatchBuildDescriptorV1 *)0x12f20)`

Static descriptor caveat:

- attempting to apply `DispatchBuildDescriptorV1` at `0x12f20` failed because Ghidra currently has conflicting instructions at that address range
- `FUN_00032820` really does materialize the literal address in machine code (`MOV EAX,0x12f20`) before calling `FUN_000326b0`, so the constant is not a decompiler invention
- byte-level inspection around `0x12f20` decodes as incoherent instruction noise, which is consistent with an embedded data blob living inside a currently misidentified code region
- reading the dumped payload bytes at both plausible file offsets (`0x2f20` for base-normalized mapping and `0x12f20` for base-padded mapping) does not yield a sane five-dword `DispatchBuildDescriptorV1` instance either
- current evidence therefore supports only this cautious claim: `0x12f20` is a real builder input address in code, but its representation in the dumped image is still unresolved
- treat `0x12f20` as a likely static build-descriptor candidate, but do not freeze it as typed data until the surrounding code/data boundary is cleaned up

Builder-side semantic gains from neighbor analysis:

- created `DispatchResolvedResourceV1` as the minimal resolved-header datatype for this slice:
  - `wFrame_width_00@0x00 : undefined2`
  - `wFrame_height_02@0x02 : undefined2`
  - `wAnchor_x_04@0x04 : undefined2`
  - `wAnchor_y_06@0x06 : undefined2`
  - `dwNext_resource_handle_08@0x08 : uint`
  - `dwDispatch_cache_key_0c@0x0c : uint`
- applied a narrow live prototype update to `tinsel_resolve_resource_pointer` so it now returns `DispatchResolvedResourceV1 *`
- this change improved the clean local slice without destabilizing the surrounding typed boundaries:
  - `FUN_00032628` now renders the resolved header as `DispatchResolvedResourceV1 *pDVar4` and makes the `+0x04/+0x06` anchor fields plus the `+0x0c` cache-key slot explicit
  - `FUN_00023db4` now cleanly renders `dwDispatch_cache_key_0c` plus the centering math `wFrame_width_00 / 2 - wAnchor_x_04` and `wFrame_height_02 / 2 - wAnchor_y_06`, which is the strongest current evidence for those width/height names
  - `FUN_0002a9bc` now renders the resource-header pointer directly and still shows the `0x1fc78` return being written into header `+0x0c`, reinforcing the cache-key interpretation
- keep one caveat explicit: `FUN_0002a9bc` still rebuilds intermediate resolver arguments from the first dword of the resolved header, so the exact relationship between `wFrame_width_00/wFrame_height_02` and chained resource lookup is not fully settled yet
- traced that node-side copy path through `FUN_0003275c`, which rewrites node `+0x30/+0x34/+0x38` directly from `DispatchResolvedResourceV1.wFrame_width_00`, `wFrame_height_02`, and `dwNext_resource_handle_08`
- live Ghidra has now been updated to match that reading in `DispatchChainNodeV2`:
  - `nFrame_width_30@0x30 : int`
  - `nFrame_height_34@0x34 : int`
  - `dwNext_resource_handle_38@0x38 : uint`
- applied a narrow live prototype update to `FUN_0003275c`, which now decompiles cleanly as `void __regparm3 FUN_0003275c(DispatchChainNodeV2 *pNode, uint dwBuild_flags)`
- that decompile now reads as a true node retarget helper: it compares `dwResource_handle_3c` and `dwFlags_24`, refreshes `nFrame_width_30/nFrame_height_34/dwNext_resource_handle_38` from the resolved header when needed, then adjusts the fixed16 deltas by the anchor-extent difference

Machine-readable cache-key export:

- added `runtime/build_dispatch_cache_key_matrix.py` and generated `outputs/dwb_payload_dump/dwb_dispatch_cache_key_matrix.json`
- the export freezes the current strongest contract for the overlapping blob at `0x1fc78`:
  - every clean dynamic caller resolves a resource header, moves that pointer into `EDX`, calls `0x1fc78`, then stores returned `EAX` into `DispatchResolvedResourceV1.dwDispatch_cache_key_0c`
  - this call-site evidence is now strong enough to state a register-level contract even though the blob body is still overlapping: `EAX` carries the produced dispatch cache key, while `EDX` remains a threaded caller-owned context register across the call
  - the two static helper callers (`FUN_00028d54`, `FUN_0002aab0`) reuse the same blob but thread its result into `FUN_00032820` instead of storing through a resolved header pointer immediately
  - side effects inside the blob itself remain low-confidence because the entry lies inside overlapping instruction flow
- one caller-specific byte pass now exposes two coherent overlapping substreams worth preserving, both still low-confidence:
  - `0x1fc80`: `MOV [0x00013c9c], EAX; RET`
  - `0x1fc88`: `PUSH EDX; XOR EDX, EDX; MOV [0x0005207c], EDX`
- those substreams are now exported in `dwb_dispatch_cache_key_matrix.json`, but they should still be treated as candidate internal decodes rather than stable function bodies
- a follow-up xref pass clarified that both addresses are also real direct helper entries in their own right:
  - `FUN_0001fc80` is high-confidence and now best understood as a tiny setter that stores caller-supplied `EAX` into global `0x13c9c` and returns; direct callers pass observed values `0` and `1`
  - `FUN_0001fc88` is medium-confidence and acts like a blob-local reset/init entry: the body zeroes `DAT_0005207c` and neighboring state before flowing into a still-noisy path, and `FUN_00024c00` calls it directly before a broader initialization sequence
- applied a narrow live prototype update to `FUN_0001fc80`, which now decompiles as `void __regparm3 FUN_0001fc80(uint dwValue)`
- that change paid off immediately in direct callers:
  - `FUN_00024a8c` now shows `FUN_0001fc80(0)` and `FUN_0001fc80(1)` on the two previously ambiguous paths
  - `FUN_000390ec` now shows the explicit call `FUN_0001fc80(1)` inside the same state-machine branch that previously only exposed the raw entry address
- a neighboring read-side candidate now rounds out the same local helper cluster:
  - `0x1fe6c` decodes cleanly as `MOV EAX, [0x0005207c]; RET`
  - there are no direct xrefs to `0x1fe6c` yet, so it remains a medium-confidence helper candidate rather than a confirmed function boundary
  - the noisy containing blob still contributes two useful concrete access patterns inside `FUN_0001fafc`:
    - `0x1fb65`: `ADC byte ptr [EBP + 0x5207c], AL`
    - `0x1fcbe`: `MOV EAX, [0x0005207c]`
  - that combination is stronger evidence for `0x5207c` as mutable blob-local state than for a simple boolean latch: one entry zeroes it, one path updates its low byte arithmetically, and another path reads the full dword back
  - together with `FUN_0001fc80` and `FUN_0001fc88`, this suggests the former blob region contains a small state-helper cluster rather than one monolithic opaque routine:
    - `FUN_0001fc80`: high-confidence setter for global `0x13c9c`
    - `FUN_0001fc88`: medium-confidence reset/init helper that zeroes `0x5207c`
    - `0x1fe6c`: medium-confidence getter-like candidate for `0x5207c`

Post-cache staging sequence:

- `FUN_0001fad4` is now a useful stable boundary adjacent to the cache-key path rather than another anonymous noisy window:
  - Ghidra recognizes `FUN_0001fad4` as a real function entry at `0x1fad4` with many callers, including `FUN_00023db4`, `FUN_0002a9bc`, `FUN_00028d54`, and `FUN_0002aab0`
  - in both dynamic dispatch paths checked directly (`FUN_00023db4` and `FUN_0002a9bc`), the sequence is now stable:
    - resolve resource chain
    - call `0x1fc78` / store the returned cache key into resolved header `+0x0c`
    - call `FUN_0001fad4`
    - call `FUN_00032068`
  - practical consequence: the cache-key computation is not an isolated leaf; it feeds a larger post-key setup stage whose first stable boundary is `FUN_0001fad4`

- the post-key setup stage now has a stronger concrete shape:
  - `FUN_00031fe8` builds a raw `DispatchChainNodeV2` singly linked list and returns the head in `EAX`
  - callers immediately copy that returned head into `EDX`
  - callers then load a mode-like value into `EAX` (observed most clearly as `1` in multiple paths) and call `FUN_0001fad4`
  - `FUN_00032068` preserves `EAX` and `EDX` across its loop, calls `FUN_00032528`, and advances the current node through `[node + 0x04]`
  - `FUN_00032528` is now readable as a sorted insertion helper: it inserts the current node into the singly linked list anchored by the pointer passed in `EAX`, comparing `dwDispatch_value_10@0x10` first and then `nDelta_y_fixed16@0x0c` as the secondary key
  - practical consequence: the stable contract after cache-key generation is no longer just “call `FUN_0001fad4`, then `FUN_00032068`”; it is now “build raw chain -> select destination list-head slot -> normalize the chain into sorted order”
- `FUN_00032628` is not a generic helper; it resolves a resource header and derives an `(x, y)` extent/origin pair under flag control
- the helper reads the resolved resource dimensions from the packed header words and conditionally flips the derived extents when flag bits `0x10` and `0x20` are set
- this makes `DispatchBuildDescriptorV1.dwBuild_flags_04` meaningfully less opaque: at minimum it carries horizontal and vertical anchor or mirror bits that affect how the final node delta is measured from a resource-backed frame
- in `FUN_000326b0`, the resource-backed path now reads as: resolve cached record via `FUN_000328d8`, load base origin and segment from the resolved resource header, call `FUN_00032628` to derive the anchor-adjusted extents, then compute `nDelta_x_fixed16` and `nDelta_y_fixed16` as `(target - anchor_extent) << 16`
- the null-resource path remains the degenerate case: no base/header data is loaded and the target coordinates are written directly into the fixed16 deltas
- `FUN_00032678` reinforces this reading by calling `FUN_00032628` and then adding the node's existing fixed16 deltas back into the derived extents, which is exactly what we would expect from a helper that reconstructs a positioned point from anchor-relative offsets
- `FUN_0003275c` shows the same flag bits participating in node retargeting: if the resource handle or low-flag set changes, it recomputes the base/header fields and adjusts the existing deltas by the difference between the old and new anchor extents
- `FUN_000328d8` is not part of the chain topology; it behaves like a small resource-backed cache or registry used by the builder and by `FUN_00032820`
- `FUN_000326b0` preserves the resolved resource header pointer in `EDX`, passes the header dword at `+0x0c` into `FUN_000328d8`, stores the returned slot pointer at node `+0x28`, and then reads `nBase_x_30/nBase_y_34/nBase_segment_38` directly back from the preserved resource header
- this disassembly-backed flow means the old `pResolved_dispatch_rec` label at node `+0x28` is now misleading; the field is much closer to `pDispatch_cache_slot` than to a raw resolved resource pointer
- live Ghidra has now been updated to match that reading: `DispatchChainNodeV2 +0x28` is renamed to `pDispatch_cache_slot`, and `FUN_000326b0` decompiles with the named store `pDVar1->pDispatch_cache_slot = ...`
- `FUN_000328d8` maintains a four-entry table from `0x1ad8c` to `0x1adbc` with 16-byte slots; on hit it increments the slot use count at `+0x04`, and on miss it allocates or reorders slots using the maintenance helper `FUN_00032888`
- `FUN_00032888` is only called from `FUN_000328d8`, which supports treating this table as a dedicated dispatch-resource cache rather than a generic engine registry
- the remaining ambiguity is upstream of the slot store, not in the slot itself: both static callers of `FUN_00032820` (`0x28df2` and `0x2ab3a`) preload `EDX` with small constants (`0xe7` and `0xe4`) and load `ECX`/`EBX` from caller-local records at `+0x18/+0x14`, then funnel through the undefined helper at `0x1fc78` before entering `FUN_00032820`
- because `0x1fc78` is not a cleanly defined function boundary and its raw-byte disassembly is still noisy, keep the `FUN_00032820` entry-key semantics provisional even though the downstream cache-slot store is now established
- raw payload bytes confirm why this remains noisy: the call target at `0x1fc78` lands inside an overlapping instruction stream rather than at the head of a clean linear block, so normal disassembly around that address is not reliable enough to type directly
- even with that limitation, the callers agree on one important behavior: the value returned from `0x1fc78` is written to the resolved resource/header dword at `+0x0c` in both `FUN_00023db4` and `FUN_0002a9bc`
- that same header `+0x0c` dword is exactly what `FUN_000326b0` later passes into `FUN_000328d8`, which makes the best current interpretation of resource-header `+0x0c` a dispatch cache key or cache lookup token rather than a raw geometry field
- the static `FUN_00032820` callers fit the same model from the other side: after `0x1fc78` they preserve `EDX` as a small dispatch-kind literal and preserve caller-local `ECX`/`EBX` values from `+0x18/+0x14`, which `FUN_00032820` then threads into the newly built node alongside the cache-slot association

Current interpretation:

- `FUN_00031fe8` is not just a generic allocator; it is a dispatch-chain builder that normalizes one descriptor, builds the first node, then follows a linked resource-derived list to clone additional nodes with the same non-resource descriptor fields.
- `FUN_000326b0` is the per-node constructor for that descriptor.

Datatype application caveat (again confirmed here):

- sparse offsets through MCP `create_struct` compact unless explicit gap fields are modeled; `DispatchChainNodeV1` collapsed the intended offsets and was superseded by padded `DispatchChainNodeV2`
- `+0x88` is now named `dwDispatch_resource_selector`
  - `FUN_00038544` writes the incoming selector there and immediately calls `tinsel_resolve_resource_pointer`
- `+0x8c` is now named `dwDispatch_resource_selector_saved`
  - `FUN_00038544` uses it as a fallback/saved selector slot in the unresolved nonzero-`BL` internal paths

Mode-input evidence for `FUN_00038544`:

- the only direct callers currently identified are `FUN_00038658` (`0x38692`) and one noisy xref window at `0x3c9c8`
- both direct callsites clear `EBX` immediately before calling `FUN_00038544`:
  - `0x38690`: `XOR EBX,EBX`
  - `0x3c9c6`: `XOR EBX,EBX`
- no external xrefs were found to the interior branch targets at `0x3855c`, `0x38575`, or `0x385a4`; current evidence does not support a clean multi-entry public interface into those `BL == 1/2/3` paths
- practical consequence: keep `FUN_00038544` on the looser raw-pointer prototype for now, and treat the visible `BL` cases as unresolved internal control rather than a stable typed API boundary

Adjacent wrapper experiment:

- attempted owner-typed prototype on `FUN_00038658` validated syntactically but regressed the decompile into `in_EAX` storage artifacts because calling-convention inference stayed unstable
- rolled back `FUN_00038658` to its previous prototype; this wrapper is useful as evidence for `+0x70` wait/dispatch behavior but not yet as a stable typed boundary

Datatype application caveat:

- initial `create_struct` with a single field intended for offset `0x04` compacted that field to offset `0x00`
- corrected by modifying the live struct and adding explicit fields at `0x04/0x08/0x0c/0x10`; treat single-field sparse struct creation through MCP as needing layout verification with `get_struct_layout`

New machine-readable schema export:

- `outputs/dwb_payload_dump/dwb_dispatch_owner_crosswalk_v1.json`
  - freezes the current external-tool path as `wrapper -> DispatchCursorV1 -> ActorOwnerStateV1 -> actor`
  - records confidence and evidence addresses for each edge

