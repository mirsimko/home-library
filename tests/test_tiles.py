import hashlib
import json

import pytest
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


def test_manifest_bytes_match_the_files_on_disk(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (2000, 2400))
    out = tmp_path / "out"

    manifest = cut_tiles(photo, out)

    for tile in manifest["tiles"]:
        assert tile["bytes"] == (out / "tiles" / tile["file"]).stat().st_size
    assert manifest["total_bytes"] == sum(
        p.stat().st_size for p in (out / "tiles").iterdir())


def test_manifest_sha256_is_the_hash_of_the_photo_file(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (1200, 900))

    manifest = cut_tiles(photo, tmp_path / "out")

    assert manifest["sha256"] == hashlib.sha256(photo.read_bytes()).hexdigest()


RED, GREEN, BLUE, YELLOW = (230, 20, 20), (20, 200, 20), (20, 20, 230), (240, 230, 20)


def make_corner_photo(path, size=(1000, 800)):
    """Four flat quadrants: red top-left, green top-right, blue bottom-left, yellow bottom-right."""
    width, height = size
    image = Image.new("RGB", size, RED)
    image.paste(GREEN, (width // 2, 0, width, height // 2))
    image.paste(BLUE, (0, height // 2, width // 2, height))
    image.paste(YELLOW, (width // 2, height // 2, width, height))
    image.save(path, "JPEG", quality=95)
    return path


def close(pixel, color, tolerance=25):
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, color))


def test_r0_tile_is_as_photographed_and_r180_is_its_exact_half_turn(tmp_path):
    photo = make_corner_photo(tmp_path / "shelf-1.jpg")
    out = tmp_path / "out"

    cut_tiles(photo, out)

    with Image.open(out / "tiles" / "r1c1-r0.jpg") as r0, \
            Image.open(out / "tiles" / "r1c1-r180.jpg") as r180:
        r0.load(), r180.load()
        assert r0.size == r180.size == (1000, 800)
        # r0 keeps the photographed layout
        assert close(r0.getpixel((10, 10)), RED)
        assert close(r0.getpixel((990, 790)), YELLOW)
        # r180 is r0 turned by half a turn, pixel for pixel up to JPEG noise
        turned = r0.rotate(180)
        total = sum(
            abs(a - b)
            for a, b in zip(turned.tobytes(), r180.tobytes())
        )
        assert total / (1000 * 800 * 3) < 3
        assert close(r180.getpixel((10, 10)), YELLOW)
        assert close(r180.getpixel((990, 790)), RED)


def test_tiles_carry_no_exif_and_an_exif_rotated_photo_gives_upright_tiles(tmp_path):
    # Stored 1000x800 with orientation 6 (rotate 90 clockwise to view):
    # the upright photo is 800x1000, and the stored top-left (red) ends up top-right.
    stored = Image.open(make_corner_photo(tmp_path / "plain.jpg"))
    exif = Image.Exif()
    exif[0x0112] = 6
    photo = tmp_path / "shelf-1.jpg"
    stored.save(photo, "JPEG", quality=95, exif=exif)
    out = tmp_path / "out"

    manifest = cut_tiles(photo, out)

    assert (manifest["width"], manifest["height"]) == (800, 1000)
    with Image.open(out / "tiles" / "r1c1-r0.jpg") as tile:
        tile.load()
        assert tile.size == (800, 1000)
        assert len(tile.getexif()) == 0
        assert "exif" not in tile.info
        assert close(tile.getpixel((790, 10)), RED)
        assert close(tile.getpixel((10, 10)), BLUE)


def test_a_second_run_with_another_layout_leaves_only_the_new_tiles(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (4080, 3072))
    out = tmp_path / "out"
    cut_tiles(photo, out)  # three columns, so r1c3 and r2c3 exist now
    (out / "tiles" / "notes.txt").write_text("stray")

    # tile 3000 wide: 1080 px of travel, step at most 2700 -> 2 columns
    manifest = cut_tiles(photo, out, tile_width=3000)

    assert manifest["layout"]["columns"] == [0, 1080]
    expected = sorted(
        f"r{r}c{c}-r{rot}.jpg" for r in (1, 2) for c in (1, 2) for rot in (0, 180))
    assert sorted(t["file"] for t in manifest["tiles"]) == expected
    assert sorted(p.name for p in (out / "tiles").iterdir()) == expected


def test_cutting_into_a_directory_inside_a_git_checkout_is_refused_and_writes_nothing(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    photo = make_photo(tmp_path / "shelf-1.jpg", (1200, 900))
    out = tmp_path / "repo" / "work" / "shelf-1"

    with pytest.raises(ValueError):
        cut_tiles(photo, out)

    assert not (tmp_path / "repo" / "work").exists()


def test_tiles_of_both_rotations_carry_no_jpeg_comment(tmp_path):
    photo = tmp_path / "shelf-1.jpg"
    Image.open(make_corner_photo(tmp_path / "plain.jpg")).save(
        photo, "JPEG", quality=95, comment=b"private note")
    out = tmp_path / "out"

    cut_tiles(photo, out)

    for name in ("r1c1-r0.jpg", "r1c1-r180.jpg"):
        with Image.open(out / "tiles" / name) as tile:
            assert "comment" not in tile.info
        assert b"private note" not in (out / "tiles" / name).read_bytes()


def test_a_tile_no_wider_than_its_minimum_overlap_is_refused(tmp_path):
    with pytest.raises(ValueError):
        plan_layout(2000, 800, tile_width=200)
    with pytest.raises(ValueError):
        plan_layout(2000, 800, tile_width=300)


def test_an_impossible_layout_leaves_an_earlier_run_untouched(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (2000, 800))
    out = tmp_path / "out"
    cut_tiles(photo, out)
    before = sorted(p.name for p in (out / "tiles").iterdir())

    with pytest.raises(ValueError):
        cut_tiles(photo, out, tile_width=200)

    assert before and sorted(p.name for p in (out / "tiles").iterdir()) == before


def block_color(x, y):
    """Colour of the generated mosaic at a source pixel: 510x512 blocks, each its own colour."""
    return (20 + 25 * (x // 510), 20 + 35 * (y // 512), 128)


def test_every_tile_shows_its_own_part_of_the_photo(tmp_path):
    mosaic = Image.new("RGB", (4080, 3072))
    for bx in range(8):
        for by in range(6):
            mosaic.paste(block_color(bx * 510, by * 512),
                         (bx * 510, by * 512, bx * 510 + 510, by * 512 + 512))
    photo = tmp_path / "shelf-1.jpg"
    mosaic.save(photo, "JPEG", quality=95)
    out = tmp_path / "out"

    manifest = cut_tiles(photo, out)

    assert len(manifest["tiles"]) == 12
    for tile_info in manifest["tiles"]:
        left, top, right, bottom = tile_info["box"]
        with Image.open(out / "tiles" / tile_info["file"]) as tile:
            tile.load()
            assert tile.size == (right - left, bottom - top) == (1560, 2000)
            for px in range(100, 1560, 200):
                for py in range(100, 2000, 200):
                    x, y = left + px, top + py
                    if min(x % 510, y % 512, 510 - x % 510, 512 - y % 512) < 12:
                        continue  # too close to a block edge for lossy compression
                    sx, sy = (px, py) if tile_info["rotation"] == 0 else (1559 - px, 1999 - py)
                    assert close(tile.getpixel((sx, sy)), block_color(x, y)), (tile_info["file"], px, py)


def test_every_manifest_entry_has_its_file_row_column_rotation_and_box(tmp_path):
    photo = make_photo(tmp_path / "shelf-1.jpg", (4080, 3072))

    manifest = cut_tiles(photo, tmp_path / "out")

    lefts, tops = [0, 1260, 2520], [0, 1072]
    expected = [
        (f"r{r}c{c}-r{rot}.jpg", r, c, rot, [lefts[c - 1], tops[r - 1], lefts[c - 1] + 1560, tops[r - 1] + 2000])
        for r in (1, 2) for c in (1, 2, 3) for rot in (0, 180)
    ]
    assert [(t["file"], t["row"], t["column"], t["rotation"], t["box"])
            for t in manifest["tiles"]] == expected
