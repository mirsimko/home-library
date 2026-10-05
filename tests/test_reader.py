import json

from PIL import Image

from home_library.reader import render_prompt
from home_library.tiles import cut_tiles

SIX_TILE_FILES = (
    "r1c1-r0.jpg r1c1-r180.jpg r1c2-r0.jpg r1c2-r180.jpg r1c3-r0.jpg r1c3-r180.jpg "
    "r2c1-r0.jpg r2c1-r180.jpg r2c2-r0.jpg r2c2-r180.jpg r2c3-r0.jpg r2c3-r180.jpg"
)


def cut_small_photo(tmp_path, name="shelf-1.jpg"):
    """A 250x150 photo cut into 100x100 tiles: 2 rows by 3 columns."""
    photo = tmp_path / name
    Image.new("RGB", (250, 150), (200, 120, 40)).save(photo, "JPEG")
    work = tmp_path / "work" / photo.stem
    manifest = cut_tiles(photo, work, tile_width=100, tile_height=100,
                         min_overlap_x=20, min_overlap_y=20)
    return work, manifest


def test_prompt_for_a_two_by_three_manifest_names_every_tile_and_the_counts(tmp_path):
    _, manifest = cut_small_photo(tmp_path)

    prompt = render_prompt(manifest)

    assert f"The images are attached in this order: {SIX_TILE_FILES}\n" in prompt
    assert "Attached are 12 images: the photo cut into 6 overlapping tiles" in prompt
    assert "(2 rows by 3 columns)" in prompt
    assert '{"file": "shelf-1.jpg", "books": [' in prompt
    assert "<<" not in prompt
