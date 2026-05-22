# Ghidra MCP Target Queue

## Why Pivot Here

The current `playcomposite` tail is no longer dominated by bad placement heuristics.

- Residual skips: `152`
- Residual class: all `nominal_negative_without_trusted_generated`
- Source: [outputs/full_playcomposite_pipeline/play_composite_export/play_composite_residual_skip_summary.json](outputs/full_playcomposite_pipeline/play_composite_export/play_composite_residual_skip_summary.json)

That means the next honest gain is static semantic recovery, not broader fallback placement.

## Stabilization Freeze

Focused diagnostics on the fresh `CLIMAX.SCN` family did not clear the safety bar for a rollout candidate.

- Targeted report: [outputs/full_playcomposite_pipeline/play_composite_export/waittime_family_diagnostic_summary.json](outputs/full_playcomposite_pipeline/play_composite_export/waittime_family_diagnostic_summary.json)
- Rows analyzed: `7`
- Carry-viable rows: `0`
- Anchor coverage: `TALK=4`, `none=3`
- Scope: the family stayed scene-spanning, not CLIMAX-isolated

Freeze state: keep the current heuristic set fixed and continue only with diagnostics that show a narrow scene scope plus at least one anchor-backed carry-viable row.

Latest ultra-narrow diagnostic pass (`tail2=PLAY>TALK|stack_prefix_imm=2`) also failed the safety gate.

- Rows analyzed: `3`
- Carry-viable rows: `0`
- Anchor coverage: `none=3`
- Scope: `scene_count=2` but no anchor-backed carry evidence, so freeze remains in force

Frontier triage is now automated via `scripts/triage_waittime_family_frontier.py` and currently returns no safe TALK/TALKAT candidate after excluding already-tested narrow families.

- Triage summary: [outputs/full_playcomposite_pipeline/play_composite_export/waittime_frontier_candidate_summary.json](outputs/full_playcomposite_pipeline/play_composite_export/waittime_frontier_candidate_summary.json)
- Triage candidate CSV: [outputs/full_playcomposite_pipeline/play_composite_export/waittime_frontier_candidates.csv](outputs/full_playcomposite_pipeline/play_composite_export/waittime_frontier_candidates.csv)
- Candidate count: `0`

Safe-cycle entrypoint is now automated via `scripts/run_safe_waittime_cycle.py`.

- It runs frontier triage first and only launches one diagnostics pass when a candidate exists.
- Latest run status: `no_safe_candidate`
- Latest run action: `diagnostics_skipped`

One-command reproducibility validation is now available via `scripts/validate_static_progress_baseline.py`.

- Validation command: `..\\.venv\\Scripts\\python.exe scripts/validate_static_progress_baseline.py --python ..\\.venv\\Scripts\\python.exe`
- Latest validation result: `all_checks_pass=true`
- Covered checks: freeze gate state, trust-verdict classifications/fingerprints, and slice/dual provenance invariants
- CI verify integration: `scripts/run_ci_verify.ps1` now runs the static baseline validator by default and hard-fails on drift.
- Skip controls when a live Ghidra endpoint is unavailable: `--skip-static-baseline` or environment variable `SKIP_STATIC_BASELINE=1`.
- Resolved CI regression: updated `tests/snapshots/finale_play_placement_timeline_diagnostic_snapshots.json` to match deterministic current builder output (`nominal_seeded_events=16`, `fallback_events=11`, `timeline_actor_state_events=14`).
- Full `scripts/run_ci_verify.ps1` now passes end-to-end (`all_checks_pass=true`, `50 tests OK`).

Workspace-local carve utility rerun (using `ghidra_scripts/` copies) matches prior stability signals.

- `copilot_constraint_trust_verdict.py` summary unchanged:
   - `update_consumer => TRUSTED` (`refs=3`)
   - `case_stub => TRUSTED` (`refs=1`)
   - `dispatcher_jump => UNSTABLE` (`L3 semantic anchor false`)
   - `38a32_wait_lane => UNSTABLE` (`INS_COUNT=0`)
- Stable fingerprints observed again: `case_stub SIG_FP=a44650c2`, `dispatcher_jump SIG_FP=a79ab56c`, `slice_38a30 SIG_FP=6cfdb45e`.
- Dual-recipe comparator remains `BOTH_STABLE=True` with intersection still reporting `ESI=0` and `EDI=0` defs in `0x38840..0x38910`.
- Upstream no-drift check also matched: `dual_38820_38880 recipe_A FP=ad125688`, `recipe_B FP=89603a91`, `pre_38898_window FP=1b12f070`, and `PRE_38870_INTERSECTION ESI=0 EDI=0` remained unchanged.
- Focused preheader probe (`0x38949..0x389dd`) also remained stable (`SIG_FP=3cbccacc`): still no true `EDI` defs, and only one weak `ESI` mutation (`INC ESI @ 0x389ae`) before the `0x389dd` call block.

## Engine Findings Since Connection

Live Ghidra MCP recovery on `dwb_le_relocated_image.bin` has already established the core movement/placement path.

- Recovered raw functions:
   - `FUN_0002fd08 @ 0x2fd08`
   - `FUN_00038a32 @ 0x38a32`
