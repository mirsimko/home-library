import pytest

from home_library.merge import match_key, merge_reads


def book(n, title, **over):
    b = {"n": n, "where": f"r1c1-r0.jpg, #{n}", "visible": "spine", "title": title, "other_text": "",
         "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}
    b.update(over)
    return b


def read(read_id, books, errors=None, file="shelf-1.jpg", complete=True):
    return {"read_id": read_id, "file": file, "books": books, "errors": errors or [], "complete": complete}


def reading(read_id, b):
    return {"read_id": read_id, **b}


def test_match_key_ignores_width_case_spaces_and_punctuation():
    assert match_key("ＴＨＥ  Blue-Kite!") == "thebluekite"
    assert match_key("The Blue Kite") == "thebluekite"


def test_match_key_keeps_diacritics_kana_and_digits_significant():
    assert match_key("Zeleny drak") != match_key("Zelený drak")
    assert match_key("Zelený drak") == "zelenýdrak"
    assert match_key("あかいふうせん") != match_key("アカイフウセン")
    assert match_key("ハリー・ポッター 1") != match_key("ハリー・ポッター 2")
    assert match_key("ハリー・ポッター 1") == "ハリーポッター1"


def test_match_key_of_punctuation_only_is_empty():
    assert match_key(" ・!? ") == ""


def test_match_key_folds_half_width_katakana_to_full_width():
    assert match_key("ｱｶｲ") == "アカイ"


def test_two_reads_that_agree_give_an_accepted_item_with_both_readings():
    a = read("a-sol", [book(1, "Zelený drak")])
    b = read("b-spark", [book(4, "Zelený drak")])
    merged = merge_reads(a, b)
    assert merged["file"] == "shelf-1.jpg"
    assert merged["reads"] == ["a-sol", "b-spark"]
    assert merged["unreadable"] == []
    assert merged["parse_errors"] == []
    assert merged["items"] == [{
        "status": "accepted", "reason": "agreed", "title": "Zelený drak", "language": "cs", "exact": True,
        "readings": [reading("a-sol", book(1, "Zelený drak")), reading("b-spark", book(4, "Zelený drak"))],
    }]


def only_item(a_title, b_title):
    merged = merge_reads(read("a-sol", [book(1, a_title)]), read("b-spark", [book(1, b_title)]))
    assert len(merged["items"]) == 1
    return merged["items"][0]


def test_exact_is_true_only_for_titles_equal_after_nfc_and_trimming():
    assert only_item("Zelený drak", " Zelený drak\n")["exact"] is True
    assert only_item("Zelený drak", "Zelený drak")["exact"] is True  # decomposed accent
    for other in ["zelený drak", "Zelený  drak", "Zelený drak!", "Ｚelený drak"]:
        item = only_item("Zelený drak", other)
        assert item["status"] == "accepted"
        assert item["exact"] is False, other


def test_a_one_character_difference_is_not_accepted_and_goes_to_review_as_near():
    a = read("a-sol", [book(1, "The Blue Kite", language="en")])
    b = read("b-spark", [book(2, "The Blue Kito", language="en")])
    items = merge_reads(a, b)["items"]
    assert len(items) == 1
    item = items[0]
    assert (item["status"], item["reason"], item["exact"]) == ("review", "near", False)
    assert item["title"] == "The Blue Kite"
    assert [r["read_id"] for r in item["readings"]] == ["a-sol", "b-spark"]
    assert [r["title"] for r in item["readings"]] == ["The Blue Kite", "The Blue Kito"]
