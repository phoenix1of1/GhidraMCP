# BAR Composited Sprite Preview Prototype

This prototype composites character/actor sprites onto the BAR.SCN background using decoded placement/anchor data for all PLAY events. It outputs a preview image for regression and visual validation.

- Uses first frame of each PLAY event (no animation)
- Z-order is event order (not true runtime layering)
- No palette/effect logic applied (not yet decoded for BAR)
- No runtime BLOCK snap; uses nominal/fallback positions

See `bar_composited_sprite_preview.png` for the output.