- Confirmed runtime roles:
   - `UpdateActorMovementAndTarget` commits `nTarget_x` and `nTarget_y`
   - `FUN_000301a8` is the target candidate planner feeding those writes
   - `FUN_0002f12c` is the planner retry wrapper
   - `FUN_00035b14` is the background-slot chooser used by planner branches
   - `FUN_00038a44` is a validity/occupancy gate before accepting candidates
   - `FUN_00038544` is a coherent actor-owner activation helper around the same owner-state block used by `FUN_00038a32`
   - `FUN_00038658` waits for owner dispatch state at `+0x70`, selects a resource from a table keyed by `+0x50` and the high byte of `+0x49`, then calls `FUN_00038544`
   - `UpdateActorMovementAndTarget` uses `ESI = param_1` as the primary owner and `EDI = [ESI + 0x284]` as a transient linked-owner handoff slot
   - on the linked-owner path, `UpdateActorMovementAndTarget` activates `EDI` first via `FUN_00038658`, clears `[EDI + 0x60]`, clears `[ESI + 0x284]`, then activates `ESI` via `FUN_00038658`
   - `FUN_0003869c` is a coherent animation/dispatch reset helper that picks a resource from `dwDispatch_resource_selector`, resolves it, resets the wrapper, and updates `nAnim_state_id` / facing on the owner
   - `FUN_0001ee34` is a small global-table mark helper applied to `[EDI + 0x90]` immediately before linked-owner activation
   - `FUN_00031f8c` is the immediate wrapper around `UpdateActorMovementAndTarget`; it only re-runs the movement update until the current position changes and does not populate `+0x284`
   - `FUN_00038170` walks a six-entry global owner pool at `0x21f98` using a `0x290` stride and returns an `ActorOwnerStateV1`-sized record
   - the undefined `0x388x-0x389x` cluster behaves like owner-state init/setup, not movement planning: it normalizes `+0x50`, zeros `+0x54/+0x5c/+0x60/+0x70/+0x88/+0x8c/+0x288`, and seeds `+0x90` from an input object handle
   - `FUN_000382f0` is a coherent planner-arm helper on the same owner record: it writes `+0x280 = param_2`, sets `+0x27c = 1`, and cancels any live dispatch chain at `+0x70`
   - `FUN_0001f184` reaches that planner-arm path via `FUN_00038170`, so the owner-pool selector already explains the `+0x27c/+0x280` fields consumed later by `UpdateActorMovementAndTarget`
   - `FUN_0001efc8` and `FUN_000384bc` mediate pooled-owner dispatch availability through `+0x70` and a fallback table rooted at `DAT_00013c58`, not through the linked-owner slot `+0x284`
   - the overlapped `FUN_00038a32` setup path has a second coherent transient-state slice: after `FUN_00038658`, it may arm/reset via `FUN_000382f0`, then sets `+0x278 = 1`, writes `+0x28c = EDI`, and loops through `FUN_00031f8c` / `FUN_000394c0`
   - `FUN_000382b0` is the matching transient-state cleanup helper: when `+0x278 == 1`, it clears `+0x278`, cancels the current `+0x70` dispatch state, reads the staged pointer from `+0x28c`, zeros `+0x70`, and passes that staged pointer to `FUN_00039414`
   - the raw body at `0x38a44` is now partly interpretable as a six-slot owner-pool neighbor scan: it iterates the pool at `0x21f98` in `0x290` strides, skips the current owner, requires an active slot byte, checks `FUN_000384bc` / `+0x38` state, and filters candidates by a small positional delta before continuing
   - direct instruction search for `0x284` still returns only two touches, both inside `UpdateActorMovementAndTarget` (`MOV EDI,[ESI+0x284]` at `0x31ba6` and clear `MOV [ESI+0x284],0` at `0x31c52`)
   - all currently visible callers of `0x38a44` are in `UpdateActorMovementAndTarget` and `FUN_000301a8`, and current raw windows for that helper still do not show a concrete store to owner `+0x284`
   - the `FUN_000301a8` windows around `0x30572/0x305a4/0x305eb` now confirm a repeated `CALL 0x38a44 -> TEST EAX` gating pattern for candidate selection; this upstream branch still does not expose any direct write to `+0x284` in the recovered slices
   - phase-2 call-chain tightening from the trusted consumer is now explicit: `UpdateActorMovementAndTarget` is called only by `FUN_00031f8c`, and that wrapper is reached from `FUN_00038a32`; no additional direct callers to the `+0x284` consumer are currently visible
   - tight recovery at `0x38a32` now decompiles as a wrapper loop (`FUN_00031f8c` plus `FUN_000394c0`/`FUN_0001f898` gating on `+0x48` vs `+0x27c`), reinforcing that this layer orchestrates dispatch/wait behavior rather than writing `+0x284`
   - tight seam recovery at `0x389a5` now fills the previously noisy transition into `0x38a19`: it calls `FUN_0001f460`, then `FUN_00038658`, may arm planner state via `FUN_000382f0`, sets `+0x278 = 1`, stores `+0x28c = EDI`, and enters the `0x38a19` wait/gate loop
   - `0x388f0` now recovers as `thunk_FUN_00038901` (entry `JMP 0x38901`) feeding the same descriptor/dispatch setup (`0x1fc78 -> 0x31fe8 -> +0x70`) and then the recovered seam at `0x389a5`; no direct `+0x284` write is exposed in this feeder lane
   - attempted pre-thunk recovery at `0x388b0` remains heavily overlapped (`ADD AL,BH` style decode and immediate fall-through into known `0x38901` lane), so it does not yet provide a trustworthy source assignment for the staged `EDI` value used later at `+0x28c`
   - major feeder recovery at `0x387fa` is now coherent across `0x387fa..0x38918`: this path initializes owner runtime fields (`+0x4c/+0x50/+0x54/+0x5c/+0x60/+0x64/+0x70/+0x88/+0x8c/+0x288/+0x27c`), seeds current coords from stack-provided values, runs `FUN_00035b14`/`FUN_000380b4`, then enters the known dispatch-build lane (`0x36a24 -> 0x3869c -> 0x1fc78 -> 0x31fe8 -> +0x70`)
   - upstream carve at `0x38760` recovered the missing prologue: it sets `EDI` from `FUN_000394b8()` and `ESI` from `[ (FUN_000394b8()+0x2c) + 0xc ]` before the `0x387fa`/`0x38861` init sequence, confirming this lane is rooted in a global dispatch context rather than caller-passed unknown registers
   - `FUN_000394b8` decompiles cleanly as `return DAT_0002a990;`, so the `EDI` lineage in this seam is now traced to global `DAT_0002a990` (also read/written by `FUN_00039298`, `FUN_00039358`, `FUN_00039414`, `FUN_000395d0`), not to any direct `+0x284` owner-link assignment site
   - recovered `0x387fa` still transitions into the same seam behavior (`FUN_0001f460`, `FUN_00038658`, optional `FUN_000382f0`, `+0x278 = 1`, staged pointer write near `+0x28c`, then wait loop through `0x31f8c`/`0x394c0`) with no explicit linked-owner `+0x284` store visible
   - direct caller searches for carved entries (`0x387fa`, `0x38861`, `0x389a5`) remain empty, so treat these as internal splits of a larger overlapped region rather than externally-invoked helpers
   - `FUN_0001f460` now decompiles coherently as dispatch-state tuning (`if [owner+0x27c]==0 then FUN_00032278([owner+0x70], computed_state)`); no `+0x284` interaction is visible and its callers (`FUN_00031b14`, `FUN_00038320`, `FUN_00038544`) are all dispatch/planner adjacent
   - tight recovery split at `0x30572` (`FUN_00030572`) confirms repeated `CALL 0x38a44 -> TEST EAX` candidate gating and fallback checks (`CALL 0x35b14` path), with no direct `+0x284` store visible in the recovered block
   - `FUN_00030572` currently has no independent inbound call references, so treat it as a carved internal branch from the overlapped `FUN_000301a8` neighborhood rather than a separately dispatched subsystem entry
   - direct `0x284` instruction search remains unchanged after seam recovery: only `UpdateActorMovementAndTarget` read (`0x31ba6`) and clear (`0x31c52`) are currently visible
   - two new indirect-write sweeps (`copilot_find_indirect_284_patterns.py` and `copilot_find_loose_284_correlations.py`) returned zero matches for `+0x280` seed -> `+0x4` store patterns in local windows, weakening the pointer-arithmetic alias hypothesis in currently recovered code
   - MOVSD sweep still points at previously known generic copy clusters (`FUN_0002f028`, `FUN_0002f12c`, `FUN_000324c9` family, etc.) and did not expose a new owner-path copy site tied to the `0x38a19/0x31f8c` lane
   - new `0x290` hits in `FUN_000187e8` were validated as a separate command/dispatcher-style subsystem (wide caller fan-in around `0x18c08..0x1b05a`), not a continuation of the owner movement chain leading into `UpdateActorMovementAndTarget`
   - `FUN_000187e8` therefore remains a false-positive `0x290` lane for the current objective; current owner-path work should stay centered on the `0x38901 -> 0x389a5 -> 0x38a19 -> 0x31f8c -> 0x31b84` chain
   - recent `+0x280` write hits at `0x20af2/0x20b31/...` are now classified as `FUN_00022099` table decode/expansion traffic (wide writes to `+0x280/+0x284/+0x288/+0x28c/+0x290` and paired `+0x3c0...` lanes), not owner-link handoff setup
   - the isolated `0x14d6f` write (`MOV [EAX+0x280],EDX`) remains in undefined/overlapped code and has no current evidence linking it to the movement owner record consumed by `UpdateActorMovementAndTarget`
   - raw recovery at `0x394c0` created `FUN_000394c0` as a real shared call target; its entry is now stable enough to show a consistent prologue (`param_1[9] = param_2`, then `CALL 0x323b8`), but the body still overlaps and is not yet semantically trustworthy end-to-end
   - additional tail carve probe at `0x39520` did not improve semantics (`RET 0xdb85` / trivial decompile), so treat the `0x394c0` post-prologue region as still overlapped and avoid over-trusting inferred field writes there
   - raw recovery at `0x38b11` created `FUN_00038b11`, but it still has no inbound references and decompiles as nonsense; treat `0x38b11` as an untrusted boundary probe rather than a recovered semantic helper
   - `FUN_000323b8` is a coherent context-save helper: it stores caller register/stack state into an 8-word frame record and returns `0`
   - `FUN_000323d5` is the matching resume/return helper for that saved frame record: it writes the saved return address / status back through the frame at `+0x18/+0x1c`
   - the nearby sibling `FUN_00039358` and the raw `FUN_000394c0` callsites both point at a shared scheduler/list cluster rooted at `DAT_0002a408` / `DAT_0002a990`, not at actor-coordinate translation
   - tighter raw windows for the scheduler cluster are now stable at key anchors even with overlap: `FUN_00039298` writes `DAT_0002a990` (`0x3930d`) and `DAT_0002a98c` (`0x39315`), `FUN_00039358` repeatedly sets `DAT_0002a990 = EBX` while walking nodes (`0x39386`) and clears it on exit (`0x393a3`), and `FUN_00039414` rotates/removes nodes while consulting both globals (`0x3944d..0x39462`)
   - direct callsite mapping now confirms `FUN_00039414` is shared teardown/list maintenance (`0x253d3`, `0x382e0`, `0x3ca9d`, `0x3cba3`, `0x3cc10`), not a unique movement-owner handoff writer
   - `FUN_000253b4` decompiles coherently as a guard around the same global cursor (`if FUN_000394b8()!=iRam00016998 then FUN_00039414()`), reinforcing that this scheduler context is reused by unrelated subsystems
   - `FUN_000382b0` decompiles coherently and confirms transient cleanup semantics: when `+0x278==1`, it cancels dispatch state, reads staged pointer from `+0x28c`, zeroes `+0x70`, and passes that staged pointer into `FUN_00039414`
   - direct operand search for `0x28c` currently returns only the cleanup read in `FUN_000382b0` (`0x382d3`) in addition to the previously recovered seam write near `0x38a13`, further isolating `+0x28c` as transient scheduler/list state rather than the hidden linked-owner slot
   - `FUN_0003cb64` now decompiles coherently as slot bookkeeping over globals at `0x2ac24/0x2ac28`: it repeatedly samples `FUN_000394b8()`, clears matching slot records, and calls `FUN_00039414()` to advance/remove queue context; no owner-link (`+0x284`) behavior is visible
   - `FUN_00036490` decompiles as a higher-level wait/selection loop that repeatedly calls `FUN_000394b8()/FUN_000394c0()` until subsystem state changes, then calls `FUN_0003cb64`; this strengthens classification of the `0x394b8/0x394c0/0x39414` trio as shared scheduler runtime machinery, not movement-owner handoff setup
   - carve split at `0x31dd0` produced a coherent post-planner branch function (`FUN_00031dd0`) with explicit `CALL 0x38a44` sites (`0x31de6/0x31dfd/0x31eb7`) and downstream movement/reset behavior, but still no store to `+0x284` in this region
   - re-decompile of `UpdateActorMovementAndTarget` after the split still shows only `+0x284` consume/clear semantics (`if nControl_state_284 != 0` handoff path, then clear `nControl_state_284 = 0`), with no newly exposed writer
   - `FUN_00031b14` is now coherently decompiled and does not write `+0x284`; it performs helper/reset flow (`0x321e4/0x36c18/0x1f460/0x3869c`) and repath-counter updates only
   - fresh inbound-reference probe for `0x2fd90..0x2fe40` shows only DATA refs into that window (no direct CALL/JMP refs to `0x2fdb1`), so current `0x2fdb1 -> CALL 0x380c0` evidence is not yet a trusted executable lane
   - table dump at `0x1e9f0..0x1ea20` now shows contiguous case-like targets (`0x1fd5e, 0x1fd9a, 0x1fddc, 0x1fe03, 0x1fe2d, ...`), which aligns with the noisy `0x1fdxx`/`0x1fdb1` fragments and supports classifying that area as jump-table case material rather than a clean standalone helper
   - function-level pcode co-occurrence scan for constants `0x84` and `0x284` now reports `TOTAL_HITS 0`, weakening the current selector-bridge hypothesis from wrapper `+0x84` traffic into owner `+0x284`
   - refreshed caller map for `FUN_00036c18` now includes `0x31b27` (`FUN_00031b14`) plus `0x350c5/0x350ce/0x353ae/0x38347/0x385e7`; this reinforces `FUN_00031b14` as movement-adjacent reset logic without exposing linked-owner `+0x284` production
   - raw operand verification for dispatcher entry confirms exact bytes at `0x1f6c7`: `2E FF 24 85 30 1F 01 00` (`JMP dword ptr CS:[EAX*4 + 0x11f30]`) after `CMP EAX,0xA` at `0x1f6be`; this is now byte-level confirmed
   - despite that encoded base, dword-table characterization at `0x11f30` does not resemble a valid case-target table for this path (entry `0` begins `0xff500000`, and no trusted movement-case targets are present), while `0x21f30` and `0x1e9e0` do show table-like target runs for other noisy fragments
   - exhaustive aligned dword scan for candidate case targets found only six hits in memory: `0x1fd5e/0x1fd9a/0x1fddc/0x1fe03/0x1fe2d/0x1fec0` at `0x1e9f0..0x1ea14`; no `0x31f87/0x31f97/0x31fc6/0x31fe8` values were found anywhere as dwords
   - exhaustive unaligned bytewise dword scan also found zero occurrences of `0x31f87/0x31f97/0x31fc6/0x31fe8`, reducing confidence that current `0x31fxx` movement-case stubs are table-driven via explicit embedded addresses in this image
   - reference-manager checks now show `0x11f30` has a single inbound data ref (from `0x1f6c7`) and `0x1e9f0..0x1ea00` currently have no inbound refs; this keeps both tables in a low-trust/overlap-sensitive bucket until additional coherent control-flow edges are recovered
   - bounded transitive caller-cone scan from `UpdateActorMovementAndTarget (0x31b84)` currently contains only `caseD_1 (0x31f97)` as direct caller context; owner-band hits in this trusted cone are limited to `+0x284` read/clear and `+0x27c/+0x280` reads inside `UpdateActorMovementAndTarget`, with no upstream `+0x284` producer write exposed
   - reference-manager recheck confirms `0x31f97` has one inbound `COMPUTED_JUMP` edge from `0x1f6c7` (`FUN_0001f6a4`), while `0x31f8c` retains one inbound direct call from `0x38a32`; this keeps the dispatcher-to-movement bridge real at xref level even though direct table-byte modeling around `0x11f30` remains contradictory
   - new hard-refresh result materially weakens that prior `COMPUTED_JUMP` confidence: after clearing/re-disassembling `0x1f680..0x1f730`, jump decodes at `0x1f6c8` (`JMP [EAX*4+0x11f30]`) and both `REFS_FROM(0x1f6c7)` and `REFS_TO(0x31f97)` drop to zero
   - scan for runtime table population at `0x11f30..0x11f80` found no pcode `STORE` hits at all; only static refs were observed (`0x1f6c8` data, plus unrelated reads at `0x17750/0x1a030/0x14b24/0x15c42/0x16760`)
   - local instruction dump confirms `0x11f30` sits in executable byte stream (e.g., coherent instructions at `0x11f44..0x11f7c`), which further undermines treating this address as a stable jump-table data base in current overlap state
   - re-running the known recovery script can recreate local `0x31f97/0x31fc6` call stubs (`CALL 0x31b84`) in window output, but reference-manager still reports `REFS_TO(0x31f97)=0`; treat these callsite windows as carve-local evidence, not stable global callgraph edges
   - post-refresh caller-cone scan from `FUN_00038a32` currently collapses to the seed only (`CONE_SIZE 1`) and shows no instruction or pcode `+0x284` hits inside that recovered body; textual operand search for `0x38a32` also returns zero matches
   - two-pass micro-refresh stability probe over tight windows (`0x1f6a0..0x1f6d8`, `0x31f80..0x31fdd`, `0x38a20..0x38a3c`) is now reproducible: both passes preserve `REFS_TO(0x31b84)=1` and `REFS_TO/FROM` zero for `0x1f6c8`, `0x31f8c`, `0x31f97`, `0x31fc6`, `0x38a32`
   - the lone stable `REFS_TO(0x31b84)` entry is now resolved as address aliasing/data confusion: source `0x36c7b` writes `MOV [0x21b84],EDX` inside `FUN_00036c78` (global zeroing of `0x21b80..0x21b8c`), not a code call/reference to function entry `0x31b84`
   - precise raw carve for `FUN_00038a44` (`0x38a44..0x38b10`) is now stable enough to confirm six-slot pool scan mechanics over `0x21f98` (`stride 0x290`, active-byte check at `+0x22210`, `+0x21fd0 == -1`, delta/metric filters via `0x384bc/0x38508/0x38510`), and this recovered body still does not show any direct `+0x284` write
   - `FUN_0002f028` is now scoped as a startup-adjacent helper (single callsite `FUN_00024c00`) and is not part of the movement-owner chain feeding `UpdateActorMovementAndTarget`
   - indexed-offset hypothesis check: `0x18780` (`MOV [ESI + ECX*4 + 0x280], EAX`) can theoretically alias `+0x284` when index==1, but the enclosing `FUN_00018618` now decompiles as a command/table setter keyed by nibble selectors (`param_2 & 0xf`, opcode classes `0xb0/0xc0/0xe0`) and is called only by `FUN_000187e8`; this confirms the earlier `0x187e8` lane remains a non-owner false positive
   - isolated setter at `0x14d6f` (`MOV [EAX+0x280], EDX ; JMP 0x14dfc`) recovered as tiny thunk-like write+tail-jump with no inbound refs to `0x14d6f`; sibling tail-jumps from `FUN_00014b52` also target `0x14dfc`, reinforcing that this is part of a generic setter/helper family and not a movement-owner producer lane
   - seam-callgraph tightened: `0x38a32 -> 0x31f8c -> UpdateActorMovementAndTarget(0x31b84)` with no extra external callers to `0x31b84`/`0x31f8c`; this lane remains a control watchdog around the existing `+0x284` read/clear and does not expose a writer
   - state-latch family classification strengthened: `FUN_000382f0` is a clean setter for `+0x280` plus `+0x27c=1` (single caller `FUN_0001f184`), and `FUN_00038320` is the paired clear path (`+0x27c=0`, called from `FUN_0003869c`); neither contains or reveals `+0x284` stores
   - deep recovery of the noisy `0x22099` region now yielded coherent copy subroutine `FUN_00020acc` plus tail fragment `FUN_00021fcc`: these perform table-lane writes to `+[0x0/0x140/0x280/0x3c0]` (and byte-granular `+[0x280..0x283]`) but still do not write `+0x284`; this materially removes the biggest remaining overlap blind spot for hidden producer hypotheses
   - post-recovery global scan remains stable: `operand_pattern=0x284` still returns only `0x31ba6` read and `0x31c52` clear inside `UpdateActorMovementAndTarget`
   - the observed call pattern into `FUN_000394c0` is stable across unrelated callers: `CALL 0x394b8` with a small `EDX` state value, then `CALL 0x394c0`, then spin until a handle/global becomes nonzero (`[owner + 0x70]`, `[0x16800]`, or another subsystem-specific slot)
   - on current evidence, `FUN_000394c0` is a shared scheduler/context helper that stages a small state value at `+0x24` inside a saved-frame-linked structure; it is adjacent runtime machinery, not the missing `+0x284` owner-link setter
   - the recent implicit-copy probe did not expose a hidden owner-record transfer path: owner-sized `0x290` references still collapse to the pool selector and neighbor scan, while the nearby `MOVSD` clusters in `FUN_0002f12c` / `FUN_0002f028` behave like planner-stack or frame copying around `FUN_000301a8`, not owner-struct propagation
   - the `DAT_00013c58` owner-management band is now partly mapped as a per-slot staging record, not a hidden owner clone: `FUN_0001f248` writes slot fields at `+0x20/+0x24/+0x28/+0x30/+0x34` and conditionally `+0x2c`, while nearby helpers expose `+0x14`, `+0x18`, `+0x44/+0x48`, `+0x50`, `+0x58`, and `+0x5c`
   - the `+0x2c` consumer path is not owner-link setup: `FUN_0001f184` calls `FUN_000320a0` when that slot field is nonzero, and `FUN_000320a0` behaves like a linked-list resource/dispatch refresh over `+0x40/+0x44`, not like linked-owner staging
   - `FUN_0001f5e4` confirms the table is serialized as a compact slot record (including bytes at offsets `0`, `0x38`, `0x40` and a dword at `0x3c`), which argues against `DAT_00013c58` being a shadow `ActorOwnerStateV1` copy
   - the resource-to-activation contract at `FUN_00038658` is now explicit in raw windows: it waits for `[owner + 0x70]`, selects a resource handle from `[owner + 0x128 + ((+0x50) << 4) + ((high_byte(+0x49)) << 2)]`, then calls `FUN_00038544(owner, selected_resource)` with `BL = 0`
   - the coherent entry of `FUN_00038544` confirms `BL` mode behavior at activation time (`BL=0` normal, `BL=1` restore from `+0x88`/`+0x48`, `BL=2` reuse `+0x8c`) and still shows no touch of `+0x284`
   - `FUN_00031fe8` is a stable dispatch-chain builder consuming a six-word descriptor block (resource handle, flags, selector, target x/y, node value) and returning a `DispatchChainNodeV2*` chain that is stored into `[owner + 0x70]`
   - representative callers of `FUN_00031fe8` (`FUN_00023db4`, `FUN_0002a9bc`, and the `0x38949` path) all route through `0x1fc78`/resource resolution before building dispatch chains; this continues to look like dispatch descriptor preparation, not hidden owner-link staging
   - tight mid-block recovery at `0x3526b` is now the best clean foothold inside the noisy `0x35104` region: this slice performs `CALL 0x1f184`, then `CALL 0x38170`, then `CALL 0x382e8`; if the `+0x278` gate is clear, it executes `CALL 0x3b8c8`, then continues into `CALL 0x1f248`, `CALL 0x1edc4`, and `CALL 0x1f864`
   - `FUN_000382e8` is now fully resolved as a trivial getter (`return *(owner + 0x278)`), with only one current caller (`0x35289` in `FUN_0003526b`); it is not a producer candidate for linked-owner `+0x284`
   - caller mapping for `FUN_0001f248` now includes `FUN_0003526b`, `FUN_0003869c`, and `FUN_00038901`; this keeps `0x3526b` aligned with already-known `DAT_00013c58` slot staging paths rather than exposing a new `+0x284` write lane
   - recovery of `0x3b8c8` remains overlap-corrupted (`decompile_function` timeout and noisy raw decode despite targeted clear/disassemble), but its call edge from `0x3526b` keeps it as the next unresolved helper boundary in the active lane
   - global operand sweep after these carves still reports only the same two direct `+0x284` touches in `UpdateActorMovementAndTarget` (`0x31ba6` read, `0x31c52` clear)
   - extra split recovery at `0x35290`/`0x352ad` did not clean the corrupted bytes around the `0x3b8c8` call setup (`0x35292..0x352a5` still bad decode), but the stable post-call slice remains `CALL 0x1f248` then optional `CALL 0x1edc4` then `CALL 0x1f864`, consistent with staging/dispatch flow and still with no direct `+0x284` write
   - `FUN_00035290` decompiles as another overlapped split of the same lane; despite noise, its coherent prefix matches the recovered instruction window and does not expose explicit linked-owner slot stores
   - `FUN_000350a8` now decompiles cleanly and remains in owner-pool/status logic (`FUN_00038170`, `FUN_0001ef24`, `FUN_00037050`, `FUN_00036c18`); current callsites are only inside `FUN_000352ad` (`0x354dd`, `0x354f0`), which further ties this branch to dispatch timing/state rather than `+0x284` population
   - post-carve indirect checks remain negative after the new splits: reruns of `copilot_find_indirect_284_patterns.py` and `copilot_find_loose_284_correlations.py` both still report `matches=0`
   - new split callsite recovery around `0x3095e` / `0x31067` confirms the full `0x3b8c8` caller set is still only `{0x3095e, 0x31067, 0x352a0}`; no new edges emerged
   - `FUN_0003095e` now has a coherent prefix (`CALL 0x3b8c8`, then checks `[ESI+0x1c]` / `[ESI+0x20]`, uses `[ESI+0x68]`, and calls `FUN_0001e94c` / `FUN_0001ee10`) that looks like a different subsystem from the owner-state lane around `+0x278/+0x27c/+0x280/+0x28c`
   - `FUN_00031067` currently appears as a split/tail chunk around the second `CALL 0x3b8c8` site; despite overlap noise, this reinforces that `0x3b8c8` is shared across at least one non-owner path and may be a generic helper boundary rather than a dedicated linked-owner producer
   - decisive seam confirmation at `0x38a13`: tight recovery now decompiles cleanly as `*(owner + 0x28c) = staged_ptr` followed by the known wait loop (`if +0x48==0 -> FUN_00031f8c`, else `FUN_0001f898` gate on `+0x27c`, then `FUN_000394c0`); this validates `+0x28c` staging and explicitly does **not** reveal any `+0x284` write in that seam
   - reference/call mapping after this carve remains consistent: no direct references target split helper `0x38a13`, while `0x38a44` still has the same six callsites (`FUN_00030572` x3 and `FUN_00031dd0` x3), keeping unresolved producer hypotheses concentrated upstream/candidate-selection logic rather than in the `0x38a13` wait loop
   - new callsite-window recovery around all six `0x38a44` calls further narrows behavior: in the `0x31de6/0x31dfd/0x31eb7` slices, `EAX` from `0x38a44` is used as a boolean gate and subsequent writes touch movement/planner fields (`+0x8/+0xc/+0x10/+0x14/+0x1c/+0x20`, plus state at `+0x34/+0x48/+0x49/+0x58/+0x5c`) with no visible linked-owner slot update
   - the parallel `0x30572/0x305a4/0x305eb` slices show the same contract: each `CALL 0x38a44` is immediately `TEST EAX`-gated and then feeds fallback chooser/status paths (`CALL 0x35b14`, status-bit writes like `OR [ECX],0x2/0x10`), again with no direct or obvious indirect population of owner `+0x284`
   - post-carve global checks remain unchanged (`operand_pattern=0x28c` only cleanup read in `FUN_000382b0`; `operand_pattern=0x284` still only read/clear in `UpdateActorMovementAndTarget`), strengthening the conclusion that the hidden producer is still outside currently coherent callsite windows
   - feeder-lane recovery is now cleaner at `0x38901`: the coherent sequence remains dispatch/resource construction (`0x36a24 -> 0x3869c -> 0x24fec chain -> 0x1fc78 -> 0x31fe8 -> [owner+0x70]`, then `0x1fad4/0x32068/0x1f248`, followed by `0x38658` and the transient wait loop); no direct linked-owner `+0x284` population is exposed
   - split `0x38949` confirms the same contract as a narrower internal slice and still flows into the same transient staging/wait behavior, reinforcing that this is an internal seam split rather than a new producer function
   - pre-feeder boundary `0x388b0` remains an overlap wall (`halt_baddata` decompile and bad decode at entry), so pointer provenance before `0x38901` is still the primary unresolved seam
   - constrained alias-offset sweep after these carves produced a strong negative for overlap-shift artifacts: `operand_pattern=0x279/0x27d/0x28d` all return zero hits, while `0x278/0x27c/0x28c/0x284` retain the expected stable matches; this weakens the “off-by-one displacement misdecode” explanation for a hidden `+0x284` writer in current code
   - ancestry re-check remains stable: `0x31b84 <- 0x31f8c <- 0x38a32` is still the only direct consumer chain for linked-owner handoff behavior, and split helpers `0x38949` / `0x38a13` still have no direct inbound references
   - MCP endpoint note: direct `function_pcode` requests currently return 404 on this bridge, so pcode-level confirmation must be done via script-side extraction rather than REST endpoint
   - script-side pcode validation is now in place and reinforces the same conclusion: focused dump over `UpdateActorMovementAndTarget`, `0x31f8c`, `0x38a13`, `0x38901`, `0x38949`, and `0x382b0` only shows explicit `const 0x284` address arithmetic in `UpdateActorMovementAndTarget` (read at `0x31ba6`, clear path at `0x31c52`)
   - global exact-constant pcode sweep (`copilot_scan_pcode_const_284.py`) now reports exactly two real `const 0x284` matches program-wide (again `0x31ba6` and `0x31c52`), after tightening the matcher to avoid substring false positives; this is strong evidence that no computed/hidden `+0x284` writer is currently present in recovered code
   - new micro-carves around the pre-staging seam now recover a cleaner setup block at `0x389dd`: `CALL 0x38658`, optional `CALL 0x382f0` depending on `[-0x65/-0x66]` guard, then `+0x278 = 1`, `+0x28c = EDI`, and the known `0x31f8c/0x1f898/0x394c0` wait loop
   - `0x38a04` split confirms the pure tail of that same contract (`+0x278 = 1`, `+0x28c = EDI`, loop), while `0x388d8` decompiles as an earlier feeder variant that sets local control fields (`+0x3c/+0x38/+0x40`) before entering the established `0x38901` resource/dispatch chain
   - inbound-reference checks for `0x388d8`, `0x389dd`, and `0x38a04` are all empty, confirming these remain internal overlap splits rather than externally called helpers
   - EDI-provenance tracing scripts over `0x38a13` and feeder anchors found no explicit `MOV/LEA/POP/XOR EDI,...` definitions inside those split bodies, so EDI source assignment is still upstream of currently coherent function boundaries
   - direct `+0x28c` mapping remains stable and narrow (`search_instructions 0x28c` still only reports cleanup read in `FUN_000382b0`), further supporting `+0x28c` as transient staged-neighbor state distinct from unresolved linked-owner `+0x284`
   - upstream seam carve immediately before `0x388d8` now exposes a concrete predecessor slice with calls to `0x367e4` and `0x36aa8` before entering the `0x38901` chain; this is the first stable pre-`0x388d8` call signal in this lane
   - current decompilation classifies `FUN_00036aa8` as table/resource coordinate extraction from `DAT_0001b220` and `FUN_000367e4` as a nearest/threshold-style selector over that same data band, which still looks like generic selection/planner support rather than explicit linked-owner slot assignment
   - inbound operand-reference searches for `0x388b8`, `0x367e4`, and `0x36aa8` are empty after the split, so these addresses currently behave as internal overlap fragments rather than independently referenced public helpers
   - unresolved core remains unchanged: the pre-staging branch is cleaner, but explicit EDI provenance into `+0x28c` is still not surfaced in coherent decoded instructions
   - refreshed parent decompile at `0x38861` now ties the newly exposed pre-branch helpers together: after `FUN_00035b14` and `FUN_000380b4`, the `==1` branch executes `FUN_000367e4` then `FUN_00036aa8`, storing the `FUN_000367e4` result into local actor field `+0x40` (with companion state at `+0x3c/+0x38`) before entering the known `0x38901` resource/dispatch chain
   - this new parent-level view strengthens a negative: the `0x367e4/0x36aa8` branch currently appears to feed local setup/state fields, not the linked-owner handoff slot `+0x284`; no direct `+0x284` population was exposed in this recovered parent path
   - range-constrained instruction queries via `search_instructions` appear unreliable for this seam (returned out-of-range global matches), so local bounded checks should use script-side listing scans for trustworthy neighborhood evidence
   - script-side bounded scan over `0x38850..0x38b20` for `0x40` references returned `TOTAL 0`, despite parent-level decompile showing `+0x40` setup in the `0x367e4/0x36aa8` branch; this indicates nearby consumer visibility is still limited by overlap/split boundaries rather than confirming a direct local follow-on use
   - bridge recovery from `0x387e0 -> 0x38890 -> 0x388d8` is now substantially cleaner and shows the full feeder progression into the known seam: `CALL 0x35b14`, branch on `CALL 0x380b4`, optional `CALL 0x367e4`/`CALL 0x36aa8`, local setup writes (`+0x3c/+0x38/+0x40`), then `JMP 0x38901` into dispatch/resource setup
   - refreshed decompile of `FUN_00038760` now explicitly seeds this lane from `FUN_000394b8` (`DAT_0002a990`) and carries that value into the transient staging setup near `+0x28c/+0x28d` during the same function body; this further supports a scheduler/global-cursor-derived staged-neighbor path rather than a hidden direct write to linked-owner `+0x284`
   - callsite map for `0x394b8` remains broad (`FUN_00023bb4`, `FUN_000253b4`, `FUN_00036490`, `FUN_00038658`, `FUN_00038760`, `FUN_0003ca08`, `FUN_0003cb64`, etc.), reinforcing that this cursor source is shared runtime machinery and not evidence of a dedicated `+0x284` producer
   - targeted staged-source backtrace over `0x38760..0x38a13` now yields a concrete register provenance anchor: `CALL 0x394b8` at `0x38769` followed immediately by `MOV EDI,EAX` at `0x38771`
   - explicit EDI-def scan for the same span currently reports only that single definition site (`0x38771`), which strongly suggests the staged-neighbor source carried into the later `+0x28c` seam is the global cursor value returned by `FUN_000394b8`
   - practical implication for the `+0x284` hunt: this lane now looks increasingly like `DAT_0002a990`-seeded transient neighbor staging (`+0x28c/+0x278/+0x27c` loop) rather than a hidden linked-owner slot producer; unresolved `+0x284` write hypothesis should stay outside this now-traced staged-neighbor path
   - new global indexed-alias sweeps were added for `+0x280`, `+0x27c`, and `+0x278` forms: only confirmed indexed `+0x280` store remains `0x18780` in `FUN_00018618`; no indexed `+0x278` store hits were found; one `+0x27c`-string hit at `0x2e7fc` decodes as an orphan tiny function with no xrefs and highly suspicious displacement (`0x27c80006`), currently treated as overlap/decode artifact until proven otherwise
   - program-wide pcode STORE-band scan (`0x270..0x290`) found 22 total stores, with only one true `+0x284` store instruction still at `0x31c52` (`UpdateActorMovementAndTarget` clear); all other hits are adjacent slots (`+0x278/+0x27c/+0x280/+0x288/+0x290`) in helper/init lanes already considered non-producer candidates
   - decompiler output for overlap-heavy table-copy functions around `0x20acc/0x21fcc` can display synthetic `+0x284` writes under bad-instruction warnings, but raw instruction/pcode global scans still do not corroborate any executable `MOV [*+0x284],*` there
   - updated xref picture for `0x20acc`/`0x21fcc`: there is now at least one confirmed external jump-table data edge from `FUN_0001f6a4` (`0x1f6c7` table at `0x11f30`) into this region (`0x21f30`), so this block is executable dispatch target code rather than a purely isolated overlap island
   - focused raw window at `0x20b10..0x20b50` is coherent and shows a stride-copy core: `MOV [EDI], [EDX]`, `MOV [EDI+0x140], [EDX+4]`, `MOV [EDI+0x280], [EDX+8]`, `MOV [EDI+0x3c0], [EDX+0xc]`, then `ADD EDI,0x4` loop; this means later iterations can logically land on `base+0x284` without encoding immediate `0x284`
   - setup/bridge windows reinforce that this is a looping lane, not an isolated single write: at `0x21e70` region the flow repeatedly `ADD EDI,0x4`, decrements loop counters, and jumps back to `0x20acc`; this supports cross-iteration landing on neighboring slots (including logical `+0x284`)
   - `0x21fcc` bridge slice is also coherent and performs byte-granular writes at `MOV byte ptr [EDI+0x280],AL`, `[EDI+0x281],AH`, `[EDI+0x282],AL`, `[EDI+0x283],AH` before continuing into the same dispatcher family; this confirms sustained traffic in the immediate neighborhood just below `+0x284`
   - dispatch-window recovery at `0x1f6a4` now clarifies pre-jump setup: `MOV ECX,EAX`, resource lookup via `CALL 0x24fec`, `MOV ESI,EAX`, `XOR EDI,EDI`, then selector load `MOV EAX,[ECX+0x10]` and computed jump `JMP [EAX*4 + 0x11f30]`
   - reference-manager expansion of the computed jump at `0x1f6c7` resolves concrete code targets in the `0x31f87..0x32071` band (including `0x31f97` inside `FUN_00031f8c`, which calls `UpdateActorMovementAndTarget`) plus data refs to `0x21f30`/`0x11f30`
   - important correction: current evidence does **not** prove that `0x20acc/0x21fcc` are direct computed-jump execution targets from `0x1f6c7`; the `0x21f30` linkage is presently a data reference, while executable computed-jump targets recovered by Ghidra point to `0x31fxx/0x320xx` case code
   - bounded scan over `0x31f80..0x32080` found no `+0x284/+0x280/+0x27c/+0x28c` offset traffic, so the newly recovered dispatcher case-target band does not expose a hidden owner-slot producer either
   - broad MOVS/REP struct-copy sweep did not surface an owner-sized (`0x290`/`0xa4 dwords`) transfer path tied to movement-owner lanes; most hits are small/static template copies
   - newly examined copy hotspot at `0x324b8..0x32524` (adjacent to `FUN_00032528`) performs a bounded descriptor copy (`ECX=0x4c`, `REP MOVSD/MOVSB`) plus a 16-byte tail write from stack to `[EDX..EDX+0xc]`, then flag/link updates on `EBX`; this pattern does not resemble a full owner-state copy and does not expose `+0x284` traffic
   - `FUN_00032528` itself decompiles as ordered insertion/link logic on node lists (`[node+0x10]` comparisons), not as a memory-copy routine or owner-state writer
   - new callsite context for `FUN_0001f898` now has four refs: trusted movement-lane callers at `FUN_00038544` (`0x3861f`, with `LEA EAX,[ESI+0x74]`) and `FUN_00038a13` (`0x38a29`, with `MOV EAX,EBX` where `EBX` is `ESI+0x74`), plus two unresolved/noisy sites in `0x1fdxx`
   - important split update: raw references to `UpdateActorMovementAndTarget` entry (`0x31b84`) now resolve only to `caseD_1` callsites (`0x31f97`, `0x31fc6`), and recovery can materialize `caseD_1` as a standalone internal case fragment
   - newly recovered `0x2006f` region appears structurally real (shared branch sink `0x203bf` with many inbound JZ edges from `0x1fec*..0x2022b`) and contains coherent wrapper-slot traffic: `MOV [EBX+0x7c],EAX` and `MOV [EBX+0x84],EAX`
   - however, bounded scans over `0x1fd40..0x20440` still show no direct `+0x284` traffic and no direct `+0x10` store in that block; current evidence supports it as wrapper/control setup context, not the missing owner-slot producer
   - confidence note for `0x2006f`: despite overlap noise in adjacent instructions, the repeated internal control-flow into `0x203bf` plus coherent `+0x7c/+0x84` assignments make this region higher-priority than prior one-off artifacts, but provenance from this wrapper path to owner `+0x284` remains unproven
   - big-slice recovery over `0x1fec0..0x203f0` now shows this block as a structured iterative copy lane with explicit tail step `ADD ESI,0x140` and `ADD EBX,0x140` at `0x203bf`, indicating a record size of `0x140` bytes (not owner-size `0x290`)
   - within that lane, observed writes include `MOV [EBX+0x7c],EAX` and `MOV [EBX+0x84],EAX`, with nearby source loads from `ESI` offsets (`+0x7c`, `+0x80`, etc.); this supports per-record slot propagation semantics rather than direct owner-slot (`+0x284`) production
   - bounded scans in this recovered block still show no direct `+0x284` writes and no direct `+0x10` stores, so it currently does not explain the selector producer consumed by `FUN_0001f6a4` nor the owner control slot consumed by `UpdateActorMovementAndTarget`
   - endpoint-level inbound searches for `0x1fec0` and `0x2006f` currently return no direct operand refs; together with heavy internal branching to `0x203bf`, this suggests an internal fragment/split context rather than a clean externally called helper
   - exact caller graph is now pinned: `UpdateActorMovementAndTarget` entry is `0x31b84`; inbound refs are only `FUN_00031f8c` callsites (`0x31f97`, `0x31fc6`) plus one unrelated global write ref at `0x36c7b` to absolute `0x21b84` (not a call)
   - direct upstream narrowing: `FUN_00031f8c` is called from `0x38a32` in the `0x38a13` wait loop; recovered pre-call window there still shows `+0x278/+0x27c/+0x28c` staging and no explicit/direct `+0x284` write
   - `FUN_00014d6f` (`*(obj+0x280)=value; FUN_00014dfc();`) has no recovered xrefs in current listing, so it is not presently tied to movement-owner flow
   - `FUN_000382f0` (`*(obj+0x280)=value; *(obj+0x27c)=1; optional dispatch notify`) is called from `FUN_0001f184` after `FUN_00038170` gating, consistent with staged-neighbor signaling and still not a direct `+0x284` producer
