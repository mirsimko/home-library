"""The catalog store keeps private evidence separate from books."""

import pytest
from store_helpers import (
    CAPTURE_ID,
    NOW,
    SECOND_ID,
    capture,
    finish,
    record,
    requeue,
    typed_book,
)
from store_helpers import db as db

from home_library import store


def test_approval_combines_read_title_catalogue_fields_and_cover(db):
    (cover,) = finish(db, [record("Měsíční člun", author="read author")], kind="cover", default_state="Stored")
    (barcode,) = finish(db, [record("", read_status="barcode", catalogue_title="Different catalogue title",
                                   sort_key="Mesicni clun", author="Lenka Testová", publisher="Test Press",
                                   year="2020", isbn="9780000000002", series="Invented voyages", source="test",
                                   source_id="42", age_from="3", age_to="")], SECOND_ID, kind="barcode")
    original_records = [cover["record"], barcode["record"]]
    book = store.approve(db, [cover["id"], barcode["id"]], {}, "reviewer", now=NOW)
    assert book["title"] == "Měsíční člun"
    assert book["sort_key"] == "Mesicni clun" and book["author"] == "Lenka Testová"
    assert (book["publisher"], book["year"], book["isbn"], book["series"]) == (
        "Test Press", "2020", "9780000000002", "Invented voyages")
    assert (book["source"], book["source_id"], book["age_from"], book["age_to"]) == ("test", "42", 3, None)
    assert book["language"] == "cs" and book["location_id"] == 1 and book["state"] == "Stored"
    assert book["cover_capture_id"] == CAPTURE_ID
    assert book["needs_review"] is False and book["reviewed_by"] == "reviewer"
    assert book["created_by"] == "reviewer" and book["created_at"] == book["updated_at"] == NOW
    assert store.observations(db) == []
    used = store.observations(db, "used")
    assert [r["record"] for r in used] == original_records
    assert [r["book_id"] for r in used] == [book["id"], book["id"]]


def test_approval_uses_given_fields_and_the_first_nonempty_read_title(db):
    rows = finish(db, [record("", read_status="unreadable"), record()])
    box = store.add_location(db, "Box B", "box", now=NOW)
    added = store.approve(db, [r["id"] for r in rows], {"title": "Hvězdná bárka", "author": "Typed Author",
                         "location_id": box["id"], "state": "Gone", "needs_review": True}, "reviewer", now=NOW)
    assert (added["title"], added["author"], added["location_id"], added["state"], added["needs_review"]) == (
        "Hvězdná bárka", "Typed Author", box["id"], "Gone", False)
    requeue(db, capture(db)["job"]["id"])
    rows = finish(db, [record("", read_status="unreadable"), record("The Glass Canoe")])
    assert store.approve(db, [r["id"] for r in rows], {}, "reviewer", now=NOW)["title"] == "The Glass Canoe"


def test_approval_requires_nonempty_open_observations_and_is_atomic(db):
    rows = finish(db, [record(), record("The Glass Canoe")])
    for ids, fields, error in [([], {}, store.Invalid), ([rows[0]["id"], 999], {}, store.NotFound),
                               ([rows[0]["id"]], {"unknown": 1}, store.Invalid),
                               ([rows[0]["id"]], {"title": " "}, store.Invalid)]:
        with pytest.raises(error):
            store.approve(db, ids, fields, "reviewer", now=NOW)
        assert store.observations(db) == rows
        assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0
    store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    with pytest.raises(store.Invalid, match="open"):
        store.approve(db, [rows[1]["id"], rows[0]["id"]], {}, "reviewer", now=NOW)
    assert [r["id"] for r in store.observations(db)] == [rows[1]["id"]]
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 1


