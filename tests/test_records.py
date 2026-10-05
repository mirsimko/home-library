from home_library.records import COLUMNS, build_records


def reading(read_id, n, title, **over):
    r = {"read_id": read_id, "n": n, "where": f"r1c1-r0.jpg, #{n}", "visible": "spine", "title": title,
         "other_text": "", "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}
    r.update(over)
    return r


def item(reason, title, readings, language="cs", exact=True):
    return {"status": "accepted" if reason == "agreed" else "review", "reason": reason, "title": title,
            "language": language, "exact": exact, "readings": readings}


def merged_of(items, unreadable=()):
    return {"file": "shelf-1.jpg", "reads": ["a-sol", "b-spark"], "items": list(items),
            "unreadable": list(unreadable), "parse_errors": []}


def agreed():
    return item("agreed", "Zelený drak", [reading("a-sol", 1, "Zelený drak", other_text="Albatros"),
                                          reading("b-spark", 4, "Zelený drak")])


def test_an_agreed_item_without_lookup_data_becomes_a_record_to_review():
    (record,) = build_records(merged_of([agreed()]))
    assert set(record) == set(COLUMNS)
    assert record["title"] == "Zelený drak"
    assert record["language"] == "cs"
    assert record["read_status"] == "agreed"
    assert record["read_ids"] == "a-sol; b-spark"
    assert record["needs_review"] is True
    assert record["sort_key"] == "Zelený drak"
    assert record["candidate_count"] == 0
    assert record["photo"] == "shelf-1.jpg"
    assert record["other_text"] == "Albatros"
    assert record["where"] == "r1c1-r0.jpg, #1"
    assert record["pick_verdict"] == ""
    assert record["notes"] == ""