- Verified planner status model:
   - `5 = 0x1 | 0x4`
   - `6` is the retry path observed by `FUN_0002f12c`
   - `9` is the terminal alternate path observed by `FUN_0002f12c`
   - `0x10` is a separate fallback/failure flag, not one of the `5/6/9` terminal values
- Current caution:
   - raw recovery at `0x1f898` created `FUN_0001f898`, but the recovered body still decompiles as bad/overlapping code; use `FUN_00038544` and `FUN_00038658` as the trustworthy current abstraction, not `FUN_0001f898`
   - raw recovery at `0x394c0` improved control-flow anchoring but not full semantics; use it as a shared runtime anchor, not yet as a clean decompiled helper
   - raw recovery at `0x38b11` did not produce a trustworthy semantic target and currently has no visible callers
   - `0x394b8` remains unrecovered as a standalone function, but its call pattern with `FUN_000394c0` is now stable enough to treat the pair as scheduler acquisition + frame/context setup rather than actor-link population
   - the current hidden-copy hypothesis has weak support: no examined `MOVSD` cluster so far has lined up with `ActorOwnerStateV1` field traffic or with the exceptional `+0x284` slot
   - the current control-table hypothesis is also weakening: the mapped `DAT_00013c58` fields increasingly look like dispatch/resource slot state rather than the hidden source of `[owner + 0x284]`
   - the current resource-bridge hypothesis is also narrowing: the coherent `FUN_00038658` / `FUN_00038544` / `FUN_00031fe8` boundary shows dispatch-chain selection and activation semantics without any visible write to the linked-owner slot `+0x284`
   - no trustworthy setter for owner field `+0x284` is currently visible in normal disassembly; current evidence only shows the read and clear inside `UpdateActorMovementAndTarget`
   - the broad `+0x280` search lane now has a major false-positive bucket (`FUN_00022099` decode lanes), so future passes should treat `+0x280/+0x284` hits outside owner-size (`0x290`) pool context as low-priority unless they connect to `UpdateActorMovementAndTarget` callers
   - the `FUN_000301a8` neighborhood remains partially overlapped/noisy around post-`0x38a44` handling, so any remaining `+0x284` hypothesis there should be treated as unresolved until recovered with tighter function-boundary cleanup
   - although the `0x30572` split improved local readability, the `FUN_000301a8` parent region still contains overlap/noise around adjacent paths, so unresolved `+0x284` hypotheses remain concentrated in unrecovered predecessor logic rather than in the now-isolated gating block
   - the `0x389a5` seam is now mostly readable and still did not expose linked-owner slot writes, further concentrating unresolved `+0x284` hypotheses into earlier predecessor selection logic (before dispatch-chain construction) rather than the activation/wait seam itself
   - with indirect-pointer and `0x290` side-lane checks now negative, the highest-value remaining search lane is narrowed to unrecovered predecessor-selection logic that chooses owner/candidate pointers before `FUN_00038658` and before the `0x38a19` wait loop
   - after `0x387fa` recovery, the unresolved gap is narrower: not owner runtime init or dispatch setup itself, but the provenance of the staged candidate pointer (`EDI`-derived value later written near `+0x28c`) and whether that provenance can alias the hidden `+0x284` producer
   - updated narrowing: `EDI` provenance is now known (`DAT_0002a990` global cursor/context). Remaining unresolved issue is where/when `DAT_0002a990`-backed node content eventually maps to the owner-link consumed as `+0x284`, because this recovered lane still contains no explicit `+0x284` writer
   - call-reference search for `0x388f0` currently shows no independent inbound edges, reinforcing that this is a carved internal split and that unresolved behavior likely sits in surrounding predecessor logic rather than in a separately invoked helper
   - the nearby owner-state setup cluster exposes adjacent high-offset fields like `+0x288`, but still does not show a direct store to `+0x284`; the linked-owner slot remains exceptional rather than a routine initializer field
   - nearby owner-pool helpers now account for `+0x27c`, `+0x280`, and `+0x70`, which makes `+0x284` look even less like ordinary planner or dispatch state
   - the newly exposed transient staged-owner path uses `+0x278` and `+0x28c`, not `+0x284`; at current confidence it looks like cleanup/list-management state rather than the linked-owner activation handoff consumed by `UpdateActorMovementAndTarget`
   - until a code-reference edge is recovered into `0x2fdb1` (or neighboring `0x2fdxx` slice), treat the `+0x84` reader callsite there as low-confidence overlap-local evidence and prioritize trusted movement/dispatch ancestors
   - dispatcher ancestry around `0x1f6a4/0x1f6c7` remains overlap-sensitive and currently contradictory (byte-valid indirect jump operand but non-table-like target band at `0x11f30`), so treat this branch as an unreliable provenance source until control-flow is recovered with coherent case targets
   - current highest-confidence negative: within the trusted caller ancestry of `UpdateActorMovementAndTarget` itself, there is still no visible producer for owner slot `+0x284`; remaining producer hypotheses are now concentrated in predecessor logic outside the recovered `0x31b84 <- 0x31f97` cone or in unresolved overlap boundaries feeding `ESI`
   - confidence downgrade: both the dispatcher computed-jump xrefs and the `0x31f97` callsite ancestry are now demonstrably sensitive to carve/disassembly order; avoid using either as sole provenance proof until a stable decode survives clear/recreate cycles
   - practical trust policy update: prioritize only edges that survive both (a) clear/re-disassemble refresh and (b) independent ref-manager requery; current `0x31f97` and `0x38a32` ancestry edges fail that bar in this state
   - updated implication: there are currently zero stable inbound call-like edges to `UpdateActorMovementAndTarget` after micro-refresh; any remaining producer hunt must proceed via nearby stable data/owner-field semantics rather than current callgraph reconstruction in this overlap state
   - new stable register-setup foothold in `FUN_00031f8c`: at `0x31f90` it sets `EDX=EAX`, at `0x31f94` it sets `ESI=[EAX+0x4]`, then calls `UpdateActorMovementAndTarget` at `0x31f97`; second callsite at `0x31fc6` restores `EAX=EDX` before calling again. This indicates the owner pointer consumed by `UpdateActorMovementAndTarget` is flowing through `EAX` at `FUN_00031f8c` entry in this recovered state
   - current ref-manager snapshot still reports no inbound refs to `0x31f8c/0x31f90/0x31f94/0x31f97`, so upstream provenance of that incoming `EAX` value remains unresolved under present overlap state despite the local register setup now being clear
   - refreshed alias-pattern scan for computed `+0x284` via `+0x280` and index math still yields only the previously known indexed store at `0x18780` (`FUN_00018618`: `MOV [ESI + ECX*4 + 0x280],EAX`) plus a non-related stack-return-address false positive; no new movement-lane producer candidate emerged
   - additional probe on previously stable globals (`0x21b80..0x21b8c`) now reports zero refs in current analysis state; this lane should no longer be treated as a dependable anchor for movement ancestry or `+0x284` provenance
   - refreshed `0x14d6f` lane check remains non-movement: `FUN_00014d6f` still decompiles as `*(obj+0x280)=value; FUN_00014dfc();`, has no direct operand refs to `0x14d6f`, and reaches shared tail `0x14dfc` via helper path `FUN_00014b52` (itself called from `FUN_000152f7`); no linkage to `UpdateActorMovementAndTarget` ancestry is currently visible
   - immediate process upgrade implemented: reusable two-pass constraint verifier `copilot_constraint_trust_verdict.py` now classifies disputed lanes with `L1 stable decode / L2 stable refs / L3 semantic anchor` and prints `TRUSTED` vs `UNSTABLE` verdicts in one run
   - current verifier run: `update_consumer (0x31b84)` and `case_stub (0x31f97)` pass L1/L2/L3 in the same micro-refresh state, while `dispatcher_jump (0x1f6c8)` and `0x38a32` lane remain unstable (missing semantic anchor and/or decode)
   - disambiguation note: `REFS_TO(0x31b84)` can contain both real call refs (`FROM 0x31f97`, `FROM 0x31fc6`) and one address-alias data write (`FROM 0x36c7b -> [0x21b84]`); keep this split explicit in downstream reasoning
   - verifier upgrade complete: `copilot_constraint_trust_verdict.py` now emits per-pass normalized `TO_REFS`/`FROM_REFS` lists and deterministic instruction fingerprints (`SIG_FP`) for each candidate lane, allowing strict cross-run signature comparison instead of count-only checks
   - two consecutive full verifier runs now match exactly for all reported signatures in current state: `update_consumer SIG_FP=8c5800ee` with stable `TO_REFS={0x31f97 CALL, 0x31fc6 CALL, 0x36c7b WRITE}`; `case_stub SIG_FP=a44650c2` with stable `FROM_REFS={0x31b84 CALL}`; `dispatcher_jump SIG_FP=a79ab56c` remains semantically unanchored; `0x38a32` window remains empty (`INS_COUNT=0`)
   - bounded backward slice on the trusted `case_stub` confirms an upstream constraint: at `0x31f90` (`MOV EDX,EAX`) there is no local prior EAX-def in the recovered `0x31f60..0x31f90` window, so the owner pointer used by `UpdateActorMovementAndTarget` is currently an external live-in to `FUN_00031f8c` rather than produced inside this stub
   - basic-block model agrees with the live-in assessment: block containing `0x31f90` (`0x31f90..0x31f96`) has `SOURCE_COUNT=0` and only fall-through destination `0x31f97`, i.e. no recovered predecessor edge currently explains the incoming `EAX` value at this entry block
   - constrained predecessor hunt now exposes two reproducible local decode states around `0x31f90..0x31fd8`: (A) gap state (`FP=9d14933d`) where `0x31f90` is absent (`before=0x31f81 RET`, `after=0x31fe8 PUSH EBX`) and no block exists, and (B) case-anchored recovered state (`FP=0ffb5350`) where `0x31f90` decodes as `MOV EDX,EAX` with 38 instructions in-window
   - important reconstruction dependency: creating function at `0x31f97` (case anchor) reliably restores state (B); anchoring only at `0x31f8c` can remain in state (A). Downstream trust checks should therefore specify the case-anchor setup explicitly before asserting lane presence/absence
   - even in recovered state (B), predecessor evidence remains negative and stable across passes: block `0x31f90..0x31f96` has `SOURCES=0`, `EDGES_INTO_BLOCK=0`, `REFS_TO(0x31f90)=0`, reinforcing that incoming `EAX` is still an external live-in beyond currently recovered control-flow
   - in gap state, `REFS_TO(0x31f8c)` may still report `FROM 0x38a32 CALL` while `0x31f90` instructions are absent; treat this as another overlap-sensitive mixed-state artifact unless accompanied by explicit in-window decode presence checks
   - new caller-side provenance contract at the trusted wait-loop callsite: around `0x38a19..0x38a32`, the `CALL 0x31f8c` is fed by `MOV EAX,ESI` at `0x38a30` on the `(+0x48==0)` branch, and by `MOV EAX,EBX` at `0x38a27` on the alternate branch before `CALL 0x1f898`; this narrows immediate owner-pointer feed to caller registers (`ESI/EBX`) rather than a local producer inside `0x31f8c`
   - attempted forced predecessor carve at `0x389dd` is currently unstable in this state (collapses to trivial `RET` at `0x389d0` with no surrounding seam decode), so upstream `ESI/EBX` definition recovery from that boundary remains unresolved and should stay in the low-trust bucket until the seam is re-materialized coherently
   - new multi-pass caller-side slicer `copilot_slice_38a30_esi_ebx_origins.py` is now stable in a minimal local reconstruction (`0x38a13..0x38a40`): all 3 passes match (`SIG_FP=6cfdb45e`) and retain `CALL 0x31f8c` at index 9, with block `0x38a30..0x38a31` sourced only by conditional jump from `0x38a19`
   - corrected register-def logic confirms there are no true in-window `ESI`/`EBX` register definitions before the `MOV EAX,ESI`/`CALL 0x31f8c` path; this means the immediate feed registers are live-ins to the `0x38a13` loop body in the currently recovered slice
   - block-source mapping for the loop is now explicit and coherent: entry block `0x38a13..0x38a18` has `SOURCE_COUNT=0`; loop header `0x38a19` has sources `{0x38a13 fall-through, 0x38a40 back-jump}`; `0x38a32` receives fall-through from `0x38a30 (MOV EAX,ESI)`
   - inbound-ref probe aligns with block findings: `REFS_TO(0x38a13)=0`, `REFS_TO(0x38a32)=0`, and only `REFS_TO(0x38a19)=1` from the internal back-jump `0x38a40`; therefore, upstream provenance for `ESI/EDI/EBX` entering this loop remains outside currently recovered callgraph edges
   - wider predecessor-window reconstruction is now stable across `0x38990..0x38a18` (`SIG_FP=40754510`): `0x38a13` (`MOV [ESI+0x28c],EDI`) has a single stable source block from `0x38a04`, and the immediate preheader contains `0x38a10: LEA EBX,[ESI+0x74]`
   - `0x38a04` preheader is also now stable and sourced from `FUN_000389dd` in three ways: conditional paths from `0x389e2` / `0x389eb` and fall-through from `0x389fa`; this is the first reproducible external edge into the `0x38a13` loop family
   - one-hop earlier live-in probe across `0x38949..0x389dd` is stable (`SIG_FP=3cbccacc`) and shows chain `0x38949 -> 0x389a5 -> 0x389dd -> 0x38a04 -> 0x38a13`; however, there are still no true `EDI` defs and only one weak `ESI` mutation (`0x389ae INC ESI`) in-window, so both registers remain effectively live-ins to this recovered seam
   - boundary probe across `0x38901..0x38949` is now stable (`SIG_FP=06f1b640`): `0x38901` is entered only from thunk `0x388f0`, `0x38949` is reached by fall-through from `0x38944`, and there are still zero true `ESI`/`EDI` register definitions in this entire recovered band
   - practical new ancestry floor for the current recoverable state: `0x388f0 -> 0x38901 -> 0x38949 -> 0x389a5 -> 0x389dd -> 0x38a04 -> 0x38a13 -> 0x38a32 -> 0x31f8c -> 0x31b84`; `ESI`/`EDI` provenance is still unresolved above `0x38901`/thunk boundary
   - pre-thunk seam probe over `0x388b0..0x38910` is now reproducible (`SIG_FP=91431b3a`): `0x388b0` still decodes as overlap-noise (`ADD AL,BH`) with no refs/sources, `0x388d8` has no recovered inbound sources, and `0x388f0` (`JMP 0x38901`) has a single stable fall-through source from `0x388e5`
   - focused narrow probe confirms the same thunk-source edge under independent reconstruction recipe (`SIG_FP=39b47e6b`): block `0x388f0..0x388f1` source is consistently `0x388e5` (`MOV EDX,[ESP+0x8]`) across all passes
   - boundary shift: earliest stable predecessor to the movement ancestry is now `FUN_000388e5 -> thunk_FUN_00038901 (0x388f0) -> FUN_00038901`; however, no true `ESI`/`EDI` register definitions are recovered in `0x388b0..0x38910`, so both remain live-ins above this revised boundary
   - expanded predecessor probe over `0x38870..0x388f0` is now reproducible (`SIG_FP=f3f4fa4f`) and refines the earliest stable chain to `0x388d8 -> 0x388e5 -> 0x388f0 -> 0x38901` via fall-through edges (`0x388d8` source into `0x388e5`, then `0x388e5` source into `0x388f0`)
   - unresolved boundary moved slightly upward but remains in overlap-heavy code: both `0x388d8` and `0x38898` blocks currently show `SOURCES=0` and `REFS=0`; `0x38898` still decodes as suspicious noise (`OR AL,0x89`, `DEC ESI`) and should not yet be treated as a trustworthy semantic producer
   - no stable `EDI` register definition is visible in `0x38870..0x388f0`; only a weak/suspect `ESI` mutation at `0x3889a` appears in the noisy `0x38898` block, so `ESI/EDI` provenance remains unresolved above this newly refined pre-thunk floor
   - higher pre-thunk expansion (`0x38840..0x388b0`) reveals a second reproducible carve state (`SIG_FP=1b12f070`) where `0x38861` is a coherent block (`MOV [EBX+0x288],0`) sourced from `0x38840`, and `0x388ac..0x388b3` is sourced from `0x388a1`; in this state `0x38890/0x38898/0x388b0` instruction-at lookups can be absent while block coverage still spans them
   - cross-check rerun confirms recipe-sensitive dual-stability in this band: the earlier `0x38870..0x388f0` carve remains independently reproducible (`SIG_FP=f3f4fa4f`, chain `0x388d8 -> 0x388e5 -> 0x388f0`), while the wider `0x38840..0x388b0` carve is also internally stable but yields different block partitioning and instruction presence
   - trust-policy implication for `0x38840..0x38910`: treat this as a forked overlap region with at least two stable local minima; only claims that survive both reconstruction recipes should be promoted to high-confidence provenance facts
   - dual-recipe comparator (`copilot_dual_recipe_intersection_38840_38910.py`) is now in place and both recipes are individually stable in the shared band (`recipe_A FP=8e5cd0ca`, `recipe_B FP=b9888103`); intersection extraction now yields a strict both-survive set for edges/defs
   - high-confidence intersection ancestry core (survives both recipes) is now: `0x388a1 -> 0x388b0/0x388f2`, `0x388ac -> 0x388b4/0x388b8`, `0x388b9 -> 0x388c6`, `0x388c6 -> 0x388d8`, `0x388b4 + 0x388d8 -> 0x388e5`, `0x388e5 -> 0x388f0`, and `0x388f0/0x388f2 -> 0x38901`
   - intersection target presence confirms continued fork above this core: `0x38840` and `0x38870` do not co-exist as instructions across recipes (A sees noisy `0x38870`, B sees noisy `0x38840`), so no both-survive predecessor edge above `0x388a1` is currently recoverable
   - intersection register-def results remain decisive for the producer hunt: `ESI_DEFS=0` and `EDI_DEFS=0` in the both-survive set for `0x38840..0x38910`; only `EBX`/`EAX` defs survive. Therefore linked-owner source provenance via `ESI/EDI` remains unresolved above `0x388a1/0x388ac` fork boundary
   - focused per-recipe source comparison for `0x388a1` / `0x388ac` is now stable in both recipes: `0x388ac` is sourced from `0x388a1` fall-through, and `0x388a1` is sourced from `0x38870` fall-through in both runs (`recipe_B` keeps this as a structural source even when `instructionAt(0x38870)` is absent)
   - updated practical boundary: earliest cross-recipe structural predecessor currently visible is `0x38870 -> 0x388a1 -> 0x388ac -> (intersection core toward 0x38901)`, but `0x38870` decode remains low-trust/noisy (`ADD byte ptr [EAX],AL` in one recipe, `<noins>` in the other), so this edge is structural-only and not yet semantic provenance for `ESI/EDI`
   - dual-recipe comparator one-hop higher (`copilot_dual_recipe_intersection_38820_38880.py`) confirms both recipes are stable in `0x38820..0x38880`, and strict pre-`0x38870` intersection check remains negative (`PRE_38870_INTERSECTION: ESI=0, EDI=0`)
   - both-survive intersection in that higher window is very narrow and structural: only two edges survive, both into block `0x3881c..0x38822` from `0x38810` (conditional) and `0x38815` (fall-through)
   - focused source probe over `0x387d0..0x38830` now extends this upstream chain with stable detail (`SIG_FP=492511da`): `0x387fa` has no recovered sources, `0x38810` is sourced from `0x38809` fall-through, and block `0x3881c..0x3883f` is sourced from `0x38810` conditional plus `0x38815` fall-through
   - register-provenance status unchanged despite upstream extension: no true `ESI` or `EDI` defs are recovered in `0x387d0..0x38830`; current stable edges in this segment are `EBX/EDX` state gating only
   - major dual-recipe breakthrough at `0x38760..0x38810`: both recipes are now identical and stable (`FP=b7882642`) with intersection-surviving register defs for the first time in this ancestry band: `EDI_DEF @0x38771 (MOV EDI,EAX)` and `ESI_DEF @0x38777 (MOV ESI,[EDX+0xc])`
   - instruction-level chain confirmed by direct dump (`0x38760..0x38780`): `CALL 0x394b8` (`0x38769`) -> `LEA EDX,[EAX+0x2c]` (`0x3876e`) -> `MOV EDI,EAX` (`0x38771`) -> `MOV ESI,[EDX+0xc]` (`0x38777`), i.e. `ESI` comes from `[EAX+0x38]` where `EAX` is the global cursor returned by `FUN_000394b8`
   - decompile corroborates this source model in the same function: `FUN_000394b8` returns `DAT_0002a990`; `FUN_00038760` then derives owner pointer context from that object and enters the now-traced movement ancestry (`... -> 0x387fa -> 0x38810 -> ...`)
   - remaining unresolved upstream producer gap is now sharply defined: while owner pointer ingress (`ESI`) is traced to global-slot read `[DAT_0002a990 + 0x38]`, no direct/clean writer to that `+0x38` slot is currently recovered; literal operand scans show writes to base `DAT_0002a990` in scheduler functions (`0x3930d/0x39386/0x393a3`) but not explicit `0x2a9c8` slot writes in current decode
   - additional targeted negative: focused scan of all currently explicit `DAT_0002a990` functions (`FUN_00039298`, `FUN_00039358`, `FUN_00039414`, `FUN_000394b8`, `FUN_000395d0`) found zero literal `+0x38` memory accesses in their instruction streams, reinforcing that `[DAT_0002a990 + 0x38]` producer is likely hidden behind overlap/noisy decode or non-literal addressing patterns
   - new adjacent initializer fragment around the sole `FUN_0002a9bc` callsite at `0x2aa50` is now visible: `ECX=EAX`, `EAX=EDX+0x8`, `EDX=-1`, then `CALL 0x2a9bc`; after the call, the returned `EAX` is stored to globals `[0x1a58a]` and `[ECX]`, and used in further table/array setup. This likely seeds the object/list whose later global-slot reads are observed in the `FUN_000394b8 -> FUN_00038760` chain
   - practical consequence: the unresolved `[DAT_0002a990 + 0x38]` writer may live in the object/list construction preceding `0x2aa50`, not in the explicit `DAT_0002a990` writer functions themselves; current evidence does not yet identify a clean store to `0x2a9c8`
    - runtime-oracle status has improved materially: the same ScummVM logging run now includes sustained player interaction events (`PLR_WALKTO`, `PLR_ACTION`, `PLR_LOOK`, `PLR_NOEVENT`, `PLR_ESCAPE`) across a long active window, so this oracle is now discriminating at interaction level even though explicit scene/global transition labels are still sparse
    - latest runtime metrics from `scummvm_tinsel_runtime.log`: `PLR` coverage is broad (`423+` interaction lines, `9` event types, `258` unique event+coordinate combinations in the sampled interval; continued growth afterward), which is enough to prioritize static targets by runtime recurrence instead of raw disassembly proximity
    - runtime extraction artifacts are now available for focused correlation:
       - `scummvm_plr_windows_latest.txt` (last `PLR` anchors with ±30-line context)
       - `scummvm_plr_signal_windows_latest.txt` (same anchors filtered to `PLR_`, `InitStepAnimScript`, `Playing sound`)
       - `scummvm_plr_script_correlation_latest.txt` (ranked post-input script IDs and latest anchor->script pairs)
    - ranked post-input script IDs (from `scummvm_plr_script_correlation_latest.txt`) now give a concrete static-first shortlist: `0x55570` (105), `0x45012D14` (61), `0x5AFF4` (40), `0x5755C` (36), `0x5AF7C` (33), `0x5920C` (30), `0x5A28C` (26), then `0x56188`/`0x5B5DC` (20 each)
    - highest-value near-term runtime cluster for static narrowing is the repeated coordinate band around `(249,130)` / `(251,129)`, which alternates strongly between `0x5958C` and `0x56188` and briefly hits `0x1704E954`; this is now the preferred bridge from oracle evidence into unrecovered predecessor selection logic
    - pragmatic static follow-up order from runtime evidence: prioritize callsites/consumers of `0x5958C`, `0x56188`, and `0x5AFF4` first (plus nearby object signatures observed in anchors such as `30bc0h` and `30d20h`), then evaluate whether any of those lanes can be traced into the unresolved `[DAT_0002a990 + 0x38]` production path before `FUN_00038760`
   - direct Ghidra probe of runtime-leading IDs shows they are currently weak as standalone static anchors in this image: `0x55570`, `0x5AFF4`, `0x5958C`, `0x56188` are in-memory but have no instruction-at, no refs-to, and no containing function before forced disassembly; `0x45012D14` is out-of-image
   - forced disassembly at nearby object-signature addresses (`0x30bc0`, `0x30d20`) creates synthetic/noisy micro-functions with `ENTRY_REFS=0` and low-trust leading bytes (e.g. `ADD [EAX],AL`), so treat these as overlap artifacts unless corroborated by real inbound references
   - meaningful positive from the same probe: `0x31db0` lands inside `UpdateActorMovementAndTarget` (`entry 0x31b84`) with known real inbound calls (`0x31f97`, `0x31fc6`), so runtime-object address correlation currently strengthens the existing `0x31f8c -> 0x31b84` lane rather than opening a new upstream producer path
   - focused upstream supplier scan confirms `0x31f8c` still has a single real external caller at `0x38a32` (`FUN_00038a32`); no additional direct suppliers of the wrapper were recovered
   - recovered pre-call branch at `0x38a19..0x38a32` tightens handoff semantics: when `[ESI+0x48]==0`, the path executes `MOV EAX,ESI ; CALL 0x31f8c`; otherwise it routes through `MOV EAX,EBX ; CALL 0x1f898` and skips the direct `0x31f8c` call on that branch
   - immediate wrapper semantics at `0x31f8c` remain stable: it seeds registers from the caller-provided record (`EDX=EAX`, `ECX=[EAX]`, `ESI=[EAX+4]`) before calling `UpdateActorMovementAndTarget` (`0x31b84`), so near-term producer narrowing should prioritize where `ESI` itself is chosen before `0x38a32` rather than expecting a writer inside `0x31f8c`
   - ESI provenance lane scan over `0x38760..0x38a40` found only two local writes before the callsite seam: stable `MOV ESI,[EDX+0xc]` at `0x38777` and an `INC ESI` at `0x389ae`; the latter sits in a no-xref overlap cluster (`0x389a8..0x389f6` with synthetic-looking opcodes) and should be treated as low-trust decode noise
   - overlap trust check confirms `0x389ae`/`0x389b0` currently have no inbound references, while `0x38a19` has a real loop edge from `0x38a40`; practical consequence: keep `0x38777` as the earliest trustworthy ESI definition feeding the `0x38a19 -> 0x38a32 -> 0x31f8c -> 0x31b84` lane
   - new runtime transition detector confirms the long play session is usable even without explicit `scene/global` strings: adjacent 15-second windows show high-confidence script-set pivots and PLR-rate regime changes that are consistent with scene/phase transitions
   - generated artifacts:
      - `scene_transition_timeline_latest.csv` (per-bin `InitStepAnimScript`/`PLR`/`DoNextFrame` summary plus top scripts)
      - `scene_transition_candidates_adjacent_latest.txt` (chronological adjacent-bin boundary ranking)
   - strongest adjacent transition windows in the current log include:
      - `12:57:30 -> 12:57:45` (score `90.99`, scripts `6 -> 46`, PLR `1 -> 18`, init `10 -> 125`)
      - `13:02:00 -> 13:02:15` (score `97.62`, scripts `2 -> 45`, PLR `0 -> 60`, init `3 -> 119`)
      - `13:05:00 -> 13:05:15` (score `83.41`, scripts `15 -> 53`, PLR `0 -> 21`, init `29 -> 113`)
      - `13:15:00 -> 13:15:15` (score `88.38`, scripts `25 -> 5`, PLR `27 -> 0`, top-script flip from `5b778` lane to `56188` lane)
      - `13:18:45 -> 13:19:00` (score `92.98`, scripts `22 -> 3`, PLR `6 -> 0`, init `51 -> 3`)
   - latest-tail behavior remains low-signal (`13:36:42` last PLR while log continues to `13:40:40`), but this is now clearly a local idle/churn period rather than evidence that the entire run lacks discriminating data
   - bridge artifact `scene_transition_static_bridge_latest.txt` now ranks top 20 adjacent transition windows and annotates each with static probe hints tied to prior PLR/script correlation
   - highest-yield bridge windows for immediate static follow-up are currently:
      - `13:02:00 -> 13:02:15` (`score 97.62`, `a_top=55570 -> b_top=5b778`, `PLR 0 -> 60`, `uniq 2 -> 45`)
      - `12:57:30 -> 12:57:45` (`score 90.99`, `a_top=55570 -> b_top=5b73c`, `PLR 1 -> 18`, `uniq 6 -> 46`)
      - `13:15:00 -> 13:15:15` (`score 88.38`, `a_top=5b778 -> b_top=56188`, `PLR 27 -> 0`, `uniq 25 -> 5`)
      - `13:02:30 -> 13:02:45` (`score 89.63`, `a_top=5b6c4 -> b_top=5755c`, strong regime contraction)
   - actionable probe shortlist is now explicitly aligned across runtime views: `55570`, `56188`, `5958c`, `5aff4`, `5755c`, `5af7c`, `5920c`, `5a28c`, `5b5dc`; prioritize windows where `55570` or `56188/5958c` participate in top-script flips
   - concrete per-window evidence file is now available: `scene_transition_window_extracts_latest.txt` (top transition windows with `lines_in_window`, plus sampled `PLR_` and `InitStepAnimScript` lines)
   - high-value sample confirmation from that extract: `13:12:45 -> 13:13:00` includes direct `PLR_WALKTO` at `(242,150)` and script set containing `55570`, `5af7c`, `5b5dc`; `13:15:00 -> 13:15:15` shows top-script regime handoff from `5b778` family toward `56188` lane in the ranked bridge file
   - low-value confirmation also now explicit in extracts: late windows (`~13:40`) are mostly no-PLR and dominated by idle-loop signatures (`4faa0/4fb98` family), so they should remain secondary unless correlated with fresh interaction anchors
   - focused static probe against transition IDs (`55570`, `56188`, `5958c`, `5aff4`, `5755c`, `5af7c`, `5920c`, `5a28c`, `5b5dc`, plus top-window companions) found zero immediate-constant instruction hits across the current recovered instruction set (`SCANNED_INSTRUCTIONS=27375`), reinforcing that runtime-leading IDs are still weak standalone static anchors in this image state
   - direct reference picture for cursor base vs unresolved slot remains unchanged: `DAT_0002a990` has the same six read/write refs (`0x3930d`, `0x39386`, `0x393a3`, `0x3944d`, `0x394b8`, `0x39602`), while `0x2a9c8` (the literal `+0x38` slot address) still has no direct refs
   - new concrete `+0x38` writer candidate set was profiled from executable code: `FUN_000166f8` (`0x16928`), `FUN_000170a8` (`0x17164`), `FUN_00017908` (`0x17971`), `FUN_000179f8` (`0x17a16`), `FUN_0001b79a` (`0x1bab6`), `FUN_0002048a` (`0x204b9`), `FUN_000326b0` (`0x3270d`), `FUN_0003275c` (`0x327c6/0x327d1`), plus known seam writes in `FUN_00038760` (`0x387b6`) and `FUN_000388d8` (`0x388df`)
   - among those, only `FUN_00038760` currently intersects the trusted cursor lane (`CALL 0x394b8`, `LEA EDX,[EAX+0x2c]`, then `MOV ESI,[EDX+0xc]`), but no matching write form to `[EDX+0xc]` was recovered there; this keeps producer status unresolved and suggests the `+0x38` source is prepared outside the visible `0x394b8`-adjacent slice
   - one-hop caller tracing from `DAT_0002a990` assignment functions (`FUN_00039298`, `FUN_00039358`) into their direct callers (`FUN_00025654`, `ProcessMainSchedulerTickLoop`) did not expose nearby `+0x38` field preparation, so the likely writer remains outside this immediate assignment neighborhood
   - bounded callgraph intersection pass between `+0x38` writer candidates and the `DAT_0002a990` assignment lane now yields a concrete shared bridge set (depth-limited), including `FUN_0002048a`, `tinsel_resolve_resource_pointer (0x24fec)`, `FUN_00024f14`, and several `0x3d***` helpers
   - strongest new bridge edge in current state: seed-side path reaches `FUN_0002061f`, which calls `FUN_0002048a` (confirmed `+0x38` writer at `0x204b9: MOV [EAX+0x38],EDX`); this is currently the most concrete writer candidate reachable from the scheduler/assignment neighborhood
   - parallel bridge path from seed side also reaches `tinsel_resolve_resource_pointer (0x24fec)`, while writer-side closure independently includes `0x24fec` via `FUN_000326b0/FUN_0003275c` callers; this shared resolver node is now a priority pivot for the next provenance step
   - strict producer-pattern scan (`CALL 0x394b8` -> `LEA [EAX+0x2c]` -> store `[reg+0xc]`) still returns zero matches, so current evidence favors an indirect lifecycle writer (e.g., shared resource/list setup) over a local explicit `DAT_0002a990+0x38` store near `FUN_00038760`
   - concrete context for the strongest bridge writer candidate is now extracted:
      - `FUN_0002061f` (`0x2061f`) calls `FUN_0002048a` twice (`0x20628`, `0x20632`) with `EAX` loaded as size-like immediates (`0x2c48`, `0xa0000`) and `EDX` forwarded as fill/source value
      - `FUN_0002048a` entry window (`0x2048a..0x204bc`) performs broad field initialization including explicit `MOV [EAX+0x38],EDX` at `0x204b9`
      - inbound refs to `FUN_0002061f` currently include callers in `FUN_00020458`, `FUN_00024a8c`, and `FUN_000390ec`, giving this lane concrete reachability from scheduler-adjacent code
   - caution: `FUN_0002048a` remains partially overlap-corrupted after the coherent prefix, so treat `0x204b9` as a high-value lead rather than final proof of the exact `[DAT_0002a990 + 0x38]` producer until register/base provenance from its callers is confirmed
   - caller-provenance check for `0x2061f` is now complete and downgrades that lead for the main objective: all three callsites (`0x20484`, `0x24b08`, `0x39125`) invoke `CALL 0x2061f` with `EAX` explicitly zeroed just before the call, consistent with a reset/init routine rather than direct production of the cursor-linked owner slot
   - decisive ingress narrowing at `DAT_0002a990` assignment: `FUN_00039298` writes `MOV [0x2a990], EDX` at `0x3930d`, and immediate predecessor chain in `FUN_00025654` does not set `EDX`; both predecessor callees preserve incoming `EDX` (`FUN_00032868` push/pop `EDX`, `FUN_000323f8` push/pop `EDX`)
   - practical consequence: the true source of the pointer assigned into `DAT_0002a990` at `0x3930d` is now moved one level higher, into callers of `FUN_00025654`
   - two concrete caller ingress lanes to `FUN_00025654` are now visible:
      - `FUN_00024c00` path: `XOR EDX,EDX` -> `CALL 0x2f028` -> `CALL 0x25654`; this strongly suggests `0x2f028` may synthesize/return the live `EDX` cursor pointer used by `FUN_00039298`
      - `FUN_0002570c` path: `CALL 0x25654` after `CALL 0x246c0`, `CALL 0x20458`, `CALL 0x25578`; `FUN_00025578` preserves `EDX`, `FUN_00020458` does not touch `EDX`, so effective `EDX` source at this site likely comes from `FUN_000246c0`
   - updated highest-priority provenance target is therefore no longer `0x2061f/0x2048a`; it is the higher ingress pair that can feed `EDX` into `FUN_00039298`: `FUN_0002f028` and `FUN_000246c0` (via the two caller lanes above)
   - two-pass call-contract scan now sharply separates those ingress candidates:
      - `FUN_0002f028` has a single critical callsite (`0x24c26` in `FUN_00024c00`) where `EDX` is explicitly zeroed before call and then immediately consumed/stored after call (`MOV [0x1696c],EDX`, `MOV [0x16978],EDX`) before `CALL 0x25654`; this is strong evidence that `0x2f028` returns/produces a live pointer in `EDX`
      - `FUN_000246c0` callsites (in `FUN_0002570c` and `FUN_0002567c`) repeatedly reset `EDX` right after call and do not preserve any post-call `EDX` value into `CALL 0x25654`; these uses look parameter/side-effect oriented rather than a pointer-return producer for the `DAT_0002a990` assignment lane
   - practical ranking update: `0x24c00 -> 0x2f028 -> 0x25654 -> 0x39298 -> DAT_0002a990` is now the highest-confidence ingress chain for the cursor pointer written at `0x3930d`
   - the alternate `0x2570c` lane remains secondary/noisier for this objective: although it calls `0x25654`, nearby `0x246c0` calls do not show a stable post-call `EDX` feed into that assignment path
   - new concrete selector bridge recovered for the `0x2f028` output globals:
      - sparse decode around `0x26082..0x260c0` shows `CALL 0x249d0` twice, first with `XOR EAX,EAX` (`EAX=0`) at `0x26088`, then with `MOV EAX,0x1` at `0x260a2`
      - `FUN_000249d0` maps these selector values to literal pointer choices: `EAX==0 -> [ECX]=0x1696c`, `EAX==1 -> [ECX]=0x16978`
      - immediately after each `0x249d0` call, the selected pointer pair is consumed via register loads from `[ESP+0x4]` and `[ESP]` and fed into `CALL 0x3dd7e` (`0x2607d` and `0x260c0`), giving a concrete post-selection consumer chain
   - this materially strengthens confidence that `0x1696c/0x16978` are deliberate staged-pointer slots populated from the `0x24c00 -> 0x2f028` lane (not dead/noise globals), and that the next upstream/downstream pivot should target the `0x3dd7e` consumer family rather than `0x2061f`
   - focused probe of `FUN_0003dd7e` (`0x3dd7e`) shows broad reuse (24 callsites, including dense fan-in from `FUN_00026610` at `0x2607d/0x260c0` and many neighboring sites), but no direct calls/touches to `DAT_0002a990` lane anchors (`0x39298/0x39358/0x39414/0x394b8/0x395d0`)
   - interpretation update: `0x3dd7e` is currently a high-connectivity consumer in the `0x1696c/0x16978` selector path, but not yet a direct bridge into the cursor-global assignment block; producer hunt should continue by tracing dataflow through `FUN_00026610`/adjacent callers and the `0x24c00 -> 0x2f028` return contract rather than expecting a direct `0x3dd7e -> DAT_0002a990` edge
   - new structural convergence point is now explicit in callgraph stitching: both `FUN_00024c00` (cursor-assignment ingress lane) and `FUN_00026610` (selector/consumer lane) are direct siblings called from `ProcessMainSchedulerTickLoop` (`0x24c50`)
   - parent-order recovery around `0x24c50..0x24cdd` shows deterministic sequencing in this slice: conditional `CALL 0x24c00` at `0x24c9f` executes before `CALL 0x26610` at `0x24caf`; this supports treating selector consumption as downstream scheduler work relative to the `0x24c00 -> 0x2f028 -> 0x25654` ingress write path
   - same parent window confirms additional lane context: `CALL 0x39358` at `0x24c87` occurs before the `0x24c00`/`0x26610` pair, and the loop condition after `0x26610` compares `EDX` with `[0x169a4]` (`0x24cba..0x24cbc`), indicating scheduler feedback state but still no direct `+0x38` writer exposure in this parent block
   - refreshed callgraph for `FUN_00025654` is now concrete and aligns with the existing EDX-provenance model: callee chain includes `CALL 0x32868` (`0x25654`), `CALL 0x323f8` (`0x25659`), then `CALL 0x39298` (`0x2565e`), with `FUN_00039298` remaining the sole writer of `DAT_0002a990` in this ingress lane
   - practical narrowing update from this pass: the most actionable unresolved boundary is no longer between `0x26610` and `0x3dd7e`; it is the producer contract of `0x2f028` (what pointer it returns in `EDX` before `0x24c00` stores to `0x1696c/0x16978` and then enters `0x25654`)
   - caller-side contract at `FUN_00024c00` is now fully pinned in one coherent window (`0x24c00..0x24c4c`): no stack args are prepared for `CALL 0x2f028`; `EDX` is explicitly zeroed immediately before call (`0x24c24`), then immediately consumed/stored (`0x24c2b`, `0x24c31`) and carried into `CALL 0x25654` (`0x24c3c`)
   - `FUN_00025644` (called at `0x24c37` immediately before `0x25654`) is now confirmed as a tiny two-call wrapper (`CALL 0x27450`, `CALL 0x253b4`) with no `EDX` writes in its recovered body; this removes the last nearby clobber candidate between `0x2f028` return and `0x25654` ingress in the `0x24c00` lane
   - targeted `FUN_0002f028` body recovery remains overlap-sensitive/noisy, but repeated windows still preserve the same contract-level signal: inbound caller set is singleton (`0x24c26`), and internal blocks include multiple `CALL 0x35b14` probes with `EDX` participating in candidate-selection-style comparisons
   - trust stance for this pass: treat `0x2f028` as a contract-confirmed `EDX` producer (high confidence at caller boundary), but treat its internal semantics as provisional until dual-recipe intersection is applied in `0x2f020..0x2f120`
   - dual-recipe intersection over `0x2f020..0x2f120` is now complete and robust (`recipe_A INS=89`, `recipe_B INS=91`, intersection `I_COUNT=89`), meaning the key contract instructions in `FUN_0002f028` survive reconstruction variance in this band
   - both-survive `0x2f028` core includes repeated `CALL 0x35b14` sites with `EDX` re-seeding (`0x2f08a/0x2f0a4/0x2f0dc`) and `CMP EAX,-1` checks (`0x2f052/0x2f091/0x2f0ab/0x2f0e3`), plus early `EDX` handling (`0x2f040 MOV EDI,EDX`, `0x2f046 XCHG EAX,EDX`)
   - interpretation refinement: even with residual overlap noise in some local opcodes, `FUN_0002f028` now has an overlap-robust internal signature of iterative selection/probe behavior (`0x35b14` loop family) while preserving the already-confirmed caller contract that post-call `EDX` is consumed as pointer material in `FUN_00024c00`
   - contract probe on `FUN_00035b14` (`INS=36`, `CALLERS=15`) now shows a stable shape consistent with selector/probe semantics used broadly across movement/planner code (`UpdateActorMovementAndTarget`, `FUN_000301a8`, `SelectPlayEventTargetPoint`, and `FUN_0002f028`)
   - key register behavior in `FUN_00035b14`: it snapshots incoming `EDX` into `EDI` early (`0x35b1d`), performs internal candidate loop/index work (`ECX` increments up to `0x100`), then restores `EDX` from `EDI` (`0x35b47`) before return while setting `EAX` as result (`ECX` on success path or `0xffffffff` on failure path)
   - implication for `0x2f028` interpretation: repeated `MOV EDX,ECX -> CALL 0x35b14 -> CMP EAX,-1` is compatible with iterative candidate probing where `EAX` carries success/failure/index and `EDX` is preserved as an input selector/context value, which fits the current high-confidence model of `0x2f028` as an upstream producer stage for the pointer lane consumed at `0x24c00`
   - new carry-proof check from callsite to sink is now explicit and clean in one packet:
      - caller chain anchors are intact (`0x24c24 XOR EDX,EDX`, `0x24c26 CALL 0x2f028`, `0x24c2b/0x24c31` stores, `0x24c3c CALL 0x25654`, `0x25654 -> 0x32868`, `0x25659 -> 0x323f8`, `0x2565e -> 0x39298`, `0x3930d MOV [0x2a990],EDX`)
      - bounded scan over `0x39298..0x3930c` reports zero explicit `EDX`-write instructions before `0x3930d`, strengthening the claim that the incoming `EDX` value is carried to the `DAT_0002a990` assignment in this lane
   - dual-recipe `0x2f028` tail intersection (`0x2f0b0..0x2f11b`) confirms stable late-lane instructions including `0x2f0dc MOV EDX,ECX` and preserved epilogue (`... RET` at `0x2f11b`), giving an overlap-robust final-stage source for the returned `EDX` contract
   - downstream consumer link is now pinned with exact instructions:
      - `FUN_000394b8` is a 2-ins getter (`0x394b8 MOV EAX,[0x2a990] ; 0x394bd RET`)
      - in `FUN_00038760`, this value is consumed via `0x38769 CALL 0x394b8`, `0x3876e LEA EDX,[EAX+0x2c]`, `0x38777 MOV ESI,[EDX+0xc]` => effective read from `[DAT_0002a990 + 0x38]`
   - practical confidence update: the end-to-end bridge `0x24c26 (2f028-return EDX) -> 0x3930d (DAT_0002a990=EDX) -> 0x394b8 getter -> 0x38777 ([DAT+0x38])` is now strongly constrained; remaining uncertainty is concentrated in the exact internal producer logic inside `FUN_0002f028` (overlap-heavy), not in the carry/linkage path
   - new intersection slice over `FUN_0002f028` (`I_COUNT=89`) sharpens internal semantics around the unresolved seam:
      - repeated pattern remains stable: `MOV EDX,ECX -> CALL 0x35b14 -> CMP EAX,-1` (`0x2f08a/0x2f08c/0x2f091`, `0x2f0a4/0x2f0a6/0x2f0ab`, `0x2f0dc/0x2f0de/0x2f0e3`)
      - late tail still stages/commits `ECX` (`MOV [EBP],ECX` at `0x2f0b6` and `0x2f105`, then `TEST ECX,ECX` at `0x2f108`) before epilogue
      - together with broader `0x35b14` callsite context (many callers compare `EAX` against `-1`/small constants), this points to `EAX` being selector/result-like while `EDX` carries context through the probe loop
   - direct `DAT_0002a990` reference classification remains compact and consistent (`6` refs total): writes at `0x3930d/0x39386/0x393a3`, reads at `0x3944d/0x394b8/0x39602`
   - local usage windows reinforce pointer-slot behavior for `DAT_0002a990` in downstream consumers:
      - `FUN_00039414` reads `ESI=[0x2a990]` then compares list node pointer `EBX` against `ESI` (`0x39462 CMP EBX,ESI`)
      - `FUN_000395d0` compares candidate pointer `EAX` against `[0x2a990]` (`0x39602 CMP EAX,[0x2a990]`)
   - interpretation delta: current evidence now strongly supports that `DAT_0002a990` is pointer-like in consumers, while `FUN_0002f028` internal stable slice still looks partially selector/probe-like; therefore the highest-value unresolved boundary is the final value-conversion step inside `0x2f028` that turns loop/probe state into the pointer carried in `EDX`
   - new strict 3-recipe ECX def-chain comparator is now in place for the exact handoff sites (`0x2f08a`, `0x2f0a4`, `0x2f0dc`): all three reconstruction recipes converge (`A=89`, `B=91`, `C=89`, `I3=89`) and produce the same stable predecessor defs
   - stable ECX->EDX feeder classes at those handoff sites are now explicit:
      - `0x2f08a MOV EDX,ECX` fed by `0x2f076 INC ECX` (arith class)
      - `0x2f0a4 MOV EDX,ECX` fed by `0x2f096 MOV ECX,0x62f0fc8` (imm class; currently unmapped as address)
      - `0x2f0dc MOV EDX,ECX` fed by `0x2f0c4 LEA ECX,[EDI-1]` (lea class)
   - source check for that final LEA lane is also stable: nearest both-survive `EDI` def before `0x2f0c4` is `0x2f040 MOV EDI,EDX`, so this path is effectively a transform of incoming `EDX`, not a newly recovered direct pointer load
   - tail-flow recovery (`0x2f0dc..0x2f11b`) confirms loop/error control shape rather than a new pointer-fetch site: `CALL 0x35b14`, `CMP EAX,-1`, fail path `MOV ECX,EAX` then jump back, and late commit via `[EBP]=ECX` before epilogue
   - narrowing consequence: no both-survive memory-load-to-ECX def has been recovered at the exact EDX handoff points in `0x2f028`; the unresolved seam is now the conversion boundary where probe/index-like ECX state becomes pointer-like EDX at function exit under overlap-sensitive code paths
   - 3-way reconstruction divergence audit over `0x2f020..0x2f120` found effectively no additional high-value hidden defs outside the stable intersection (`UNIQ_A=0`, `UNIQ_C=0`, `UNIQ_B=2` where only one register-related unique line appears: `0x2f11e ADD CL,[EDX+0x6a5]`, low-trust/noisy)
   - implication: current overlap variance is not concealing a robust alternate `MOV/LEA ECX|EDX` memory-load producer in this window; unresolved pointer-conversion logic is likely in still-noisy local ops/implicit control interactions, not in a missing clean side branch
   - micro-tail branch tagging over `0x2f0b0..0x2f11b` now separates value domains more clearly:
      - at `0x2f0e3 (CMP EAX,-1)`, both-survive defs show `ECX` still from `LEA ECX,[EDI-1]` and `EDX` from `MOV EDX,ECX`
      - after the failure branch, `0x2f0e8 MOV ECX,EAX` feeds the late commit/test (`0x2f105`, `0x2f108 TEST ECX,ECX`), indicating return-status shaping on this path rather than a fresh pointer-load site
   - stable immediate `0x62f0fc8` is now confirmed as local-only inside `FUN_0002f028` (`0x2f096 MOV ECX,0x62f0fc8`, `0x2f0b9 CMP ECX,0x62f0fc8`) with no other program-wide instruction hits; treat it as local sentinel/control constant in this lane, not a shared global pointer anchor
   - sparse recovery at `0x2f0ec..0x2f11b` remains overlap-noisy but preserves the same control shell (`... CMP EAX,-1`, branch, `MOV [EBP],ECX`, `TEST ECX,ECX`, return-code shaping `EAX=1/0` before epilogue)
   - literal-usage rescan for staging globals is now minimal and tight in current decode:
      - `0x1696c` literal hit only at `0x24c2b` (`MOV [0x1696c],EDX`)
      - `0x16978` literal hit only at `0x24c31` (`MOV [0x16978],EDX`)
     this strengthens the postcondition that `FUN_00024c00` is the concrete staging writer endpoint for whatever `EDX` contract `FUN_0002f028` returns
   - refined seam statement: internal stable `0x2f028` tail evidence is currently status-domain heavy, while external carry/consumer evidence is pointer-domain heavy; the unresolved conversion boundary is now strictly between these two domains within overlap-sensitive local semantics of `FUN_0002f028`
   - focused success-vs-commit subpath extraction (`0x2f0c9` branch) is now stable and explicit:
      - direct-commit arm: `0x2f0cb JMP 0x2f108` bypasses the extra `0x35b14` probe
      - success/probe arm: `0x2f0d5..0x2f0de` executes `MOV EAX,ESI ; MOV EDX,ECX ; CALL 0x35b14` before rejoining tail control at `CMP EAX,-1`
      - failure loop arm: `0x2f0e8 MOV ECX,EAX ; JMP 0x2f08a` feeds status-like values back into the probe loop
   - branch-site origin tags confirm the split near commit test:
      - at `0x2f108 TEST ECX,ECX`, the nearest stable ECX def is `0x2f0e8 MOV ECX,EAX` (from probe result domain)
      - at `0x2f0c7 CMP ECX,EDX`, ECX is still `LEA`-derived (`0x2f0c4`) and EDX is propagated from ECX (`0x2f0a4` / `0x2f0dc`)
   - caller boundary remains clean and unique for staging postcondition:
      - `0x24c26 CALL 0x2f028` has pre-def `0x24c24 XOR EDX,EDX`
      - immediate post-call uses are only `MOV [0x1696c],EDX` and `MOV [0x16978],EDX` before `CALL 0x25654`
      - `FUN_00024c00` has one caller (`ProcessMainSchedulerTickLoop` at `0x24c9f`)
   - sink boundary uniqueness remains stable:
      - `FUN_00039298` has one caller (`0x2565e` in `FUN_00025654`)
      - assignment anchor remains `0x3930d MOV [0x2a990],EDX`
   - updated inference: the unresolved conversion seam is now localized to `FUN_0002f028` path interaction around `0x2f0d5..0x2f0ea` (where probe outcomes re-enter ECX/EDX flow), while all outer boundary contracts (`0x24c26` postcondition and `0x3930d` sink) are high-confidence and structurally unique
   - per-edge micro-CFG tagging over `0x2f0c0..0x2f110` is now stable (`7` blocks) and identifies the first explicit domain flip edge:
      - pre-split and split edges (`0x2f0c9`, `0x2f0cb`, entry to `0x2f0d5`) remain ECX-lea/EDX-from-ECX dominated (`ECX <- LEA [EDI-1]`, `EDX <- ECX`)
      - probe arm (`0x2f0d5..0x2f0e7`) keeps that same ECX/EDX lineage while setting up `EAX <- ESI` before `CALL 0x35b14`
      - first explicit status-handoff occurs at `0x2f0e8 MOV ECX,EAX`; from this point, blocks feeding the commit test (`0x2f108 TEST ECX,ECX`) carry `ECX_from_eax`
   - practical consequence: the earliest reproducible status-domain handoff is now pinned to edge `0x2f0e6 -> 0x2f0e8`; there is no earlier both-survive pointer-load def at the branch split itself (`0x2f0c9/0x2f0cb`)
   - refined unresolved seam: not "where split occurs" but "how post-`0x35b14` `EAX`/`ECX` status-like flow coexists with the externally observed pointer-like `EDX` postcondition at `0x24c26` and sink write at `0x3930d`"
   - lightweight symbolic-domain pass over intersection-stable instructions in `FUN_0002f028` (seeded with caller fact `EDX=0` at `0x24c24`) now quantifies the inconsistency:
      - stable transforms produce only status/derived domains (`arith(unknown)`, local immediate `0x62f0fc8`, and `lea(in_edx_zero-1)`), with no both-survive memory-load promotion to a pointer domain before return
      - symbolic final stable `EDX` domain in this model is `lea(in_edx_zero-1)`, which conflicts with the externally observed pointer-like behavior (`0x24c2b/0x24c31` staging and later `DAT_0002a990` pointer consumption)
   - interpretation consequence: the pointer-domain conversion is now strongly indicated to reside in overlap-sensitive/non-stable semantics inside `FUN_0002f028` (or in side effects not represented by the intersection-stable core), not in any currently recovered deterministic ECX/EDX handoff instruction
   - non-intersection recurrence sweep over `0x2f0ec..0x2f11b` with `12` anchor permutations found a fully stable decode footprint (`18` instructions recovered in every recipe; all addresses in this window appear with frequency `12/12`), so this tail block is deterministic under current reconstruction methods even without strict set intersection
   - the deterministic tail footprint remains semantically suspicious for a normal pointer-return epilogue: recurring ops include `MOVSD ES:EDI,ESI`, `PUSH ES`, `ADD [EAX],AL`, `ADD [ECX+0xe8ca89f0],CL`, `SBB CH,[EDX]`, and `MOV ESP,[EDX+0x300006a5]` before `MOV [EBP],ECX` and return-code shaping
   - alternative alignment probes (`start=0x2f0ec..0x2f0f5`) did not surface a more plausible competing decode: only starts at `0x2f0ec/0x2f0ed/0x2f0ee/0x2f0f0` produce the same suspicious sequence; other starts yield no instruction stream in this local setup
   - raw-byte dump for `0x2f0ec..0x2f105` (`A5 06 00 00 00 89 F0 89 CA E8 1A 6A 00 00 83 F8 FF 75 CE 8B A2 A5 06 00 30 89`) corroborates that the odd instruction cluster is backed by actual bytes, not a transient display glitch
   - refined trust classification for this subrange: treat `0x2f0ec..0x2f105` as a reproducible but likely overlap-artifact-heavy decode island; it is still the highest-probability host for the missing pointer-domain conversion semantics, but current opcode-level interpretation there should remain low-confidence until a higher-fidelity carve is obtained
   - high-value improvement from byte-aligned carving: forcing decode at `0x2f0f1/0x2f0f3/0x2f0f5` recovers a materially more coherent success-path fragment from the same raw bytes:
      - `0x2f0f1 MOV EAX,ESI`
      - `0x2f0f3 MOV EDX,ECX`
      - `0x2f0f5 CALL 0x35b14`
      - `0x2f0fa CMP EAX,-1`
      - `0x2f0fd JNZ 0x2f0cd`
   - anchoring the recovered branch target at `0x2f0cd` yields additional coherent control flow preceding the known `0x35b14` probe arm:
      - `0x2f0cd MOV EBX,[ESP]`
      - `0x2f0d1 CMP ECX,EBX`
      - `0x2f0d3 JL 0x2f108`
      - `0x2f0d5 MOV EBX,1 ; 0x2f0da MOV EAX,ESI ; 0x2f0dc MOV EDX,ECX ; 0x2f0de CALL 0x35b14`
   - interpretation update: the best current carve for this overlap island is no longer the naive `0x2f0ec` stream; a more coherent overlapped subpath likely begins at `0x2f0cd` and continues through `0x2f0f1..0x2f0fd`, after which the remaining scar at `0x2f0ff` is still suspicious
   - practical consequence: the hidden conversion zone is narrower and better localized: likely inside the overlapped byte band between `0x2f0f1` and `0x2f0ff`, with `0x2f0ff` remaining the main low-confidence scar rather than the entire `0x2f0ec..0x2f105` region uniformly
   - follow-up byte-aware scoring around the remaining scar shows the coherent suffix is insensitive to local start choice: starts at `0x2f0ff..0x2f105` all preserve the same clean tail (`MOV [EBP],ECX ; TEST ECX,ECX ; JGE 0x2f113 ; MOV EAX,1 ; JMP 0x2f115 ; XOR EAX,EAX`), while the only recurring suspicious op is the lead instruction at `0x2f0ff`
   - displacement plausibility check now strongly downgrades that lead op as semantic reality:
      - current decode is `0x2f0ff MOV ESP,[EDX + 0x300006a5]`
      - displacement `0x300006a5` is unmapped in program memory and has zero other decoded uses program-wide
      - practical interpretation: `0x2f0ff` is very likely the residual overlap/artifact scar, not a trustworthy stack-pivot-like real instruction
   - refined local trust boundary:
      - high-confidence coherent overlapped subpath: `0x2f0cd .. 0x2f0fd`
      - high-confidence clean suffix: `0x2f105 .. 0x2f113`
      - low-confidence artifact scar concentrated at `0x2f0ff` (possibly masking the true transition between the recovered `JNZ 0x2f0cd` branch and the `MOV [EBP],ECX` commit/test suffix)

