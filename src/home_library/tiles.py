"""Stage 1: cut a photo into overlapping tiles (see docs/pipeline.md)."""


def _starts(size, tile, min_overlap):
    if tile >= size:
        return [0]
    span = size - tile
    gaps = -(-span // (tile - min_overlap))  # ceiling division
    count = gaps + 1
    return [(2 * i * span + gaps) // (2 * gaps) for i in range(count)]


def plan_layout(width, height, *, tile_width=1560, tile_height=2000,
                min_overlap_x=300, min_overlap_y=900):
    tile_width = min(tile_width, width)
    tile_height = min(tile_height, height)
    return {
        "tile_width": tile_width,
        "tile_height": tile_height,
        "columns": _starts(width, tile_width, min_overlap_x),
        "rows": _starts(height, tile_height, min_overlap_y),
    }