def test_attach_sets_only_a_missing_cover_and_preserves_personal_edits(db):
    original = typed_book(db, title="The Glass Canoe", notes="person's note", author="Typed Author")
    (cover,) = finish(db, [record("different title")], kind="cover")
    attached = store.attach(db, [cover["id"]], original["id"], "reviewer", now="2026-01-03T00:00:00Z")
    assert attached["cover_capture_id"] == CAPTURE_ID
    assert (attached["title"], attached["notes"], attached["author"]) == (
        "The Glass Canoe", "person's note", "Typed Author")
    assert attached["version"] == 2 and attached["updated_at"] == "2026-01-03T00:00:00Z"
    assert store.observations(db, "used")[0]["book_id"] == original["id"]
    (another,) = finish(db, [record()], SECOND_ID, kind="cover")
    assert store.attach(db, [another["id"]], original["id"], "reviewer", now=NOW) == attached
    with pytest.raises(store.Invalid, match="open"):
        store.attach(db, [another["id"]], original["id"], "reviewer", now=NOW)


def test_dismiss_and_attach_validate_the_whole_selection(db):
    rows = finish(db, [record(), record("The Glass Canoe"), record("Hvězdná bárka")])
    original = typed_book(db)
    for action in (lambda ids: store.dismiss(db, ids, "reviewer"),
                   lambda ids: store.attach(db, ids, original["id"], "reviewer", now=NOW)):
        with pytest.raises(store.NotFound):
            action([rows[0]["id"], 999])
        assert store.observations(db) == rows
    dismissed = store.dismiss(db, [rows[0]["id"], rows[1]["id"]], "reviewer")
    assert [r["status"] for r in dismissed] == ["dismissed", "dismissed"]
    assert [r["id"] for r in store.observations(db, "dismissed")] == [rows[0]["id"], rows[1]["id"]]
    with pytest.raises(store.Invalid, match="open"):
        store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    with pytest.raises(store.Invalid, match="open"):
        store.attach(db, [rows[2]["id"], rows[0]["id"]], original["id"], "reviewer", now=NOW)
    with pytest.raises(store.NotFound):
        store.attach(db, [rows[2]["id"]], 999, "reviewer", now=NOW)
    assert [r["id"] for r in store.observations(db)] == [rows[2]["id"]]
    assert store.book(db, original["id"]) == original


def test_a_rerun_never_changes_used_dismissed_or_edited_books(db):
    rows = finish(db, [record(), record("The Glass Canoe"), record("Hvězdná bárka")])
    approved = store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    edited = store.update_book(db, approved["id"], 1, {"title": "Personal title", "notes": "Keep my edit"},
                               "editor", now=NOW)
    store.dismiss(db, [rows[1]["id"]], "reviewer")
    used = store.observations(db, "used")
    dismissed = store.observations(db, "dismissed")
    requeue(db, capture(db)["job"]["id"])
    finish(db, [record("Machine's new guess")])
    assert store.book(db, edited["id"]) == edited
    assert store.observations(db, "used") == used
    assert store.observations(db, "dismissed") == dismissed
    assert [r["id"] for r in store.observations(db, "superseded")] == [rows[2]["id"]]


def test_observation_filters_and_selections_validate_status_and_capture_ids(db):
    (observation,) = finish(db, [record()])
    with pytest.raises(store.Invalid):
        store.observations(db, status="missing")
    with pytest.raises(store.Invalid):
        store.observations(db, capture_id="../elsewhere")
    for ids in ([], [True], [str(observation["id"])]):
        with pytest.raises(store.Invalid):
            store.dismiss(db, ids, "reviewer")
    assert store.observations(db) == [observation]


def test_superseded_observations_cannot_be_approved_or_attached(db):
    (old,) = finish(db, [record()])
    original = typed_book(db)
    requeue(db, capture(db)["job"]["id"])
    finish(db, [record("Hvězdná bárka")])
    for action in (lambda: store.approve(db, [old["id"]], {}, "reviewer", now=NOW),
                   lambda: store.attach(db, [old["id"]], original["id"], "reviewer", now=NOW)):
        with pytest.raises(store.Invalid, match="open"):
            action()
    assert store.book(db, original["id"]) == original
    assert len(store.observations(db)) == 1