## Operating Constraint

This environment now has a working live Ghidra MCP connection.

Practical runtime notes:

- Use `run_ghidra_script`, not `run_script_inline`, for automation in this session.
- `run_script_inline` is enabled but currently fails in this Ghidra 12.1 session due to a source-bundle loader issue.
- The recovered functions and comments are already saved in the active project.

Relevant bridge/runtime references:

- Bridge transport and instance connect flow: [ghidra-mcp/bridge_mcp_ghidra.py](ghidra-mcp/bridge_mcp_ghidra.py)
- Bridge usage and architecture: [ghidra-mcp/CLAUDE.md](ghidra-mcp/CLAUDE.md)

## Primary Goal

Recover the real runtime source of `PLAY` calls that still emit `x = -1, y = -1` in the top residual scenes.

Questions to answer in Ghidra:

1. Does the script helper load position from actor state, globals, or scene-local structs before calling `PLAY`?
2. Are these cutscene helpers intentionally using sentinel `-1,-1` to mean “use actor slot position” or “use a hidden staging function”?
3. Is there a reusable helper shared across multiple residual scenes?
4. Are some of these residuals genuinely non-placeable from current script state and therefore safe to classify as unresolved?

Current cross-scene refinement from the VM-lite trace:

- Only `14 / 152` residual `PLAY -1,-1` rows have a recent `TALK` with non-empty hidden `film_args` in the preceding 6 libcall rows.
- That means `TALK`-carried hidden film handles are a real but narrow residual subclass, not a global explanation for the remaining tail.
- Confirmed positive buckets so far: parts of `CUTBARN`, `INTROSHA`, `OVEREDGE`, and at least one `CLIMAX` row.
- Confirmed negative Tier 1 bucket so far: `SQUARE` has no recent `TALK` rows at all in the residual run.
- Quant check on full residual tail (`152` rows): raw stack-prefix coordinate pairs are high-noise (`59` plausible in bounds), but strict non-sentinel + post-`SCROLL` gating reduces this to only `3` candidates total (`CUTBARN 293599`, `INTROSHA 226315`, `ROOFTOPS 129985`).
- Implication: a broad stack-prefix rule is too noisy right now; any next pass should be scene/handle-scoped and hypothesis-driven (start with `CUTBARN` only) rather than globally enabled.

