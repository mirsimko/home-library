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


def cand(cid, title, **over):
    c = {"id": cid, "source": cid.split(":")[0], "source_id": cid.split(":")[1], "url": "", "title": title,
         "title_reading": "", "authors": [], "publisher": "", "year": "", "isbn": "", "series": "",
         "language": "cs", "audience": "", "age_note": "", "subjects": [], "summary": ""}
    c.update(over)
    return c


def candidates_of(*candidates, item=0):
    return {"file": "shelf-1.jpg", "books": [
        {"item": item, "title": "x", "language": "cs", "queries": [], "candidates": list(candidates)}]}


def picks_of(verdict, candidate_id=None, reason="r", item=0):
    return {"file": "shelf-1.jpg", "picks": [
        {"item": item, "verdict": verdict, "candidate_id": candidate_id, "reason": reason}]}


def test_a_matched_candidate_fills_the_catalogue_fields_and_the_sort_key():
    merged = merged_of([item("agreed", "あかいふうせん", [reading("a-sol", 1, "あかいふうせん", language="ja"),
                                                        reading("b-spark", 2, "あかいふうせん", language="ja")],
                             language="ja")])
    candidates = candidates_of(
        cand("ndl:000111", "あかいふうせん", title_reading="アカイ フウセン", authors=["山田, 花子", "鈴木, 太郎"],
             publisher="青空社", year="2008", isbn="9784000000001", series="えほんシリーズ"),
        cand("ndl:000222", "あかいふうせん 2"))
    (record,) = build_records(merged, candidates, picks_of("match", "ndl:000111"))
    assert record["catalogue_title"] == "あかいふうせん"
    assert record["author"] == "山田, 花子; 鈴木, 太郎"
    assert record["publisher"] == "青空社"
    assert record["year"] == "2008"
    assert record["isbn"] == "9784000000001"
    assert record["series"] == "えほんシリーズ"
    assert record["source"] == "ndl"
    assert record["source_id"] == "000111"
    assert record["sort_key"] == "アカイ フウセン"
    assert record["pick_verdict"] == "match"
    assert record["candidate_count"] == 2


def test_the_title_stays_the_reading_when_the_catalogue_title_differs():
    candidates = candidates_of(cand("nkcr:cnb001", "Zelený drak a jiné pohádky", title_reading=""))
    (record,) = build_records(merged_of([agreed()]), candidates, picks_of("match", "nkcr:cnb001"))
    assert record["title"] == "Zelený drak"
    assert record["catalogue_title"] == "Zelený drak a jiné pohádky"
    assert record["sort_key"] == "Zelený drak"


def test_a_pick_of_none_or_ambiguous_fills_no_catalogue_field():
    candidates = candidates_of(cand("nkcr:cnb001", "Zelený drak", authors=["Novotná, Marta"], publisher="Albatros",
                                    year="2001", isbn="9788000000001", series="Malá knihovna",
                                    title_reading="Zeleny drak"))
    for verdict in ["none", "ambiguous"]:
        (record,) = build_records(merged_of([agreed()]), candidates, picks_of(verdict))
        for column in ["catalogue_title", "author", "publisher", "year", "isbn", "series", "source",
                       "source_id", "age_from", "age_to"]:
            assert record[column] == "", column
        assert record["sort_key"] == "Zelený drak"
        assert record["pick_verdict"] == verdict
        assert record["candidate_count"] == 1


def test_age_from_and_age_to_come_from_the_matched_candidates_age_note():
    for note, low, high in [("Pro děti od 3 let", "3", ""), ("Pro děti 5-8 let", "5", "8"),
                            ("Pro čtenáře", "", "")]:
        candidates = candidates_of(cand("nkcr:cnb001", "Zelený drak", age_note=note))
        (record,) = build_records(merged_of([agreed()]), candidates, picks_of("match", "nkcr:cnb001"))
        assert (record["age_from"], record["age_to"]) == (low, high), note


def near_item():
    return item("near", "The Blue Kite", [reading("a-sol", 3, "The Blue Kite", language="en"),
                                          reading("b-spark", 5, "The Blue Kyte", language="en")],
                language="en", exact=False)


def test_other_reading_holds_the_second_title_of_a_near_pair_only():
    near, same = build_records(merged_of([near_item(), agreed()]))
    assert near["other_reading"] == "The Blue Kyte"
    assert near["read_status"] == "near"
    assert same["other_reading"] == ""


def test_notes_say_why_a_read_status_needs_a_look():
    solo = item("solo", "The Blue Kite", [reading("b-spark", 7, "The Blue Kite", language="en")], language="en",
                exact=False)
    partial = item("partial", "Zelený", [reading("a-sol", 2, "Zelený", readable="partial")], exact=False)
    records = build_records(merged_of([solo, near_item(), partial, agreed()]))
    assert [r["notes"] for r in records] == [
        "Only b-spark gave this title.", "The two reads differ.", "Partly legible.", ""]


def test_notes_quote_the_first_guess_in_inferred():
    guessed = item("partial", "Zelený", [reading("a-sol", 2, "Zelený", readable="partial", inferred=""),
                                         reading("b-spark", 3, "Zelený", readable="partial", inferred="Zelený drak"),
                                         ], exact=False)
    (record,) = build_records(merged_of([guessed]))
    assert record["notes"] == "Partly legible. Guess: Zelený drak."


def test_notes_give_the_reason_of_an_ambiguous_match_and_the_audience_of_a_matched_candidate():
    ambiguous = build_records(
        merged_of([agreed()]), candidates_of(cand("nkcr:cnb001", "Zelený drak")),
        picks_of("ambiguous", reason="Two editions with the same publisher."))
    assert ambiguous[0]["notes"] == "Catalogue match ambiguous: Two editions with the same publisher."
    candidates = candidates_of(cand("nkcr:cnb001", "Zelený drak", audience="Děti", age_note="Pro děti od 3 let"))
    (matched,) = build_records(merged_of([agreed()]), candidates, picks_of("match", "nkcr:cnb001"))
    assert matched["notes"] == "Catalogue audience: Děti. Catalogue age note: Pro děti od 3 let."
    unmatched = build_records(merged_of([agreed()]), candidates, picks_of("none"))
    assert unmatched[0]["notes"] == ""


def test_location_is_passed_through_to_every_record():
    records = build_records(merged_of([agreed(), near_item()]), location="Kids room, shelf 2")
    assert [r["location"] for r in records] == ["Kids room, shelf 2"] * 2
    assert build_records(merged_of([agreed()]))[0]["location"] == ""


def test_unreadable_entries_of_the_first_read_follow_the_items():
    unreadable = [reading("b-spark", 6, "", where="r2c1-r0.jpg, #6", other_text="red spine", readable="no"),
                  reading("a-sol", 9, "", where="r2c2-r0.jpg, #9", other_text="gold letters", readable="no"),
                  reading("a-sol", 11, "", where="r2c3-r0.jpg, #11", readable="no")]
    records = build_records(merged_of([agreed(), near_item()], unreadable), location="Hall")
    assert [r["title"] for r in records] == ["Zelený drak", "The Blue Kite", "", ""]
    first = records[2]
    assert first["read_status"] == "unreadable"
    assert first["other_text"] == "gold letters"
    assert first["where"] == "r2c2-r0.jpg, #9"
    assert first["read_ids"] == "a-sol"
    assert first["photo"] == "shelf-1.jpg"
    assert first["location"] == "Hall"
    assert first["needs_review"] is True and first["candidate_count"] == 0
    assert first["notes"] == "Could not be read from the shelf photo; needs a cover photo."
    assert set(first) == set(COLUMNS)
