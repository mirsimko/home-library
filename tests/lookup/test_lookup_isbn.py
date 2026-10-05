from home_library.lookup.isbn import normalize_isbn


def test_isbn13_with_hyphens_is_normalized_to_digits():
    assert normalize_isbn("978-4-89309-431-5") == "9784893094315"