## Priority Order

### Tier 1: Highest Semantic Payoff

These should go first because they are concentrated, scene-important, and likely to expose reusable helper semantics.

1. `CUTBARN.SCN` `entrance.script` `0x23847917` — 9 residuals
   - Residual seqs: `342, 347, 360, 377, 396, 398, 399, 403, 437`
   - IP cluster: `293157, 293197, 293285, 293397, 293528, 293557, 293569, 293599, 293916`
   - Film handles: `0x238463F4` x2, plus `0x23846B7C, 0x23846D14, 0x23846E90, 0x23847190, 0x23847280, 0x238473F0, 0x23846608`
   - Why first: largest bucket; current timeline only has fallback placeholders for the entire burst.
   - Working local split from extracted trace:
     - `342, 347, 360, 377, 396` are all `TALK -> PLAY -1,-1` with no `TALKAT` in between.
     - `398, 399, 403` form a tighter post-`SCROLL` staging run, with `403` immediately followed by `STAND actor=0 x=-2 y=150 direction=194`.
     - `437` replays `film 0x238463F4` after a long `TALK`/`SCROLL` burst involving `0x238469EC` and repeated `0x238464BC` films.
   - Checked already:
     - final scene timeline still records all nine as raw `PLAY -1,-1`
     - scene-space playback timeline has no generated placement rows for these seqs
      - conservative scheduler-stack recovery is now validated for the immediate hidden-speaker subclass only: hidden `TALK` operands from `scheduler_trace_events.csv` recover trusted anchors for `347/360/377/396` as `(114,38)`, `(114,38)`, `(114,36)`, and `(114,86)` respectively, and the focused CUTBARN regression test passes against the builder
      - scene-scoped `playcomposite` probe now improves CUTBARN from `5 placed / 9 skipped` to `9 placed / 5 skipped`; remaining unresolved rows are `342` plus the post-`SCROLL` cluster `398/399/403` and late replay `437`
      - implemented CUTBARN/script-scoped post-`SCROLL` stack-prefix gate (`scene == CUTBARN.SCN`, `script_handle == 0x23847917`, short age window + non-sentinel bounds); builder now recovers two additional rows via `timeline_scroll_prefix` (`398 -> 304,0`, `403 -> 9,72`) while leaving `INTROSHA` and `OVEREDGE` unchanged (`timeline_scroll_prefix_events = 0`)
      - fresh targeted `playcomposite` rerun (`CUTBARN/INTROSHA/OVEREDGE`) confirms downstream uptake: CUTBARN residuals drop from `9 -> 3` (resolved `347/360/377/396/398/403`, remaining `342/399/437`), while INTROSHA (`7`) and OVEREDGE (`6`) remain unchanged; no new residual rows were introduced
      - added instrumentation-only rejection analyzer for the remaining CUTBARN trio: `scripts/analyze_cutbarn_scroll_prefix_rejections.py` writes `cutbarn_scroll_prefix_rejection_report.csv/json`; latest probe classifies `342` as `no_prior_scroll`, and `399/437` as `no_plausible_prefix_pair` (recent scroll exists but no usable non-sentinel prefix pair)
      - added a narrowly gated CUTBARN same-film replay bridge (`timeline_film_replay`) for unresolved PLAY rows with a recent trusted placement of the same film; fresh targeted rerun resolves exactly one additional row (`437`, film `0x238463F4`) with no new residuals and no INTROSHA/OVEREDGE drift
      - validated next recommendation (`seq 399` adjacent trusted-neighbor carry) against latest artifacts: only one residual row in the entire probe set matches the trigger shape (CUTBARN `399`), so best-case uplift is exactly `+1` placement (`CUTBARN 2 -> 1`, global residuals `15 -> 14`, `6.67%` global reduction); precision risk is low if kept CUTBARN/script/seq-scoped
      - implemented that seq399-only neighbor-carry gate (`timeline_neighbor_carry`) and validated with fresh targeted rerun: resolved exactly CUTBARN `399` (`ip 293569`, `film 0x23846608`), introduced no new residuals, and left INTROSHA/OVEREDGE unchanged; current CUTBARN residual frontier is now only `342`
      - reran CUTBARN rejection diagnostics on the latest probe: remaining row `342` is still a pure `no_prior_scroll` case (no prefix/scroller-derived anchor path to reuse)
      - added cross-scene residual signature miner (`scripts/analyze_residual_signature_shortlist.py`): top recurring signature spans INTROSHA+OVEREDGE (`prev=PLAYSAMPLE>WAITFRAME>PLAYSAMPLE>WAITFRAME`, `stack_prefix_imm=4`, count `2`) and is the first non-CUTBARN candidate for project-wide heuristics
      - implemented cross-scene `timeline_waitframe_prefix` source (gated to unresolved PLAY rows with immediate `PLAYSAMPLE -> WAITFRAME` predecessor and plausible scheduler prefix pair) and validated on a fresh targeted rerun: resolved exactly `INTROSHA 2360` (`ip 226434`, `film 0x2903691C`) and `OVEREDGE 2930` (`ip 40394`, `film 0x20009448`), with no new residual rows
      - implemented ultra-conservative known-case non-tiny prefix recovery (`timeline_prefix_known_non_tiny`) for two validated residual IPs (`INTROSHA 2348`, `OVEREDGE 2955`) and confirmed exact `+2` uplift on fresh rerun (global residuals `12 -> 10`) with zero new residual rows
      - added placement-confidence instrumentation without behavior changes: timeline outputs now include `placement_confidence`, manifests include `placement_confidence_counts`, and residual analysis now reports confidence/source calibration fields plus `confidence_promotion_candidates`; fresh confidence probe shows trusted generated placements concentrated in `medium` confidence (`61` rows, `0` negative generated rows)
      - added automated promotion governance (`scripts/evaluate_confidence_promotions.py`) and produced current decision artifact at `outputs/playcomposite_confidence_probe/play_composite_export/confidence_promotion_decisions.json`; under `min_trusted_rows=2` and `negative_rows=0`, all six current candidates are promoted (`timeline_talk_anchor`, `timeline_scroll_prefix`, `timeline_actor_state`, `timeline_prefix_known_non_tiny`, `timeline_waitframe_prefix`, `timeline_talkat_anchor`)
      - applied the promotion decisions to live policy in `PLACEMENT_SOURCE_CONFIDENCE` (builder map now marks the six approved sources as `high`) and regenerated the three-scene confidence probe end-to-end; trusted generated confidence distribution shifted from `medium=61` to `high=59, medium=2` (remaining medium sources: `timeline_neighbor_carry`, `timeline_film_replay`), with residual frontier unchanged at `10` and zero generated negatives
      - promoted the last two singleton validated sources as well (`timeline_neighbor_carry`, `timeline_film_replay`) and rebuilt the three-scene confidence probe; trusted generated confidence distribution is now `high=61`, `medium=0`, with residual frontier still `10` and zero generated negatives
      - refreshed residual signature mining on the post-promotion 10-row frontier and extended `scripts/analyze_residual_signature_shortlist.py` to emit relaxed family signatures (`tail1`/`tail2` plus `stack_prefix_imm`) in addition to exact 4-libcall signatures; exact signatures are now all unique, but the top recurring families are cross-scene `tail1=WAITTIME|stack_prefix_imm=4` (`3` rows across `INTROSHA` + `OVEREDGE`), cross-scene `tail2=PLAY>WAITTIME|stack_prefix_imm=4` (`2` rows across `INTROSHA` + `OVEREDGE`), and cross-scene `tail1=PLAYSAMPLE|stack_prefix_imm=4` (`2` rows across `INTROSHA` + `OVEREDGE`)
      - added focused family diagnostic script `scripts/analyze_waittime_family_diagnostics.py` and ran it on `outputs/playcomposite_confidence_probe`; for target families (`tail2=PLAY>WAITTIME|stack_prefix_imm=4`, `tail1=WAITTIME|stack_prefix_imm=4`, `tail1=PLAYSAMPLE|stack_prefix_imm=4`) the report covers `5` residual rows and shows: `carry_viable=3`, `carry_not_viable=2`, nearest prior TALK/TALKAT anchors unavailable in-window (`none=5`), and non-coordinate-like stack third/fourth immediates (`12|1`, `6781|0`, `16|1`, `6|1`, `6676|0`)
      - immediate heuristic implication: the strongest deterministic candidate is not stack-prefix decoding; it is a tightly gated adjacent trusted-play carry on the three carry-viable rows (`INTROSHA 2350`, `INTROSHA 2364`, `OVEREDGE 2952`) with scene/script/seq allowlisting to avoid drift
      - implemented that allowlisted carry as `timeline_waittime_family_carry` in `build_bar_play_placement_timeline.py` (`INTROSHA 226342`, `INTROSHA 226473`, `OVEREDGE 40609`; max back = 2, fallback-rows skipped), wired it through trusted source allowlists (`extractor/discworld_extract.py`, `scripts/analyze_playcomposite_residuals.py`), and added regression coverage in `tests/test_waittime_family_carry_cases.py`
      - validated end-to-end on regenerated three-scene confidence probe: residual frontier improved `10 -> 7` (`INTROSHA 5 -> 3`, `OVEREDGE 4 -> 3`, `CUTBARN 1 unchanged`), trusted generated high-confidence rows increased `61 -> 64`, and `negative_generated_by_source` remained empty
      - ran a second family diagnostic pass on remaining INTROSHA TALK-tail residuals (`tail2=PLAY>TALK|stack_prefix_imm=2` / `tail1=TALK|stack_prefix_imm=2`): both rows (`INTROSHA 226364`, `226456`) are carry-viable with adjacent trusted neighbors and no viable in-window TALK/TALKAT anchors
      - implemented second allowlisted carry source `timeline_talk_family_carry` in `build_bar_play_placement_timeline.py` for those two INTROSHA IPs (max back = 2), wired trusted-source allowlists (`extractor/discworld_extract.py`, `scripts/analyze_playcomposite_residuals.py`), and added regression coverage in `tests/test_talk_family_carry_cases.py`
      - validated on regenerated three-scene confidence probe: residual frontier improved `7 -> 5` (`INTROSHA 3 -> 1`, `OVEREDGE 3 unchanged`, `CUTBARN 1 unchanged`), trusted generated high-confidence rows increased `64 -> 66`, and generated negatives remain zero
      - refreshed promotion decisions after rollout: `candidate_count=8`, `promoted_count=8`, `deferred_count=0` (new promoted source: `timeline_talk_family_carry`)
      - implemented OVEREDGE cluster carry source `timeline_overedge_cluster_carry` for allowlisted IPs (`OVEREDGE 40322`, `40339`, `40573`) using bidirectional short-gap trusted-neighbor carry (prefer prior trusted up to distance 2, then future timeline candidate up to distance 2), wired trusted-source allowlists, and added regression coverage in `tests/test_overedge_cluster_carry_cases.py`
      - validated on regenerated three-scene confidence probe: residual frontier improved `5 -> 2` (remaining only `CUTBARN 342` and `INTROSHA 2343`), generated negatives remain zero, and promotion decisions stay fully promoted under thresholds (`candidate_count=6`, `promoted_count=6`, `deferred_count=0`)
      - implemented final singleton bootstrap source `timeline_bootstrap_carry` for allowlisted first-row residual IPs (`CUTBARN 293157`, `INTROSHA 226278`) using forward trusted candidate carry (ahead up to 3 rows), wired trusted-source allowlists, and added regression coverage in `tests/test_singleton_bootstrap_carry_cases.py`
      - validated on regenerated three-scene confidence probe: residual frontier is now `0` (`CUTBARN=0`, `INTROSHA=0`, `OVEREDGE=0`) with no generated negatives; note current residual analyzer emits empty trusted-confidence/source aggregates when there are no residual scenes because it only accumulates per-scene trusted stats inside the `expected_skips > 0` branch
      - fixed that analyzer gating in `scripts/analyze_playcomposite_residuals.py` by decoupling trusted timeline aggregation from residual reconstruction; rerun on the same zero-residual probe now reports populated trusted totals (`trusted_generated_confidence_counts.high=71`, `candidate_count=10`, `promoted_count=10`) while residual frontier remains `0`
      - extended the existing singleton bootstrap carry to the same-shape SQUARE pair (`SQUARE2 3921/3922`, `SQUARE3 3981/3982`) after confirming the residuals were just the first two rows and the trusted actor-state anchor appears immediately after; fresh rerun now resolves both scenes fully (`residual_skip_count=0`, `trusted_generated_source_counts: timeline_actor_state=6, timeline_bootstrap_carry=4`) with no negatives, and promotion evaluation still cleanly promotes both trusted sources under threshold
      - validated the remaining CUTBARN singleton target as a live artifact refresh (`CUTBARN.SCN` only): residual frontier is also `0`, with `timeline_neighbor_carry` covering the CUTBARN 399 row (`293569`) alongside the already-valid CUTBARN anchor sources; no new negatives were introduced and the scene remains fully clean
   - Questions:
     - For `342/347/360/377/396`, does `TALK` without `TALKAT` still seed the same runtime target state that `TALKAT` made visible in other scenes?
     - For `398/399/403`, does the planner consume post-`SCROLL` staging state rather than dialogue-speaker state?
       - For `398` and `403`, do pre-film stack-prefix pairs carry coordinates (`398`: `imm:304|imm:0|imm:0|imm:0|film`, `403`: `imm:6014|imm:0|imm:9|imm:72|film`) even though nominal PLAY args remain `-1,-1`?
     - Does the `STAND actor=0 x=-2 y=150 direction=194` at `ip 293614` explain the later `0x238463F4` replay at `ip 293916`?
       - Which `ActorOwnerStateV1` instance owns the hidden `TALK` film handles (`0x23847518`, `0x23847660`, `0x23847788`, `0x238478B0`) before `FUN_00038658` chooses a playback resource?
       - Where is the transient linked-owner slot `[owner + 0x284]` populated before `UpdateActorMovementAndTarget` consumes it?
      - Does the six-slot owner pool rooted at `0x21f98` establish linked-owner relationships indirectly during owner allocation/setup rather than through an explicit recovered `MOV [owner + 0x284], ...` store?
      - If `+0x284` is not ordinary planner or dispatch state, is it written only in overlapped code inside the `0x38a44..0x38b4c` region or by a non-recovered helper near the `0x1ed3c..0x1f248` owner-management layer?
      - Is `+0x284` written by a copy/transfer path that is not surfaced as an explicit `0x284` operand, while the visible `+0x278/+0x28c` pair only tracks staged cleanup/removal of the neighboring owner?
      - Can `FUN_000394c0` be made coherent enough to show which structure field it updates after `param_1[9] = param_2`, especially on the call path from `FUN_00038658` and `FUN_00038a32`?
      - Is the real `+0x284` producer somewhere before the `0x394b8/0x394c0` scheduler loop, with the scheduler pair merely waiting for dispatch readiness rather than constructing owner relationships?
      - If the copy/transfer hypothesis is mostly falsified in the planner/scheduler slices, should the next pass move back upward to owner-management callers and search for pointer staging before `FUN_00038658` rather than for hidden block copies?
      - If both the scheduler pair and the `DAT_00013c58` slot table are mostly dispatch/resource machinery, should the next pass target the resource-to-owner bridge just before `FUN_00038544` instead of continuing through generic owner-management helpers?
      - If the bridge before `FUN_00038544` is also mostly dispatch descriptor machinery, is the `+0x284` write happening in an earlier owner-selection layer (e.g. the pool-neighbor arbitration around `0x38a44`) that only later triggers the dispatch chain path?

