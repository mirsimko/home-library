"""Approve, attach and dismiss from the review page, and where each one leaves the reviewer."""
from contextlib import closing

from store_helpers import SECOND_ID, typed_book
from test_pages_review import stock
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import form_values, tags

from home_library import store

HX = {"HX-Request": "true"}


def statuses(tmp_path):
    with closing(store.open(tmp_path)) as db:
        return {row["id"]: row["status"] for status in ("open", "used", "dismissed")
                for row in store.observations(db, status)}


def test_approving_makes_one_book_from_the_form_and_goes_to_the_next_observation(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    page = client.get(f"/review/{cover[0]['id']}").text
    values = form_values(page, "approve-form")
    posted = {**values, "title": "Paper Moon, corrected", "tags": "moon", "also": str(barcode[0]["id"])}
    response = client.post(f"/review/{cover[0]['id']}/approve", data=posted, headers=HX)
    assert response.status_code == 204
    assert response.headers["hx-redirect"] == f"/review/{shelf[0]['id']}?done=approved&book=1"
    with closing(store.open(tmp_path)) as db:
        book = store.book(db, 1)
    assert (book["title"], book["tags"], book["isbn"], book["reviewed_by"]) == ("Paper Moon, corrected", "moon", "9780000000002", "parent")
    assert book["cover_capture_id"] == SECOND_ID and book["needs_review"] is False
    assert statuses(tmp_path)[cover[0]["id"]] == "used" and statuses(tmp_path)[barcode[0]["id"]] == "used"
    landed = client.get(response.headers["hx-redirect"]).text
    assert "Approved as a new book" in landed and 'href="/books/1"' in landed


def test_a_plain_form_post_is_redirected_and_the_last_row_goes_back_to_an_earlier_one(client, tmp_path):
    shelf, _, _ = stock(tmp_path)
    values = form_values(client.get(f"/review/{shelf[1]['id']}").text, "approve-form")
    response = client.post(f"/review/{shelf[1]['id']}/approve", data=values, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/review/{shelf[0]['id']}?done=approved&book=1"


def test_the_inbox_is_shown_when_nothing_else_is_open(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        from store_helpers import finish, record

        (row,) = finish(db, [record("Paper Moon")])
    values = form_values(client.get(f"/review/{row['id']}").text, "approve-form")
    response = client.post(f"/review/{row['id']}/approve", data=values, headers=HX)
    assert response.headers["hx-redirect"] == "/review?done=approved&book=1"
    assert "Approved as a new book" in client.get(response.headers["hx-redirect"]).text


def test_unticking_a_paired_photo_takes_its_values_out_of_the_form_and_leaves_it_open(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    cover_id, barcode_id = cover[0]["id"], barcode[0]["id"]
    both = client.get(f"/review/{cover_id}").text
    assert form_values(both, "approve-form")["isbn"] == "9780000000002"
    (box,) = [item for item in tags(both, "input") if item.get("name") == "also"]
    assert "checked" in box and box["hx-get"] == f"/review/{cover_id}" and box["hx-target"] == "#review"
    alone = client.get(f"/review/{cover_id}?without={barcode_id}").text
    values = form_values(alone, "approve-form")
    assert values["isbn"] == "" and values["title"] == "Paper Moon" and "also" not in values
    (box,) = [item for item in tags(alone, "input") if item.get("name") == "also"]
    assert box["value"] == str(barcode_id) and "checked" not in box
    assert f'href="/review/{barcode_id}"' in alone  # still listed as the same book, only not ticked
    response = client.post(f"/review/{cover_id}/approve", data=values, headers=HX)
    assert response.status_code == 204
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["isbn"] == ""
    assert statuses(tmp_path)[cover_id] == "used" and statuses(tmp_path)[barcode_id] == "open"


def test_ticking_both_photos_again_uses_both_and_a_bad_exclusion_is_refused(client, tmp_path):
    _, cover, barcode = stock(tmp_path)
    cover_id, barcode_id = cover[0]["id"], barcode[0]["id"]
    barcode_alone = client.get(f"/review/{barcode_id}?without={cover_id}").text
    assert form_values(barcode_alone, "approve-form")["title"] == "Paper Moon (catalogue)"
    unrelated = client.get(f"/review/{cover_id}?without=999")  # not a paired photo: nothing to leave out
    assert unrelated.status_code == 200 and form_values(unrelated.text, "approve-form")["isbn"] == "9780000000002"
    assert client.get(f"/review/{cover_id}?without=abc").status_code == 400
    values = form_values(client.get(f"/review/{cover_id}").text, "approve-form")
    assert client.post(f"/review/{cover_id}/approve", data=values, headers=HX).status_code == 204
    assert statuses(tmp_path)[cover_id] == "used" and statuses(tmp_path)[barcode_id] == "used"


def test_a_refused_approval_says_why_and_changes_nothing(client, tmp_path):
    shelf, cover, _ = stock(tmp_path)
    values = form_values(client.get(f"/review/{shelf[0]['id']}").text, "approve-form")
    blank = client.post(f"/review/{shelf[0]['id']}/approve", data={**values, "title": " "}, headers=HX)
    assert blank.status_code == 400 and "book title must not be empty" in blank.text and "<html" not in blank.text
    bad_age = client.post(f"/review/{shelf[0]['id']}/approve", data={**values, "age_from": "many"}, headers=HX)
    assert bad_age.status_code == 400 and "age_from" in bad_age.text
    taken = client.post(f"/review/{shelf[0]['id']}/approve", data={**values, "also": "abc"}, headers=HX)
    assert taken.status_code == 400
    missing = client.post(f"/review/{shelf[0]['id']}/approve", data={**values, "also": "999"}, headers=HX)
    assert missing.status_code == 404
    assert set(statuses(tmp_path).values()) == {"open"}
    with closing(store.open(tmp_path)) as db:
        assert store.search_books(db) == []


def test_dismissing_marks_only_this_observation_and_goes_to_the_next(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    response = client.post(f"/review/{cover[0]['id']}/dismiss", headers=HX)
    assert response.status_code == 204
    assert response.headers["hx-redirect"] == f"/review/{barcode[0]['id']}?done=dismissed"
    assert statuses(tmp_path)[cover[0]["id"]] == "dismissed" and statuses(tmp_path)[barcode[0]["id"]] == "open"
    assert "Dismissed" in client.get(response.headers["hx-redirect"]).text
    again = client.post(f"/review/{cover[0]['id']}/dismiss", headers=HX)
    assert again.status_code == 400 and "is not open" in again.text
    assert client.post("/review/999/dismiss", headers=HX).status_code == 404


def test_attaching_searches_the_books_and_uses_the_observation_for_the_chosen_one(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    with closing(store.open(tmp_path)) as db:
        typed_book(db, title="Paper Moon", author="A. Writer", language="en")
        typed_book(db, title="Glass Cloud")
    page = client.get(f"/review/{cover[0]['id']}").text
    assert 'hx-get="/review/%d/attach-search"' % cover[0]["id"] in page
    found = client.get(f"/review/{cover[0]['id']}/attach-search", params={"q": "moon"}, headers=HX)
    assert found.status_code == 200 and "Paper Moon" in found.text and "Glass Cloud" not in found.text
    assert "<html" not in found.text
    (button,) = [item for item in tags(found.text, "button") if item.get("hx-post")]
    assert button["hx-post"] == f"/review/{cover[0]['id']}/attach" and '"book_id": 1' in button["hx-vals"]
    assert "No books match" in client.get(f"/review/{cover[0]['id']}/attach-search", params={"q": "zzzz"}).text
    assert "Type" in client.get(f"/review/{cover[0]['id']}/attach-search", params={"q": ""}).text
    attached = client.post(f"/review/{cover[0]['id']}/attach", data={"book_id": "1", "also": str(barcode[0]["id"])}, headers=HX)
    assert attached.status_code == 204
    assert attached.headers["hx-redirect"] == f"/review/{shelf[0]['id']}?done=attached&book=1"
    with closing(store.open(tmp_path)) as db:
        assert store.book(db, 1)["cover_capture_id"] == SECOND_ID
    assert statuses(tmp_path)[cover[0]["id"]] == "used" and statuses(tmp_path)[barcode[0]["id"]] == "used"


def test_a_refused_attachment_says_why(client, tmp_path):
    shelf, _, _ = stock(tmp_path)
    nowhere = client.post(f"/review/{shelf[0]['id']}/attach", data={"book_id": "99"}, headers=HX)
    assert nowhere.status_code == 404 and "books: 99 was not found" in nowhere.text
    unchosen = client.post(f"/review/{shelf[0]['id']}/attach", data={"book_id": ""}, headers=HX)
    assert unchosen.status_code == 400 and "choose a book" in unchosen.text
    assert statuses(tmp_path)[shelf[0]["id"]] == "open"


def test_a_book_added_by_hand_returns_to_the_observation_and_only_local_paths_are_followed(client, tmp_path):
    shelf, _, _ = stock(tmp_path)
    page = client.get(f"/review/{shelf[0]['id']}").text
    hand = {"title": "Tin Comet", "author": "", "location_id": "1", "state": "Active"}
    nxt = f"/review/{shelf[0]['id']}?done=added"
    assert nxt in page
    response = client.post("/books", data={**hand, "next": nxt}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == nxt
    assert "Book added by hand" in client.get(nxt).text and statuses(tmp_path)[shelf[0]["id"]] == "open"
    hostile = client.post("/books", data={**hand, "title": "Tin Comet II", "next": "//evil.example/x"}, follow_redirects=False)
    assert hostile.headers["location"] == "/books/2"


def test_review_actions_need_access_and_the_same_origin(client, anonymous, tmp_path):
    shelf, _, _ = stock(tmp_path)
    for action in ("approve", "dismiss", "attach"):
        assert anonymous.post(f"/review/{shelf[0]['id']}/{action}").status_code == 401
        foreign = client.post(f"/review/{shelf[0]['id']}/{action}", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
        assert foreign.status_code == 403
    assert anonymous.get(f"/review/{shelf[0]['id']}/attach-search").status_code == 401
    assert set(statuses(tmp_path).values()) == {"open"}


def test_only_a_plain_path_on_this_site_is_followed_after_adding_a_book(client, tmp_path):
    hand = {"title": "Tin Comet", "author": "", "location_id": "1", "state": "Active"}
    stock(tmp_path)
    hostile = ["//evil.example/x", "/\\evil.example", "/\\\\evil.example", "http://evil.example/", "https://evil.example/",
               "evil.example", "javascript:alert(1)", "/ok\\path", "/\t/evil.example", "/\n/evil.example", "///evil.example", ""]
    for index, url in enumerate(hostile, start=1):
        response = client.post("/books", data={**hand, "title": f"Tin Comet {index}", "next": url}, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == f"/books/{index}", url
    fine = client.post("/books", data={**hand, "title": "Tin Comet fine", "next": "/review/5?done=added"}, follow_redirects=False)
    assert fine.headers["location"] == "/review/5?done=added"
    assert 'value="/review/5"' in client.get("/books/new", params={"next": "/review/5"}).text
    assert "evil" not in client.get("/books/new", params={"next": "/\\evil.example"}).text


def test_attach_buttons_include_the_ticked_pairs_only_when_there_are_pairs(client, tmp_path):
    """htmx logs an error for an hx-include selector that matches nothing, so a lone photo gets none."""
    shelf, cover, _ = stock(tmp_path)
    with closing(store.open(tmp_path)) as db:
        typed_book(db, title="Paper Moon")
    paired = client.get(f"/review/{cover[0]['id']}/attach-search", params={"q": "moon"}, headers=HX).text
    (button,) = [item for item in tags(paired, "button") if item.get("hx-post")]
    assert button["hx-include"] == "[name='also']"
    alone = client.get(f"/review/{shelf[0]['id']}/attach-search", params={"q": "moon"}, headers=HX).text
    (button,) = [item for item in tags(alone, "button") if item.get("hx-post")]
    assert "hx-include" not in button
