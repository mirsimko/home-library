from home_library.tiles import plan_layout


def test_layout_of_a_4080_by_3072_photo_matches_the_contract_example():
    assert plan_layout(4080, 3072) == {
        "tile_width": 1560,
        "tile_height": 2000,
        "columns": [0, 1260, 2520],
        "rows": [0, 1072],
    }