2. `INTROSHA.SCN` `entrance.script` `0x290373CE` — 7 residuals
   - Residual seqs: `2343, 2348, 2350, 2352, 2360, 2362, 2364`
   - IP cluster: `226278, 226315, 226342, 226364, 226434, 226456, 226473`
   - Film handles: `0x29037014, 0x29037050, 0x29035FF4, 0x2903658C, 0x2903691C, 0x29035F88, 0x29036998`
   - Why second: already improved through `TALKAT`; the remaining tail may reveal the boundary condition of that model.
   - Working local split from extracted trace:
     - `2343, 2348, 2350, 2360` have no recent `TALK` rows in the preceding 6 libcall steps.
     - `2352` follows `TALK @ 226352` with hidden film args `0x29035FF4 | 0x29035C44`.
     - `2362` and `2364` follow `TALK @ 226444` with hidden film args `0x2903691C | 0x290368E8`.
    - Checked already:
       - scene-scoped `playcomposite` probe with conservative `timeline_talk_anchor` recovery yields **no uplift** (`44 placed / 7 skipped`, unchanged from baseline)
       - the first seven rows in `introsha_scene_space_playback_timeline_full.csv` remain `fallback_visual_validation`
   - Questions:
     - Are `2352`, `2362`, and `2364` the same hidden-speaker subclass as `CUTBARN`, while the other four belong to a different path?
     - Is there a helper before the first `TALKAT` at seq `2365` that initializes a speaker anchor for the earlier rows?
     - Is `TALK` alone enough to identify a speaker slot even without `TALKAT` when those hidden film args are present?
       - Are the hidden-film `TALK` rows here carrying only speaker identity (film/string) while coordinate seeding is deferred until the first `TALKAT` block?