def test_approving_a_barcode_alone_takes_the_catalogue_title_and_leaves_pipeline_notes_out(db):
    (barcode,) = finish(db, [record("", read_status="barcode", catalogue_title="The Invented Lighthouse",
                                   isbn="9780000000002", source="test", source_id="7",
                                   notes="No catalogue age note.")], kind="barcode")
    book = store.approve(db, [barcode["id"]], {}, "reviewer", now=NOW)
    assert book["title"] == "The Invented Lighthouse" and book["isbn"] == "9780000000002"
    assert book["notes"] == ""


THIRD_ID = "10000000-0000-4000-8000-000000000003"


def paired_evidence(db):
    """A cover read by the models, then its barcode: one matched with blanks, one not matched but decoded."""
    (cover,) = finish(db, [record("Měsíční člun", author="read author", publisher="read press", series="read series")],
                      kind="cover", default_state="Stored", now="2026-01-02T03:04:05Z")
    (barcode,) = finish(db, [record("", read_status="barcode", isbn="9780000000002", catalogue_title="Catalogue title")],
                        SECOND_ID, kind="barcode", sha256="b" * 64, now="2026-01-02T03:04:09Z")
    (matched,) = finish(db, [record("", read_status="barcode", isbn="", catalogue_title="Matched title", sort_key="",
                                   author="Lenka Testová", publisher="", year="2020", source="test", source_id="42")],
                        THIRD_ID, kind="barcode", sha256="c" * 64, now="2026-01-02T03:04:12Z")
    return cover, barcode, matched


def test_default_fields_prefer_the_catalogue_match_then_any_row_and_keep_a_decoded_isbn(db):
    cover, barcode, matched = paired_evidence(db)
    fields = store.default_fields(db, [cover["id"], barcode["id"], matched["id"]])
    assert fields["author"] == "Lenka Testová" and fields["year"] == "2020"  # the match beats the earlier reading
    assert (fields["source"], fields["source_id"]) == ("test", "42")
    assert fields["publisher"] == "read press" and fields["series"] == "read series"  # the match is blank there
    assert fields["isbn"] == "9780000000002"  # decoded from a barcode that matched nothing
    assert fields["title"] == "Měsíční člun" and fields["sort_key"] == "Měsíční člun"
    assert fields["notes"] == "" and fields["language"] == "cs"
    assert (fields["location_id"], fields["state"], fields["cover_capture_id"]) == (1, "Stored", CAPTURE_ID)


def test_default_fields_use_the_catalogue_title_when_nothing_was_read_and_do_not_depend_on_the_order_given(db):
    cover, barcode, matched = paired_evidence(db)
    assert store.default_fields(db, [barcode["id"], matched["id"]])["title"] == "Catalogue title"
    ids = [cover["id"], barcode["id"], matched["id"]]
    assert store.default_fields(db, ids) == store.default_fields(db, ids[::-1]) == store.default_fields(db, ids[1:] + ids[:1])
    with pytest.raises(store.NotFound):
        store.default_fields(db, [999])
    with pytest.raises(store.Invalid):
        store.default_fields(db, [])


def test_approval_fills_a_book_with_the_same_rule_whatever_order_the_evidence_comes_in(db):
    cover, barcode, matched = paired_evidence(db)
    expected = store.default_fields(db, [cover["id"], barcode["id"], matched["id"]])
    book = store.approve(db, [matched["id"], barcode["id"], cover["id"]], {"author": "Typed Author"}, "reviewer", now=NOW)
    assert book["author"] == "Typed Author"
    for key in ("title", "sort_key", "publisher", "year", "isbn", "series", "source", "source_id", "language",
                "location_id", "state", "cover_capture_id"):
        assert book[key] == expected[key], key
