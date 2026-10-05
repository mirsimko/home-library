import json

from home_library.parse import parse_read

FIELDS = ["n", "where", "visible", "title", "other_text", "language", "readable", "confidence", "inferred"]


def entry(n=1, title="Zelený drak", **over):
    e = {"n": n, "where": "r1c1-r0.jpg, left", "visible": "spine", "title": title, "other_text": "",
         "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}
    e.update(over)
    return e


def answer(*entries, file="shelf-1.jpg"):
    return json.dumps({"file": file, "books": list(entries)}, ensure_ascii=False)


def test_clean_json_answer_gives_complete_read():
    raw = answer(entry(1, "Zelený drak"), entry(2, "あかいふうせん", language="ja"))
    read = parse_read(raw)
    assert read["file"] == "shelf-1.jpg"
    assert [b["title"] for b in read["books"]] == ["Zelený drak", "あかいふうせん"]
    assert read["errors"] == []
    assert read["complete"] is True


def test_answer_in_code_fence_with_prose_is_read():
    raw = "Here are the books I found:\n```json\n" + answer(entry(1, "The Blue Kite", language="en")) + "\n```\nHope this helps!"
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["The Blue Kite"]
    assert read["file"] == "shelf-1.jpg"
    assert read["complete"] is True


def test_entry_with_a_missing_quote_is_reported_and_its_neighbours_survive():
    raw = (
        '{"file": "shelf-1.jpg", "books": [\n'
        '{"n": 1, "title": "A"},\n'
        '{"n": 2, "title": B"},\n'
        '{"n": 3, "title": "C"}\n'
        ']}'
    )
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A", "C"]
    assert [b["n"] for b in read["books"]] == [1, 3]
    assert len(read["errors"]) == 1
    error = read["errors"][0]
    assert error["position"] == 2
    assert error["offset"] == 59  # 35 chars of header and newline, 22 of entry 1, comma and newline
    assert error["raw"] == '{"n": 2, "title": B"}'
    assert error["reason"] != ""
    assert read["complete"] is False


def test_entry_with_a_missing_comma_is_reported_with_its_raw_text():
    raw = (
        '{"file": "shelf-1.jpg", "books": [\n'
        '{"n": 1, "title": "A"},\n'
        '{"n": 2 "title": "B"},\n'
        '{"n": 3, "title": "C"}\n'
        ']}'
    )
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A", "C"]
    assert read["errors"][0]["position"] == 2
    assert read["errors"][0]["raw"] == '{"n": 2 "title": "B"}'
    assert "delimiter" in read["errors"][0]["reason"]


def test_braces_brackets_and_escaped_quotes_inside_a_title_do_not_split_entries():
    raw = (
        '{"file": "shelf-1.jpg", "books": [\n'
        '{"n": 1, "title": "Kite } ] { [ \\"Blue\\""},\n'
        '{"n": 2, "title": "Broken {x} \\"q\\"" "other_text": "}"},\n'
        '{"n": 3, "title": "C"}\n'
        ']}'
    )
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ['Kite } ] { [ "Blue"', "C"]
    assert len(read["errors"]) == 1
    assert read["errors"][0]["raw"] == '{"n": 2, "title": "Broken {x} \\"q\\"" "other_text": "}"}'


def test_answer_cut_off_inside_an_entry_keeps_complete_entries_and_is_incomplete():
    raw = '{"file": "shelf-1.jpg", "books": [\n{"n": 1, "title": "A"},\n{"n": 2, "title": "Zel'
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A"]
    assert read["errors"][0]["position"] == 2
    assert read["errors"][0]["raw"] == '{"n": 2, "title": "Zel'
    assert read["complete"] is False


def test_answer_cut_off_between_entries_is_incomplete_without_an_error():
    raw = '{"file": "shelf-1.jpg", "books": [\n{"n": 1, "title": "A"},\n'
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A"]
    assert read["errors"] == []
    assert read["complete"] is False


def test_missing_fields_are_filled_with_empty_strings_and_all_nine_are_present():
    raw = '{"file": "shelf-1.jpg", "books": [{"n": 1, "title": "The Blue Kite", "readable": "yes"}]}'
    book = parse_read(raw)["books"][0]
    assert list(book) == FIELDS
    assert book["title"] == "The Blue Kite"
    assert book["where"] == ""
    assert book["inferred"] == ""
    assert book["confidence"] == ""


def test_unusable_n_is_replaced_by_the_position_in_the_list():
    raw = answer(entry(1, "A"), entry("x", "B"), entry(None, "C"), entry(2.5, "D"), entry(True, "E"), entry(9, "F"))
    read = parse_read(raw)
    assert [b["n"] for b in read["books"]] == [1, 2, 3, 4, 5, 9]


def test_missing_n_is_replaced_by_the_position_in_the_list():
    e = entry(1, "B")
    del e["n"]
    read = parse_read(answer(entry(1, "A"), e))
    assert [b["n"] for b in read["books"]] == [1, 2]


def test_unknown_readable_value_becomes_partial_and_known_values_stay():
    raw = answer(entry(1, "A", readable="yes"), entry(2, "B", readable="no"), entry(3, "C", readable="partial"),
                 entry(4, "D", readable="mostly"), entry(5, "E", readable="Yes"), entry(6, "F", readable=True))
    read = parse_read(raw)
    assert [b["readable"] for b in read["books"]] == ["yes", "no", "partial", "partial", "partial", "partial"]


def test_non_object_entries_become_errors_and_neighbours_survive():
    raw = '{"file": "shelf-1.jpg", "books": [{"n": 1, "title": "A"}, 42, "text, ] }", {"n": 4, "title": "D"}]}'
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A", "D"]
    assert [(e["position"], e["raw"]) for e in read["errors"]] == [(2, "42"), (3, '"text, ] }"')]
    assert read["errors"][0]["offset"] == 58
    assert read["complete"] is False


def test_garbage_answer_gives_no_books_one_error_and_incomplete():
    raw = "I am sorry, I could not look at the photos."
    read = parse_read(raw)
    assert read["books"] == []
    assert len(read["errors"]) == 1
    assert read["errors"][0]["raw"] == raw
    assert read["errors"][0]["reason"] != ""
    assert read["file"] == ""
    assert read["complete"] is False


def test_empty_answer_gives_no_books_and_incomplete():
    read = parse_read("")
    assert read["books"] == []
    assert read["complete"] is False
    assert len(read["errors"]) == 1


def test_object_without_a_books_list_keeps_the_file_name_and_is_incomplete():
    read = parse_read('{"file": "shelf-2.jpg", "result": []}')
    assert read["file"] == "shelf-2.jpg"
    assert read["books"] == []
    assert read["complete"] is False
    assert len(read["errors"]) == 1


def test_non_string_field_values_become_strings():
    raw = answer(entry(1, 2001, other_text=None, language=["ja"]))
    book = parse_read(raw)["books"][0]
    assert book["title"] == "2001"
    assert book["other_text"] == ""
    assert book["language"] == '["ja"]'


def test_object_nested_inside_a_malformed_entry_is_not_promoted_to_a_book():
    raw = '{"books":[{"title":"bad" "other_text":{"title":"Invented","readable":"yes"}},{"title":"C"}]}'
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["C"]
    assert read["books"][0]["n"] == 2
    assert [(e["position"], e["raw"]) for e in read["errors"]] == [
        (1, '{"title":"bad" "other_text":{"title":"Invented","readable":"yes"}}')
    ]


def test_braces_and_a_bracket_inside_a_malformed_title_keep_the_entry_whole():
    raw = '{"books":[{"title":"A"},{"title":"x { } ] y" "z"},{"title":"C"}]}'
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["A", "C"]
    assert [b["n"] for b in read["books"]] == [1, 3]
    assert [(e["position"], e["raw"]) for e in read["errors"]] == [(2, '{"title":"x { } ] y" "z"}')]


def test_invalid_escape_in_the_file_name_does_not_lose_the_books():
    raw = '{"file":"shelf\\q.jpg","books":[{"title":"A"}]}'
    read = parse_read(raw)
    assert read["file"] == ""
    assert [b["title"] for b in read["books"]] == ["A"]
    assert read["complete"] is False


def test_escaped_key_and_nested_metadata_do_not_hide_the_real_books_list():
    escaped = parse_read('{"file":"s.jpg","bo\\u006fks":[{"title":"A"}]}')
    assert [b["title"] for b in escaped["books"]] == ["A"]
    nested = parse_read('{"metadata":{"books":[{"title":"Fake"}]},"books":[{"title":"Real"}]}')
    assert [b["title"] for b in nested["books"]] == ["Real"]
    assert nested["complete"] is True


def test_answer_cut_off_after_the_books_list_is_incomplete_and_keeps_the_books():
    for raw in ('{"file":"s.jpg","books":[{"title":"A"}]', '{"books":[{"title":"A"}],"file":'):
        read = parse_read(raw)
        assert [b["title"] for b in read["books"]] == ["A"]
        assert read["complete"] is False


def test_numbers_and_nesting_that_the_json_decoder_refuses_become_errors_not_exceptions():
    huge = '{"books":[{"n":' + "9" * 5000 + ',"title":"A"},{"title":"B"}]}'
    read = parse_read(huge)
    assert [b["title"] for b in read["books"]] == ["B"]
    assert [e["position"] for e in read["errors"]] == [1]
    assert read["complete"] is False
    deep = '{"books":[{"title":"A"},' + "[" * 100000 + "]" * 100000 + ',{"title":"C"}]}'
    read = parse_read(deep)
    assert [b["title"] for b in read["books"]] == ["A", "C"]
    assert [e["position"] for e in read["errors"]] == [2]
    assert read["complete"] is False
