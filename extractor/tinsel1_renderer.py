#!/usr/bin/env python3
"""
GPL-3.0-or-later compatible Discworld/Tinsel 1 PC resource probe + bitmap renderer.

This is an extractor-oriented port of the Tinsel 1 PC WrtNonZero path from
ScummVM's engines/tinsel/graphics.cpp. It intentionally implements only the
Discworld PC / Tinsel 1 tile-index renderer used by the uploaded .SCN samples.

Source basis:
- ScummVM engines/tinsel/graphics.cpp: DrawObject() and WrtNonZero()
- ScummVM engines/tinsel/handle.cpp: image/palette record structures
"""
from __future__ import annotations

import argparse, json, struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Optional

try:
    from PIL import Image
except Exception:
    Image = None

CHUNK_BITMAP_ARENA = 0x33340003
CHUNK_PALETTE = 0x33340005
CHUNK_IMAGE = 0x33340006
HANDLE_SHIFT = 23
OFFSET_MASK = 0x007FFFFF
HANDLE_MASK = 0xFF800000


def u32le(b: bytes, off: int) -> int: return struct.unpack_from('<I', b, off)[0]
def i16le(b: bytes, off: int) -> int: return struct.unpack_from('<h', b, off)[0]
def u16le(b: bytes, off: int) -> int: return struct.unpack_from('<H', b, off)[0]

@dataclass
class Chunk:
    offset: int
    id: int
    next: int
    payload_offset: int
    payload_size: int

@dataclass
class ImageRecord:
    index: int
    offset: int
    width: int
    height: int
    anim_x: int
    anim_y: int
    bitmap_handle: int
    bitmap_offset: int
    palette_handle: int
    palette_offset: int

@dataclass
class RenderStats:
    width: int
    height: int
    index_bytes: int
    max_tile_index: int
    min_tile_index: int
    positive_blocks: int
    transparent_blocks: int
    skipped_blocks: int
    out_of_bounds_blocks: int
    consumed_index_bytes: int