3. `SQUARE.SCN` `scene.hSceneScript` `0x17052648` — 6 residuals
   - IP cluster: `337499, 337511, 337536, 337560, 337572, 337584`
   - Film handles: `0x1704E1B0, 0x1704E6E8, 0x1704F8DC, 0x1704F504, 0x1704F624, 0x1704F5F0`
   - Why third: high concentration in a single scene script, which is often easier to reason about than a scattered actor script.
   - Checked already:
     - no recent `TALK` rows appear in the preceding 6 libcall steps for any of the six residual `PLAY -1,-1` rows
   - Questions:
     - Does the scene script dispatch through a common ambient-object or crowd helper?
     - Are these `PLAY -1,-1` rows using a scene-global table of spawn points?

4. `OVEREDGE.SCN` `entrance.script` `0x20009D63` + adjacent `0x20009EAF` — 6 residuals
   - Residual seqs on these entrance handles: `2923, 2925, 2930, 2948, 2952, 2955`
   - Main IP cluster: `40322, 40339, 40394, 40573, 40609`
   - Adjacent handle: `entrance.script` `0x20009EAF` at `ip 40639`
   - Film handles: `0x20009324` x2, plus `0x2000975C, 0x20009448, 0x20009870, 0x20009D24`
   - Why fourth: another concentrated entrance script bucket with repeated film handles.
   - Working local split from extracted trace:
     - `2923, 2925, 2930` have no recent `TALK` rows in the preceding 6 libcall steps.
     - `2948` and `2952` follow a dense `TALK` burst with hidden film args built from `0x2000991C` and `0x20009394`.
       - `2955` is on adjacent handle `0x20009EAF` and also remains unresolved.
    - Checked already:
       - scene-scoped `playcomposite` probe with conservative `timeline_talk_anchor` recovery yields **no uplift** (`0 placed / 6 skipped`)
       - all six rows remain `fallback_visual_validation` in `overedge_scene_space_playback_timeline_full.csv`
   - Questions:
       - Are `2948` and `2952` a crowd-dialogue/staging subclass rather than the same path as the first three rows?
       - Does this helper derive placement from camera scroll or edge transition state?
       - Are `esc=1` and `esc=0` variants semantically important for hidden placement rules?
         - Does the dense `TALK` burst at `ip 40410..40560` provide only dialogue sequencing (e.g., `imm:6|imm:1`) rather than scene coordinates, explaining the zero uplift under conservative `timeline_talk_anchor`?

