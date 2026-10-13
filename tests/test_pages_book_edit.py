"""Adding a book by hand, editing one with the version check, and what a conflict shows."""
from contextlib import closing

from store_helpers import NOW, typed_book
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import tags

from home_library import store


def form_values(page, form_id="book-form"):
    """What a browser would post for the page's form: every named input, select (first option unless selected) and text area."""
    from html.parser import HTMLParser

    values = {}

    class Collect(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inside = False
            self.select = None
            self.area = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "form":
                self.inside = attrs.get("id") == form_id
            if not self.inside:
                return
            if tag == "input" and attrs.get("name") and attrs.get("type") != "checkbox":
                values[attrs["name"]] = attrs.get("value", "")
            if tag == "input" and attrs.get("type") == "checkbox" and "checked" in attrs:
                values[attrs["name"]] = attrs.get("value", "on")
            if tag == "select":
                self.select = attrs["name"]
                values.setdefault(self.select, None)
            if tag == "option" and self.select and (values[self.select] is None or "selected" in attrs):
                values[self.select] = attrs.get("value", "")
            if tag == "textarea":
                self.area = attrs["name"]
                values[self.area] = ""

        def handle_data(self, data):
            if self.area:
                values[self.area] += data

        def handle_endtag(self, tag):
            if tag == "select":
                self.select = None
            if tag == "textarea":
                self.area = None

    Collect().feed(page)
    return values


def test_a_book_is_added_by_hand_and_the_form_keeps_what_was_typed_when_refused(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        store.add_location(db, "Shelf A", "shelf", now=NOW)
    page = client.get("/books/new")
    assert page.status_code == 200 and 'id="book-form"' in page.text and 'name="version"' not in page.text
    values = form_values(page.text)
    assert values["state"] == "Active" and values["location_id"] == "1" and values["needs_review"] == "0"
    refused = client.post("/books", data={**values, "title": "  ", "author": "A. Writer"})
    assert refused.status_code == 400 and "book title must not be empty" in refused.text
    assert 'value="A. Writer"' in refused.text
    created = client.post("/books", data={**values, "title": "Paper Moon", "age_from": "3", "tags": "moon,  night",
                                          "language": "en"}, follow_redirects=False)
    assert created.status_code == 303 and created.headers["location"] == "/books/1"
    with closing(store.open(tmp_path)) as db:
        book = store.book(db, 1)
    assert (book["title"], book["age_from"], book["tags"], book["created_by"]) == ("Paper Moon", 3, "moon, night", "parent")


def test_a_book_page_shows_the_record_with_its_version_and_saves_only_what_changed(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db, title="月とうさぎ", author="山田", language="ja", age_from=4)
    page = client.get("/books/1")
    assert page.status_code == 200
    values = form_values(page.text)
    assert values["version"] == "1" and values["title"] == "月とうさぎ" and values["age_from"] == "4"
    assert any(item.get("name") == "title" and item.get("lang") == "ja" for item in tags(page.text, "input"))
    saved = client.post("/books/1", data={**values, "notes": "Signed by the author", "needs_review": "1"},
                        follow_redirects=False)
    assert saved.status_code == 303 and saved.headers["location"] == "/books/1?saved=1"
    with closing(store.open(tmp_path)) as db:
        book = store.book(db, 1)
    assert (book["notes"], book["needs_review"], book["version"], book["reviewed_by"]) == ("Signed by the author", True, 2, "parent")
    assert "Saved" in client.get("/books/1?saved=1").text
    nothing = client.post("/books/1", data=form_values(client.get("/books/1").text), follow_redirects=False)
    assert nothing.status_code == 303
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["version"] == 2


def test_a_refused_edit_stays_on_the_form_with_the_users_values(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db)
    values = form_values(client.get("/books/1").text)
    refused = client.post("/books/1", data={**values, "title": " ", "author": "New author", "age_from": "many"})
    assert refused.status_code == 400 and 'value="New author"' in refused.text
    assert 'name="version" value="1"' in refused.text
    assert client.post("/books/99", data=values).status_code == 404
    assert client.get("/books/99").status_code == 404


def test_a_stale_edit_shows_the_stored_values_beside_the_users_and_can_be_reapplied(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db, title="Paper Moon", author="A. Writer", publisher="Old House")
    mine = form_values(client.get("/books/1").text)
    with closing(store.open(tmp_path)) as db:
        store.update_book(db, 1, 1, {"author": "B. Painter", "publisher": "New House"}, "other")
    conflict = client.post("/books/1", data={**mine, "author": "C. Poet", "notes": "My note"})
    assert conflict.status_code == 409
    page = conflict.text
    assert "changed while you were editing" in page
    assert "B. Painter" in page and "C. Poet" in page and "My note" in page
    assert "New House" not in page  # not edited by this person, so not part of the comparison
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["author"] == "B. Painter"
    reapply = form_values(page, "reapply-form")
    assert reapply["version"] == "2" and reapply["author"] == "C. Poet" and reapply["notes"] == "My note"
    assert "title" not in reapply and "publisher" not in reapply
    done = client.post("/books/1/reapply", data=reapply, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == "/books/1?saved=1"
    with closing(store.open(tmp_path)) as db:
        book = store.book(db, 1)
    assert (book["author"], book["notes"], book["publisher"], book["version"]) == ("C. Poet", "My note", "New House", 3)
    again = client.post("/books/1/reapply", data=reapply)
    assert again.status_code == 409 and "changed while you were editing" in again.text


def test_book_edit_pages_need_access(anonymous):
    assert anonymous.get("/books/new").status_code == 401
    assert anonymous.get("/books/1").status_code == 401
    assert anonymous.post("/books", data={"title": "x"}).status_code == 401
    assert anonymous.post("/books/1", data={"title": "x"}).status_code == 401
