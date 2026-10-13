"""The books page: live search with filters, and moving or changing the state of several books."""
from contextlib import closing

from store_helpers import NOW, typed_book
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import tags

from home_library import store

HX = {"HX-Request": "true"}


def stock(tmp_path):
    with closing(store.open(tmp_path)) as db:
        typed_book(db, title="Paper Moon", author="A. Writer", language="en", tags="moon, night")
        typed_book(db, title="月とうさぎ", author="山田", language="ja", tags="night", state="Stored")
        store.add_location(db, "Box 3", "box", now=NOW)
        typed_book(db, title="Měsíční člun", language="cs", location_id=2, tags="boat")


def test_books_page_has_a_debounced_live_search_and_filters(client, tmp_path):
    stock(tmp_path)
    page = client.get("/books").text
    form = next(form for form in tags(page, "form") if form.get("id") == "filters")
    assert form["hx-get"] == "/books/results" and "delay:" in form["hx-trigger"] and form["hx-target"] == "#results"
    names = {item.get("name") for item in tags(page, "input") + tags(page, "select")}
    assert {"q", "state", "location_id", "tag"} <= names
    assert "Paper Moon" in page and "月とうさぎ" in page and "Měsíční člun" in page
    assert '<a href="/books/new"' in page


def test_results_are_a_fragment_filtered_by_text_state_location_and_tag(client, tmp_path):
    stock(tmp_path)

    def titles(**query):
        response = client.get("/books/results", params=query, headers=HX)
        assert response.status_code == 200 and "<html" not in response.text
        return [title for title in ("Paper Moon", "月とうさぎ", "Měsíční člun") if title in response.text]

    assert titles() == ["Paper Moon", "月とうさぎ", "Měsíční člun"]
    assert titles(q="moon") == ["Paper Moon"]
    assert titles(q="月") == ["月とうさぎ"]
    assert titles(q="", state="Stored") == ["月とうさぎ"]
    assert titles(location_id="2") == ["Měsíční člun"]
    assert titles(tag="night") == ["Paper Moon", "月とうさぎ"]
    assert titles(q="", state="", location_id="", tag="") == ["Paper Moon", "月とうさぎ", "Měsíční člun"]
    assert "No books match" in client.get("/books/results", params={"q": "nothing like this"}).text
    assert 'lang="ja"' in client.get("/books/results", params={"q": "月"}).text
    bad = client.get("/books/results", params={"state": "Lost"})
    assert bad.status_code == 400 and "state must be one of" in bad.text


def test_a_search_in_the_address_fills_the_form_and_the_first_results(client, tmp_path):
    stock(tmp_path)
    page = client.get("/books", params={"location_id": "2", "q": "člun"}).text
    assert "Měsíční člun" in page and "Paper Moon" not in page
    assert 'value="člun"' in page
    assert any(option.get("value") == "2" and "selected" in option for option in tags(page, "option"))


def test_long_results_offer_the_next_page_instead_of_stopping_silently(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        for number in range(105):
            typed_book(db, title=f"Book {number:03}")
    first = client.get("/books/results", headers=HX).text
    assert "Book 099" in first and "Book 100" not in first
    assert 'hx-get="/books/rows?offset=100' in first
    rest = client.get("/books/rows", params={"offset": "100"}, headers=HX).text
    assert "Book 100" in rest and "Book 104" in rest and "Book 099" not in rest and "hx-get" not in rest


def test_selected_books_move_or_change_state_together(client, tmp_path):
    stock(tmp_path)
    moved = client.post("/books/move", data={"book_ids": ["1", "2"], "location_id": "2", "state": "", "q": "night"}, headers=HX)
    assert moved.status_code == 200 and "Moved 2 books" in moved.text and "<html" not in moved.text
    with closing(store.open(tmp_path)) as db:
        assert [(b["location_id"], b["state"]) for b in map(lambda i: store.book(db, i), (1, 2, 3))] == [
            (2, "Active"), (2, "Stored"), (2, "Active")]
    changed = client.post("/books/move", data={"book_ids": ["1"], "location_id": "", "state": "Retired"}, headers=HX)
    assert changed.status_code == 200 and "Changed 1 book" in changed.text
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["state"] == "Retired" and store.book(db, 1)["version"] == 3


def test_a_refused_move_changes_nothing_and_says_why(client, tmp_path):
    stock(tmp_path)
    nothing = client.post("/books/move", data={"book_ids": ["1"], "location_id": "", "state": ""}, headers=HX)
    assert nothing.status_code == 400 and "choose a location or state" in nothing.text
    none_picked = client.post("/books/move", data={"location_id": "2"}, headers=HX)
    assert none_picked.status_code == 400 and "choose at least one" in none_picked.text.lower()
    missing = client.post("/books/move", data={"book_ids": ["1", "99"], "state": "Stored"}, headers=HX)
    assert missing.status_code == 404
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["state"] == "Active"


def test_books_pages_need_access(anonymous):
    assert anonymous.get("/books").status_code == 401
    assert anonymous.get("/books/results").status_code == 401
    assert anonymous.post("/books/move", data={"book_ids": ["1"], "state": "Stored"}).status_code == 401


def test_after_a_move_the_search_that_was_showing_is_shown_again(client, tmp_path):
    stock(tmp_path)
    page = client.get("/books/results", params={"tag": "night"}, headers=HX).text
    assert 'name="filter_tag" value="night"' in page
    moved = client.post("/books/move", data={"book_ids": ["1"], "location_id": "2", "state": "", "filter_tag": "night"}, headers=HX)
    assert "Paper Moon" in moved.text and "月とうさぎ" in moved.text and "Měsíční člun" not in moved.text
    assert "to Box 3" in moved.text


def test_a_move_with_a_location_that_is_not_a_number_is_refused_before_anything_changes(client, tmp_path):
    stock(tmp_path)
    refused = client.post("/books/move", data={"book_ids": ["1"], "location_id": "box", "state": "Retired"}, headers=HX)
    assert refused.status_code == 400 and "location" in refused.text and "<html" not in refused.text
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["state"] == "Active" and store.book(db, 1)["version"] == 1
