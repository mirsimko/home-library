"""The catalog store keeps private evidence separate from books."""

import pytest
from store_helpers import (
    CAPTURE_ID,
    EXPORT_COLUMNS,
    NOW,
    capture,
    typed_book,
)
from store_helpers import db as db

from home_library import store


def test_search_uses_trigrams_and_short_japanese_queries(db):
    czech = typed_book(db, title="Měsíční člun", sort_key="a")
    japanese = typed_book(db, title="ぐぽ", sort_key="b")
    author = typed_book(db, title="The Glass Canoe", sort_key="c", author="Invented Author", series="Silver boats")
    statements = []
    db.set_trace_callback(statements.append)
    assert store.search_books(db, "ěsí") == [czech]
    assert any("books_fts" in sql and "MATCH" in sql for sql in statements)
    assert db.execute("SELECT sql FROM sqlite_master WHERE name = 'books_fts'").fetchone()[0].find("trigram") >= 0
    statements.clear()
    assert store.search_books(db, "ぐぽ") == [japanese]
    assert any("LIKE" in sql for sql in statements)
    assert not any("MATCH" in sql for sql in statements)
    db.set_trace_callback(None)
    assert store.search_books(db, "ěs") == [czech]
    assert store.search_books(db, "Author") == [author]
    assert store.search_books(db, "boats") == [author]
    assert store.search_books(db, "missing") == []
    assert store.search_books(db, "a") == [czech, author]


def test_search_filters_tags_state_location_and_pages_in_catalog_order(db):
    store.add_location(db, "Shelf A", "shelf", now=NOW)
    box = store.add_location(db, "Box B", "box", now=NOW)
    first = typed_book(db, title="Alpha invented", sort_key="a", tags="moon, boats", state="Stored")
    second = typed_book(db, title="Beta invented", sort_key="a", tags="moonlight", location_id=box["id"])
    third = typed_book(db, title="Gamma invented", sort_key="c", tags="moon", location_id=box["id"], state="Gone")
    assert store.search_books(db) == [first, second, third]
    assert store.search_books(db, tag="moon") == [first, third]
    assert store.search_books(db, state="Stored", tag="moon", location_id=1) == [first]
    assert store.search_books(db, location_id=box["id"]) == [second, third]
    assert store.search_books(db, "invented", state="Gone", tag="moon") == [third]
    assert store.search_books(db, limit=1, offset=1) == [second]


def test_fts_tracks_updates_and_deletes_of_all_its_columns(db):
    original = typed_book(db, title="First vessel", sort_key="first key", author="First writer",
                          series="First series", isbn="111111")
    changed = store.update_book(db, original["id"], 1, {"title": "Second vessel", "sort_key": "second key",
                                "author": "Second writer", "series": "Second series", "isbn": "222222"},
                                "editor", now=NOW)
    for query in ("First", "111111"):
        assert store.search_books(db, query) == []
    for query in ("Second vessel", "second key", "Second writer", "Second series", "222222"):
        assert store.search_books(db, query) == [changed]
    # There is no public delete function; exercise the specified database trigger directly.
    with db:
        db.execute("DELETE FROM books WHERE id = ?", (original["id"],))
    assert store.search_books(db, "Second") == []
    assert db.execute("SELECT rowid FROM books_fts WHERE books_fts MATCH 'Second'").fetchall() == []


def test_export_is_flat_in_spec_order_and_uses_the_current_location_name(db):
    assert store.export_rows(db) == []
    capture(db, kind="cover", media_type="image/png")
    typed_book(db, title="=Invented title", sort_key="b", illustrator="Test Artist", publisher="Test Press",
               year="2020", language="cs", isbn="9780000000002", series="Test Series", age_from=3, age_to=8,
               tags="moon", state="Gone", cover_capture_id=CAPTURE_ID, source="test", source_id="42", notes="typed")
    store.rename_location(db, 1, "New Shelf")
    (row,) = store.export_rows(db)
    assert list(row) == EXPORT_COLUMNS
    assert row == dict(zip(EXPORT_COLUMNS, ["=Invented title", "b", "", "Test Artist", "Test Press", "2020", "cs",
                       "9780000000002", "Test Series", 3, 8, "moon", "Gone", "New Shelf",
                       f"captures/{CAPTURE_ID}.png", "test", "42", False, "typed"]))
    typed_book(db, title="The Glass Canoe", sort_key="a")
    exported = store.export_rows(db)
    assert [r["title"] for r in exported] == ["The Glass Canoe", "=Invented title"]
    assert exported[0]["cover_photo"] == "" and exported[0]["age_from"] is None


@pytest.mark.parametrize("parameters", [{"query": 3}, {"state": "lost"}, {"limit": -1}, {"offset": -1},
                                       {"limit": "all"}, {"tag": []}])
def test_search_rejects_invalid_filters_and_pagination(db, parameters):
    with pytest.raises(store.Invalid):
        store.search_books(db, **parameters)


def test_search_treats_user_text_as_literal_and_tags_as_trimmed_tokens(db):
    percent = typed_book(db, title="The 100% Canoe", tags=" moon,   paper boats , ")
    underscore = typed_book(db, title='The _ "Canoe"')
    assert percent["tags"] == "moon, paper boats"
    assert store.search_books(db, "%") == [percent]
    assert store.search_books(db, "_") == [underscore]
    assert store.search_books(db, '"Canoe"') == [underscore]
    assert store.search_books(db, 'Canoe" OR "missing') == []
    assert store.search_books(db, tag="paper boats") == [percent]
