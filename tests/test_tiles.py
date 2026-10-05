import hashlib
import json

from PIL import Image

from home_library.tiles import cut_tiles, plan_layout


def make_photo(path, size, color=(200, 120, 40)):
    Image.new("RGB", size, color).save(path, "JPEG", quality=90)
    return path


def test_layout_of_a_4080_by_3072_photo_matches_the_contract_example():
    assert plan_layout(4080, 3072) == {
        "tile_width": 1560,
        "tile_height": 2000,
        "columns": [0, 1260, 2520],
        "rows": [0, 1072],
    }


def test_image_smaller_than_a_tile_gives_one_tile_of_the_images_size():
    assert plan_layout(1000, 800) == {
        "tile_width": 1000,
        "tile_height": 800,
        "columns": [0],
        "rows": [0],
    }


def test_layout_of_a_portrait_3072_by_4080_photo():
    # width: 1512 px of travel, at most 1260 per step -> 3 columns of step 756
    # height: 2080 px of travel, at most 1100 per step -> 3 rows of step 1040
    assert plan_layout(3072, 4080) == {
        "tile_width": 1560,
        "tile_height": 2000,
        "columns": [0, 756, 1512],
        "rows": [0, 1040, 2080],
    }


def test_any_vertical_run_of_928_pixels_lies_whole_inside_some_tile():
    layout = plan_layout(4080, 3072)
    height = layout["tile_height"]
    tiles = [(top, top + height) for top in layout["rows"]]
    for start in range(0, 3072 - 928 + 1):
        end = start + 928
        assert any(top <= start and end <= bottom for top, bottom in tiles), start


def test_no_tile_side_exceeds_2000_with_the_defaults():
    for width, height in [(4080, 3072), (3072, 4080), (9000, 9000), (100, 5000)]:
        layout = plan_layout(width, height)
        assert layout["tile_width"] <= 2000
        assert layout["tile_height"] <= 2000


def test_cutting_a_4080_by_3072_photo_writes_twelve_named_tiles_and_a_manifest(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (4080, 3072))
    out = tmp_path / "work" / "shelf-1"

    manifest = cut_tiles(photo, out)

    expected_names = sorted(
        f"r{r}c{c}-r{rot}.jpg" for r in (1, 2) for c in (1, 2, 3) for rot in (0, 180)
    )
    assert sorted(p.name for p in (out / "tiles").iterdir()) == expected_names
    assert json.loads((out / "tiles.json").read_text(encoding="utf-8")) == manifest
    assert manifest["photo"] == "shelf-1.jpg"
    assert (manifest["width"], manifest["height"]) == (4080, 3072)
    assert manifest["layout"] == {
        "tile_width": 1560, "tile_height": 2000,
        "columns": [0, 1260, 2520], "rows": [0, 1072],
    }
    assert manifest["quality"] == 88
    boxes = {t["file"]: t["box"] for t in manifest["tiles"]}
    assert boxes["r1c1-r0.jpg"] == [0, 0, 1560, 2000]
    assert boxes["r2c3-r180.jpg"] == [2520, 1072, 4080, 3072]
    assert boxes["r2c2-r0.jpg"] == boxes["r2c2-r180.jpg"] == [1260, 1072, 2820, 3072]