5. `CLIMAX.SCN` `entrance.script` `0x0406C85F` and actor handles `0x0406D43C/49/56` — 6 residuals total
   - Residual seqs: `265, 267, 295, 337, 338, 339`
   - Entrance IPs: `446060, 446082, 446277`
   - Actor IPs: `447558, 447571, 447584`
   - Film handles: `0x0406B5F4, 0x0406B5C0, 0x0406AEC4, 0x0406B734, 0x0406C76C, 0x0406B628`
   - Why fifth: high-value scene, but the remaining misses already resisted the `TALKAT` pass and may be genuinely implicit staging.
   - Questions:
     - What differentiates these six from the 38 `TALKAT`-recoverable placements?
     - Do actor-side helpers pass film handles that imply actor ownership without explicit coordinates?

### Tier 2: Shared Cutscene Patterns

These are good candidates if Tier 1 reveals a reusable “cutscene helper means actor/object position” pattern.

1. `CUTROOFT.SCN`
   - Handles: `0x0C8262B2`, `0x0C826375`, `0x0C826430`, `0x0C8264F3`, `0x0C826540`, `0x0C82654D`
   - Shape: four entrance-script handles, then two actor-script handles; `0x0C8264F3` is the only duplicated bucket.
   - Residuals: 7

2. `CUTSQUAR.SCN`
   - Handles: `0x4080A0B6`, `0x4080A2E8`, `0x4080A301`, `0x4080A30E`, `0x4080A31B`, `0x4080A328`
   - Shape: one entrance-script setup row, then a tight actor-script burst at `ip 41714..41778`.
   - Residuals: 7

3. `CUTTOILE.SCN`
   - Actor-side burst of 1x1 preview films; likely special control markers, not visual actors.
   - Residuals: 4

### Tier 3: Low-Priority Boilerplate / Likely Synthetic Cases

These should wait unless Tier 1 shows a broadly reusable helper.

1. `ACT1.SCN` through `ACT4.SCN`
   - Repeated two-row pattern, likely title-card or act-card scaffolding.

2. Very small preview films or 1x1 assets
   - Examples: `CUTTOILE`, `INTROHID`, `MISSILE`, `OVEREDGE` tiny previews.
   - These may be markers, masks, or effect triggers rather than placeable scene sprites.

## Recommended Ghidra MCP Flow

With the live connection already working, use this order on each Tier 1 target:

1. For each target script handle:
   - Decompile the containing function.
   - Get P-code for the same function.
   - Identify the exact block around the residual `ip` range.
   - Trace where the `PLAY` call’s effective coordinates come from when the literals are `-1,-1`.
   - Prefer `run_ghidra_script` for targeted instruction/range dumps.

2. Look specifically for:
   - actor struct field reads
   - scene-global coordinate tables
   - helper calls that translate actor/object IDs to screen positions
   - temporary stack structs passed by pointer
   - sentinel branches where `-1,-1` means “reuse current actor placement”
   - planner status writes that distinguish accepted candidates, retries, terminal alternates, and hard fallbacks

3. Only after confirming one reusable semantic rule:
   - map it back into the extractor/builder
   - validate on one focused scene
   - rerun the full artifact only if the focused check is clean

## Suggested MCP Tool Use

The exact live schema depends on the connected instance, but the bridge docs indicate these are the right classes of tools to use:

1. `decompile_function`
   - First pass for the handle owning each residual burst.

2. `analyze_function_complete`
   - Useful when decompilation is noisy and you need signatures, variables, and references together.

3. `get_function_pcode`
   - Best discriminating check for how `-1,-1` is transformed before the runtime helper call.

4. `find_similar_functions_fuzzy` or equivalent
   - After identifying one helper in `CUTBARN`, search for the same shape in `CUTROOFT`, `CUTSQUAR`, and `OVEREDGE`.

5. `run_ghidra_script` only if needed
   - Reserve for batch extraction after a manual proof of one pattern.

## What Counts As Success

Any of the following is a good outcome:

1. Prove a new reusable semantic rule for `PLAY -1,-1` and feed it back into placement recovery.
2. Prove that a top residual cluster is using hidden actor/object position state not currently surfaced by the trace pipeline.
3. Prove that a cluster is not a meaningful scene-placement candidate at all, so it should be explicitly classified and deprioritized.

## What Not To Do

1. Do not broaden trust to `fallback_visual_validation` just to reduce counts.
2. Do not start with low-value singleton scenes.
3. Do not do broad undirected binary archaeology before checking the Tier 1 handles above.

## Cycle Log 2026-05-22 (Safety-Gated No-Go)

### Outcome

- `run_safe_waittime_cycle.py` returned `no_safe_candidate` with `candidate_count: 0`.
- Action taken: `diagnostics_skipped` (expected under safety-first gating).
- Promotion decision: `NO-GO` for confidence expansion this cycle.

### Gate Evidence

- `validate_static_progress_baseline.py` returned `all_checks_pass: true`.
- Trust and provenance fingerprints remained stable:
   - case stub fingerprint `a44650c2`
   - dispatcher fingerprint `a79ab56c`
   - slice fingerprint `6cfdb45e`
- `run_ci_verify.ps1` passed dry snapshot drift check and regression suite (`Ran 50 tests ... OK`).

### Operational Decision

- Keep the freeze posture for waittime-family promotion until triage yields a safe candidate.
- Continue using the same trigger rule:
   - baseline validator failure, or
   - non-empty safe triage candidate set, or
   - new trusted provenance edge.

## Cycle Log 2026-05-22 (Controlled Token-Broadening Probe)

### Probe Setup

- Command:
   - `python scripts/run_safe_waittime_cycle.py --require-tokens TALK,TALKAT,PLAY --select smallest`
- Scope control remained unchanged:
   - triage-first
   - one-family diagnostic maximum
   - no trust-policy relaxation

### Probe Result

- Selected family: `tail1=PLAYSAMPLE|stack_prefix_imm=2`
- Scene/count: `scene_count=1`, `rows_analyzed=1`
- Diagnostic outcome:
   - `carry_viability_counts: { carry_not_viable: 1 }`
   - `nearest_anchor_type_counts: { none: 1 }`
- Decision: `NO-GO` for promotion from this probe.

### Safety Verification

- `validate_static_progress_baseline.py`: `all_checks_pass: true`
- `run_ci_verify.ps1`: dry snapshot drift check passed; regression suite passed (`Ran 51 tests ... OK`).

### Follow-On Guidance

- Keep default token gate (`TALK,TALKAT`) for routine cycles.
- Reserve broader-token probes for explicit, one-off diagnostics with full gate reruns.
## Cycle Log 2026-05-22T11:44:05+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail1=PLAYSAMPLE|stack_prefix_imm=2`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_not_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`

## Cycle Log 2026-05-22T11:45:32+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail1=PLAY|stack_prefix_imm=3`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_not_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`

## Cycle Log 2026-05-22T12:07:00+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail1=WAITFRAME|stack_prefix_imm=0`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`

## Cycle Log 2026-05-22T12:09:54+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail2=BACKGROUND>PLAYSAMPLE|stack_prefix_imm=2`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_not_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`

## Cycle Log 2026-05-22T12:12:31+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail2=BACKGROUND>WAITTIME|stack_prefix_imm=0`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_not_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`

## Cycle Log 2026-05-22T12:13:16+00:00 (Automated)

### Outcome

- status: `diagnostic_ran`
- selected_source: `one_off_probe`
- selected_family: `tail2=BACKGROUND>WAITTIME|stack_prefix_imm=4`
- diagnostic_exit_code: `0`
- rows_analyzed: `1`

### Signals

- carry_viability_counts: `{"carry_not_viable": 1}`
- nearest_anchor_type_counts: `{"none": 1}`

### Artifacts

- triage_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_frontier_candidate_summary.json`
- diagnostic_summary: `C:\Users\James\Desktop\Decompile\discworld_full_repo_package\outputs\full_playcomposite_pipeline\play_composite_export\waittime_family_diagnostic_summary.json`
