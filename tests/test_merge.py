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
