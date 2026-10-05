from home_library.tiles import plan_layout


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
