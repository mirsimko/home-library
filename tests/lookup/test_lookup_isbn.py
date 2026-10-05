from home_library.lookup.isbn import normalize_isbn


def test_isbn13_with_hyphens_is_normalized_to_digits():
    assert normalize_isbn("978-4-89309-431-5") == "9784893094315"


def test_isbn13_with_a_wrong_check_digit_is_rejected():
    assert normalize_isbn("9784893094316") is None


def test_isbn10_is_validated_and_keeps_a_final_x():
    assert normalize_isbn("4-8340-0082-6") == "4834000826"
    assert normalize_isbn("80-11-01711-x") == "801101711X"
    assert normalize_isbn("4834000827") is None


def test_text_that_is_not_an_isbn_is_rejected():
    assert normalize_isbn("") is None
    assert normalize_isbn("hello") is None
    assert normalize_isbn("978-4-89309-431") is None
    assert normalize_isbn("48340X0826") is None


def test_non_ascii_digits_are_rejected_without_raising():
    assert normalize_isbn("²" * 13) is None
    assert normalize_isbn("²" * 10) is None
    assert normalize_isbn("٩٧٨٤٨٩٣٠٩٤٣١٥") is None
