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


def test_a_title_only_one_read_gave_is_solo_review_with_one_reading():
    a = read("a-sol", [book(1, "Zelený drak")])
    b = read("b-spark", [book(1, "あかいふうせん", language="ja")])
    items = merge_reads(a, b)["items"]
    assert [(i["status"], i["reason"], i["title"], i["language"], i["exact"]) for i in items] == [
        ("review", "solo", "Zelený drak", "cs", False),
        ("review", "solo", "あかいふうせん", "ja", False),
    ]
    assert [r["read_id"] for r in items[0]["readings"]] == ["a-sol"]
    assert [r["read_id"] for r in items[1]["readings"]] == ["b-spark"]


def test_items_follow_the_first_read_then_entries_only_the_second_read_gave():
    a = read("a-sol", [book(1, "Alpha Book"), book(2, "Bravo Tale"), book(3, "Charlie Song")])
    b = read("b-spark", [book(1, "Zulu Story"), book(2, "Charlie Song"), book(3, "Alpha Book"), book(4, "Yankee Hill")])
    titles = [i["title"] for i in merge_reads(a, b)["items"]]
    assert titles == ["Alpha Book", "Bravo Tale", "Charlie Song", "Zulu Story", "Yankee Hill"]


def test_duplicate_copies_pair_one_to_one_and_the_extra_copy_is_solo():
    a = read("a-sol", [book(1, "The Blue Kite"), book(2, "The Blue Kite")])
    b = read("b-spark", [book(1, "The Blue Kite")])
    items = merge_reads(a, b)["items"]
    assert [(i["status"], i["reason"]) for i in items] == [("accepted", "agreed"), ("review", "solo")]
    assert [r["n"] for r in items[0]["readings"]] == [1, 1]
    assert [r["read_id"] for r in items[1]["readings"]] == ["a-sol"]
    assert [r["n"] for r in items[1]["readings"]] == [2]


def test_two_copies_in_each_read_give_two_accepted_pairs():
    a = read("a-sol", [book(1, "The Blue Kite"), book(2, "The Blue Kite")])
    b = read("b-spark", [book(5, "The Blue Kite"), book(6, "The Blue Kite")])
    items = merge_reads(a, b)["items"]
    assert [i["reason"] for i in items] == ["agreed", "agreed"]
    assert [[r["n"] for r in i["readings"]] for i in items] == [[1, 5], [2, 6]]


def test_partial_or_inferred_titles_are_never_accepted_even_when_the_other_read_agrees():
    clean = book(1, "The Blue Kite", language="en")
    cases = [
        book(1, "The Blue Kite", language="en", readable="partial"),
        book(1, "The Blue Kite", language="en", inferred="The Blue Kite?"),
        book(1, "The Blue Kite", language="en", readable="no"),
    ]
    for other in cases:
        for first, second in [(clean, other), (other, clean)]:
            items = merge_reads(read("a-sol", [first]), read("b-spark", [second]))["items"]
            assert len(items) == 1, other
            assert (items[0]["status"], items[0]["reason"]) == ("review", "partial"), other
            assert len(items[0]["readings"]) == 2
            assert items[0]["exact"] is True


def test_a_title_marked_yes_with_an_empty_inferred_is_eligible():
    items = merge_reads(read("a-sol", [book(1, "A Tale", inferred="")]), read("b-spark", [book(1, "A Tale")]))["items"]
    assert items[0]["status"] == "accepted"


def test_a_partial_entry_alone_is_reported_as_partial_not_solo():
    a = read("a-sol", [book(1, "Zelený dr", readable="partial")])
    items = merge_reads(a, read("b-spark", []))["items"]
    assert [(i["status"], i["reason"]) for i in items] == [("review", "partial")]


def test_near_titles_where_one_is_partial_are_reported_as_partial():
    a = read("a-sol", [book(1, "The Blue Kite", readable="partial")])
    b = read("b-spark", [book(1, "The Blue Kito")])
    items = merge_reads(a, b)["items"]
    assert [(i["reason"], len(i["readings"])) for i in items] == [("partial", 2)]
