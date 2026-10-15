"""The catalog store keeps private evidence separate from books."""

import pytest
from store_helpers import (
    CAPTURE_ID,
    NOW,
    typed_book,
)
from store_helpers import db as db

from home_library import store


def test_a_book_typed_by_hand_is_a_plain_versioned_record(db):
    added = typed_book(db, author="Lenka Testová", age_from="3", age_to="8", tags="moon, boats")
    assert isinstance(added, dict)
    assert added["title"] == added["sort_key"] == "Měsíční člun"
    assert added["state"] == "Active"
    assert added["version"] == 1
    assert added["created_by"] == "parent"
    assert added["created_at"] == added["updated_at"] == NOW
    assert added["age_from"] == 3 and added["age_to"] == 8
    assert isinstance(added["needs_review"], bool)
    assert store.book(db, added["id"]) == added
    with pytest.raises(store.NotFound):
        store.book(db, 999)
    for state in ("Stored", "Retired", "Gone"):
        assert typed_book(db, state=state)["state"] == state


@pytest.mark.parametrize("changes", [
    {"title": " \n\t "}, {"title": None}, {"state": "lost"}, {"unknown": "x"}, {"version": 7},
    {"author": []}, {"age_from": "three"}, {"age_to": 2.5}, {"age_from": "9", "age_to": "3"}, {"needs_review": "false"},
])
def test_invalid_book_fields_leave_no_book(db, changes):
    with pytest.raises(store.Invalid):
        typed_book(db, **changes)
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0


def test_books_require_a_location_and_a_cover_capture_when_given(db):
    with pytest.raises(store.NotFound):
        typed_book(db, location_id=999)
    with pytest.raises(store.Invalid, match="location"):
        store.add_book(db, {"title": "Hvězdná bárka"}, "parent", now=NOW)
    with pytest.raises(store.NotFound):
        typed_book(db, cover_capture_id=CAPTURE_ID)
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0


def test_edits_are_partial_versioned_and_attributed(db):
    original = typed_book(db, notes="keep this", age_from=3)
    changed = store.update_book(db, original["id"], 1, {"title": " Hvězdná bárka ", "state": "Gone"},
                                "editor", now="2026-01-03T00:00:00Z")
    assert changed["title"] == "Hvězdná bárka" and changed["state"] == "Gone"
    assert changed["notes"] == "keep this" and changed["age_from"] == 3
    assert changed["version"] == 2 and changed["reviewed_by"] == "editor"
    assert changed["created_by"] == "parent" and changed["created_at"] == NOW
    assert changed["updated_at"] == "2026-01-03T00:00:00Z"
    with pytest.raises(store.Conflict):
        store.update_book(db, original["id"], 1, {"notes": "stale overwrite"}, "other", now=NOW)
    assert store.book(db, original["id"]) == changed


@pytest.mark.parametrize("changes", [{"unknown": "x"}, {"created_by": "x"}, {"version": 9},
                                     {"title": " "}, {"state": "lost"}, {"location_id": None}])
def test_invalid_edits_leave_the_book_and_version_unchanged(db, changes):
    original = typed_book(db)
    with pytest.raises(store.Invalid):
        store.update_book(db, original["id"], 1, changes, "editor", now=NOW)
    assert store.book(db, original["id"]) == original


def test_editing_a_missing_book_or_moving_to_a_missing_location_is_refused(db):
    with pytest.raises(store.NotFound):
        store.update_book(db, 999, 1, {"title": "Hvězdná bárka"}, "editor", now=NOW)
    original = typed_book(db)
    with pytest.raises(store.NotFound):
        store.update_book(db, original["id"], 1, {"location_id": 999}, "editor", now=NOW)
    assert store.book(db, original["id"]) == original


def test_books_move_together_and_each_editing_version_advances(db):
    first = typed_book(db)
    second = typed_book(db, title="The Glass Canoe")
    box = store.add_location(db, "Box B", "box", now=NOW)
    moved = store.move_books(db, [second["id"], first["id"]], box["id"], "Stored", by="mover", now=NOW)
    assert [r["id"] for r in moved] == [second["id"], first["id"]]
    for book in moved:
        assert (book["location_id"], book["state"], book["version"], book["reviewed_by"]) == (
            box["id"], "Stored", 2, "mover")
    gone = store.move_books(db, [first["id"]], state="Gone", by="mover", now=NOW)[0]
    assert gone["location_id"] == box["id"] and gone["version"] == 3
    relocated = store.move_books(db, [second["id"]], location_id=1, by="mover", now=NOW)[0]
    assert relocated["state"] == "Stored" and relocated["location_id"] == 1


def test_an_invalid_batch_move_changes_no_book(db):
    original = typed_book(db)
    for ids, changes, error in [([original["id"], 999], {"state": "Stored"}, store.NotFound),
                               ([original["id"]], {"location_id": 999}, store.NotFound),
                               ([original["id"]], {"state": "lost"}, store.Invalid),
                               ([original["id"]], {}, store.Invalid), ([], {"state": "Gone"}, store.Invalid)]:
        with pytest.raises(error):
            store.move_books(db, ids, **changes, by="mover", now=NOW)
        assert store.book(db, original["id"]) == original


@pytest.mark.parametrize("id", ["1", [], True, None])
def test_book_and_location_ids_must_be_integer_keys(db, id):
    original = typed_book(db)
    with pytest.raises(store.Invalid, match="integer"):
        store.book(db, id)
    with pytest.raises(store.Invalid, match="integer"):
        store.update_book(db, original["id"], 1, {"location_id": id}, "editor", now=NOW)
    assert store.book(db, original["id"]) == original


@pytest.mark.parametrize("version", [True, "1", None, 1.0])
def test_an_editing_version_must_be_an_integer(db, version):
    original = typed_book(db)
    with pytest.raises(store.Invalid, match="version"):
        store.update_book(db, original["id"], version, {"notes": "bad version"}, "editor", now=NOW)
    assert store.book(db, original["id"]) == original
