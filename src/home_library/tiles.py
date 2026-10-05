"""Stage 1: cut a photo into overlapping tiles (see docs/pipeline.md)."""
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from home_library.workspace import refuse_inside_checkout


def _starts(size, tile, min_overlap):
    if tile >= size:
        return [0]
    span = size - tile
    gaps = -(-span // (tile - min_overlap))  # ceiling division
    count = gaps + 1
    return [(2 * i * span + gaps) // (2 * gaps) for i in range(count)]


def plan_layout(width, height, *, tile_width=1560, tile_height=2000,
                min_overlap_x=300, min_overlap_y=900):
    if tile_width <= min_overlap_x or tile_height <= min_overlap_y:
        raise ValueError("a tile must be larger than its minimum overlap")
    tile_width = min(tile_width, width)
    tile_height = min(tile_height, height)
    return {
        "tile_width": tile_width,
        "tile_height": tile_height,
        "columns": _starts(width, tile_width, min_overlap_x),
        "rows": _starts(height, tile_height, min_overlap_y),
    }


def cut_tiles(photo, out_dir, *, quality=88, **layout_options):
    photo = Path(photo)
    out_dir = refuse_inside_checkout(out_dir)
    with Image.open(photo) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    layout = plan_layout(width, height, **layout_options)
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    for stale in tiles_dir.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()
    tiles = []
    for row, top in enumerate(layout["rows"], start=1):
        for column, left in enumerate(layout["columns"], start=1):
            box = [left, top, left + layout["tile_width"], top + layout["tile_height"]]
            tile = image.crop(box)
            tile.info.clear()
            for rotation in (0, 180):
                name = f"r{row}c{column}-r{rotation}.jpg"
                shown = tile if rotation == 0 else tile.rotate(180)
                shown.save(tiles_dir / name, "JPEG", quality=quality)
                size = (tiles_dir / name).stat().st_size
                tiles.append({"file": name, "row": row, "column": column,
                              "rotation": rotation, "box": box, "bytes": size})
    manifest = {
        "photo": photo.name,
        "sha256": hashlib.sha256(photo.read_bytes()).hexdigest(),
        "width": width,
        "height": height,
        "layout": layout,
        "quality": quality,
        "tiles": tiles,
        "total_bytes": sum(t["bytes"] for t in tiles),
    }
    (out_dir / "tiles.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
