"""The locations page: a list with book counts, adding, and renaming in place."""
from contextlib import closing

from store_helpers import typed_book
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import tags

from home_library import store


def names(tmp_path):
    with closing(store.open(tmp_path)) as db:
        return [(row["name"], row["kind"], row["books"]) for row in store.locations_with_counts(db)]


def test_locations_page_lists_names_kinds_and_book_counts(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db)
        typed_book(db, title="Glass Cloud")
        store.add_location(db, "Box 3", "box")
    page = client.get("/locations").text
    assert "Shelf A" in page and "Box 3" in page
    assert 'data-books="2"' in page and 'data-books="0"' in page
    form = [form for form in tags(page, "form") if form.get("hx-post") == "/locations"]
    assert len(form) == 1
    assert {"name", "kind"} <= {item.get("name") for item in tags(page, "input") + tags(page, "select")}


def test_adding_a_location_returns_the_new_list_and_a_refused_one_says_why(client, tmp_path):
    added = client.post("/locations", data={"name": "  Hall shelf ", "kind": "shelf"}, headers={"HX-Request": "true"})
    assert added.status_code == 200
    assert "Hall shelf" in added.text and 'id="locations"' in added.text and "<html" not in added.text
    assert names(tmp_path) == [("Hall shelf", "shelf", 0)]
    duplicate = client.post("/locations", data={"name": "Hall shelf", "kind": "box"}, headers={"HX-Request": "true"})
    assert duplicate.status_code == 400 and "already exists" in duplicate.text and "Hall shelf" in duplicate.text
    blank = client.post("/locations", data={"name": " ", "kind": "shelf"}, headers={"HX-Request": "true"})
    assert blank.status_code == 400 and "must not be empty" in blank.text
    assert names(tmp_path) == [("Hall shelf", "shelf", 0)]


def test_a_location_is_renamed_in_place_without_moving_its_books(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db)
        store.add_location(db, "Box 3", "box")
    edit = client.get("/locations/1/edit")
    assert edit.status_code == 200 and 'value="Shelf A"' in edit.text and 'hx-post="/locations/1/rename"' in edit.text
    assert "<html" not in edit.text
    assert 'id="location-1"' in client.get("/locations/1/row").text
    renamed = client.post("/locations/1/rename", data={"name": "Living room shelf"}, headers={"HX-Request": "true"})
    assert renamed.status_code == 200 and "Living room shelf" in renamed.text and 'data-books="1"' in renamed.text
    assert names(tmp_path) == [("Box 3", "box", 0), ("Living room shelf", "shelf", 1)]
    clash = client.post("/locations/1/rename", data={"name": "Box 3"}, headers={"HX-Request": "true"})
    assert clash.status_code == 400 and "already exists" in clash.text and 'value="Box 3"' in clash.text
    assert client.get("/locations/99/edit").status_code == 404
    assert client.post("/locations/99/rename", data={"name": "Nowhere"}).status_code == 404


def test_locations_pages_need_access(anonymous):
    assert anonymous.get("/locations").status_code == 401
    assert anonymous.post("/locations", data={"name": "X", "kind": "box"}).status_code == 401