class Tinsel1Scene:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.chunks = list(self.walk_chunks())
        self.by_id = {c.id: c for c in self.chunks}
        # ScummVM DrawObject() for TinselVersion < 2 computes these from the locked file base.
        self.char_base = u32le(self.data, 0x10)
        self.trans_offset = u32le(self.data, 0x14)

    def walk_chunks(self) -> Iterator[Chunk]:
        off = 0
        seen = set()
        while 0 <= off < len(self.data):
            if off in seen:
                raise ValueError(f'chunk chain loop at {off}')
            seen.add(off)
            if off + 8 > len(self.data):
                raise ValueError(f'truncated chunk header at {off}')
            cid = u32le(self.data, off)
            nxt = u32le(self.data, off + 4)
            end = len(self.data) if nxt == 0 else nxt
            if end < off + 8 or end > len(self.data):
                raise ValueError(f'invalid next offset {nxt} at {off}')
            yield Chunk(off, cid, nxt, off + 8, end - (off + 8))
            if nxt == 0:
                break
            off = nxt

    def image_records(self) -> list[ImageRecord]:
        c = self.by_id[CHUNK_IMAGE]
        if c.payload_size % 16:
            raise ValueError('CHUNK_IMAGE payload is not divisible by 16')
        out = []
        for i, off in enumerate(range(c.payload_offset, c.payload_offset + c.payload_size, 16)):
            w = i16le(self.data, off)
            h = u16le(self.data, off + 2)
            ax = i16le(self.data, off + 4)
            ay = i16le(self.data, off + 6)
            bh = u32le(self.data, off + 8)
            ph = u32le(self.data, off + 12)
            out.append(ImageRecord(i, off, w, h, ax, ay, bh, bh & OFFSET_MASK, ph, ph & OFFSET_MASK))
        return out

    def palette(self, palette_offset: int) -> list[tuple[int,int,int,int]]:
        n = struct.unpack_from('<i', self.data, palette_offset)[0]
        if not (0 <= n <= 256):
            raise ValueError(f'invalid palette color count {n} at {palette_offset}')
        pal = []
        p = palette_offset + 4
        for _ in range(n):
            v = u32le(self.data, p); p += 4
            pal.append((v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, 255))
        # Fill absent slots with transparent black to keep indexed images simple.
        while len(pal) < 256:
            pal.append((0,0,0,0))
        return pal

    def render_wrt_nonzero(self, rec: ImageRecord, apply_clipping: bool=False) -> tuple[bytearray, RenderStats]:
        """Port of ScummVM Tinsel 1 PC WrtNonZero(), rendering to a tight width stride.

        Clipping is intentionally disabled by default for standalone asset export.
        """
        width, height = rec.width, rec.height
        if width <= 0 or height <= 0:
            raise ValueError(f'empty/invalid image dimensions {width}x{height}')
        stride = width
        dest = bytearray(width * height)
        src = rec.bitmap_offset
        right_clip = 0
        top_clip = left_clip = bot_clip = 0
        h = height
        if apply_clipping:
            h -= bot_clip
            src += 2 * ((width + 3) >> 2) * (top_clip >> 2)
            h -= top_clip
            top_clip %= 4
        y = 0
        pos_count = neg_count = skip_count = oob = 0
        max_idx = -999999
        min_idx = 999999
        src_start = src
        while h > 0:
            temp_x = 0
            line_width = width
            if not apply_clipping:
                box_top = 0
                box_bottom = min(h - 1, 3)
                box_left = 0
            else:
                box_top = top_clip; top_clip = 0
                box_bottom = min(box_top + h - 1, 3)
                box_left = left_clip
                if box_left >= 4:
                    src += 2 * (box_left >> 2)
                    line_width -= box_left & 0xfffc
                    box_left %= 4
                line_width -= box_left
            while line_width > right_clip:
                box_right = min(box_left + line_width - right_clip - 1, 3)
                if src + 2 > len(self.data):
                    raise ValueError('index stream overran file')
                raw = u16le(self.data, src); src += 2
                index_val = raw if raw < 0x8000 else raw - 0x10000
                max_idx = max(max_idx, index_val); min_idx = min(min_idx, index_val)
                if index_val >= 0:
                    pos_count += 1
                    tile_off = self.char_base + (index_val << 4)
                    transparent = False
                else:
                    idx = index_val & 0x7fff
                    if idx == 0:
                        skip_count += 1
                        tile_off = None
                    else:
                        neg_count += 1
                        tile_off = self.char_base + ((self.trans_offset + idx) << 4)
                    transparent = True
                if tile_off is not None:
                    if tile_off < 0 or tile_off + 16 > len(self.data):
                        oob += 1
                    else:
                        for yp in range(box_top, box_bottom + 1):
                            row_off = tile_off + yp * 4
                            dy = y + (yp - box_top)
                            if dy >= height: continue
                            for xp in range(box_left, box_right + 1):
                                pix = self.data[row_off + xp]
                                if (not transparent) or pix != 0:
                                    dx = temp_x + (xp - box_left)
                                    if 0 <= dx < width:
                                        dest[dy * stride + dx] = pix
                temp_x += box_right - box_left + 1
                line_width -= 3 - box_left + 1
                box_left = 0
            if line_width >= 0:
                src += 2 * ((line_width + 3) >> 2)
            h -= box_bottom - box_top + 1
            y += box_bottom - box_top + 1
        stats = RenderStats(width, height, width*height, max_idx, min_idx, pos_count, neg_count, skip_count, oob, src - src_start)
        return dest, stats

    def save_png(self, rec: ImageRecord, out_path: Path) -> RenderStats:
        if Image is None:
            raise RuntimeError('Pillow is required for PNG export')
        pixels, stats = self.render_wrt_nonzero(rec)
        pal = self.palette(rec.palette_offset)
        rgba = bytearray()
        for px in pixels:
            rgba.extend(pal[px])
        img = Image.frombytes('RGBA', (rec.width, rec.height), bytes(rgba))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return stats

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scn', type=Path)
    ap.add_argument('--out', type=Path, default=Path('out'))
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--manifest', type=Path)
    args = ap.parse_args()
    scn = Tinsel1Scene(args.scn)
    records = scn.image_records()
    report = {'file': str(args.scn), 'char_base': scn.char_base, 'trans_offset': scn.trans_offset, 'chunks':[asdict(c) for c in scn.chunks], 'renders': []}
    for rec in records[args.start:args.start+args.limit]:
        if rec.width <= 0 or rec.height <= 0:
            continue
        try:
            out = args.out / f'{args.scn.stem}_{rec.index:04d}_{rec.width}x{rec.height}.png'
            st = scn.save_png(rec, out)
            item = asdict(rec); item.update({'png': str(out), 'stats': asdict(st)})
            report['renders'].append(item)
        except Exception as e:
            item = asdict(rec); item.update({'error': str(e)})
            report['renders'].append(item)
    if args.manifest:
        args.manifest.write_text(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
