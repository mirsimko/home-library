"""The review inbox: open observations grouped by photo, and by book for one-book photos, newest first."""
import json
from contextlib import closing

from store_helpers import CAPTURE_ID, SECOND_ID, finish, record
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import form_values, tags

from home_library import store
from home_library.lookup.candidate import new_candidate

THIRD_ID = "10000000-0000-4000-8000-000000000003"
GROUP = "20000000-0000-4000-8000-000000000001"


def stock(tmp_path):
    """An older shelf photo with two rows, then a newer cover and barcode of one book."""
    with closing(store.open(tmp_path)) as db:
        shelf = finish(db, [record("月とうさぎ", language="ja"), record("Měsíční člun")], CAPTURE_ID)
        cover = finish(db, [record("Paper Moon", language="en")], SECOND_ID, kind="cover", group_id=GROUP,
                       now="2026-01-03T00:00:00Z", sha256="b" * 64)
        barcode = finish(db, [record("", read_status="barcode", isbn="9780000000002", catalogue_title="Paper Moon (catalogue)")],
                         THIRD_ID, kind="barcode", group_id=GROUP, now="2026-01-03T00:00:05Z", sha256="c" * 64)
    return shelf, cover, barcode


def test_inbox_groups_open_observations_newest_first_with_location_and_kind(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    page = client.get("/review").text
    assert page.index("Paper Moon") < page.index("月とうさぎ")  # the newer one-book group comes first
    assert page.count('class="group"') == 2
    assert "One book" in page and "Shelf photo" in page and "Shelf A" in page
    for row in (*shelf, *cover, *barcode):
        assert f'href="/review/{row["id"]}"' in page
    assert page.index("Paper Moon (catalogue)") > page.index("Paper Moon")  # cover row, then barcode row
    assert "9780000000002" in page
    assert any(item.get("lang") == "ja" for item in tags(page, "span"))
    assert 'data-open-count="4"' in page


def test_inbox_leaves_out_what_a_person_has_dealt_with(client, tmp_path):
    shelf, _, _ = stock(tmp_path)
    with closing(store.open(tmp_path)) as db:
        store.dismiss(db, [shelf[0]["id"]], "parent")
        store.approve(db, [shelf[1]["id"]], {}, "parent")
    page = client.get("/review").text
    assert "月とうさぎ" not in page and "Měsíční člun" not in page and 'data-open-count="2"' in page


def test_an_empty_inbox_says_so_and_pages_need_access(client, anonymous):
    assert "Nothing is waiting for review" in client.get("/review").text
    assert anonymous.get("/review").status_code == 401


# ---- the detail of one observation -------------------------------------------------------------------


def write_work(tmp_path, id, tiles=("r1c1-r0.jpg", "r1c2-r0.jpg"), kind=None, candidates=None):
    directory = tmp_path / "work" / id
    (directory / "lookup").mkdir(parents=True)
    manifest = {"tiles": [{"file": name} for name in tiles]}
    if kind:
        manifest["kind"] = kind
    (directory / "tiles.json").write_text(json.dumps(manifest))
    if candidates is not None:
        (directory / "lookup" / "candidates.json").write_text(json.dumps({"books": candidates}))


def fields_of(page, form_id="approve-form"):
    return form_values(page, form_id)


def test_detail_shows_the_tile_named_in_where_and_links_the_full_photo(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        (row,) = finish(db, [record("Paper Moon", where="r1c2-r0.jpg, left")])
    write_work(tmp_path, CAPTURE_ID)
    page = client.get(f"/review/{row['id']}").text
    assert f'src="/api/captures/{CAPTURE_ID}/tiles/r1c2-r0.jpg"' in page
    assert f'href="/api/captures/{CAPTURE_ID}/photo"' in page


def test_detail_falls_back_to_the_cover_tile_then_to_the_full_photo(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        (cover,) = finish(db, [record("Paper Moon", where="front")], CAPTURE_ID, kind="cover")
        (shelf,) = finish(db, [record("Glass Cloud", where="r9c9-r0.jpg, left")], SECOND_ID, sha256="b" * 64)
        (bare,) = finish(db, [record("Tin Comet", where="")], THIRD_ID, sha256="c" * 64)
    write_work(tmp_path, CAPTURE_ID, tiles=("cover-r0.jpg",), kind="cover")
    write_work(tmp_path, SECOND_ID)
    assert f'src="/api/captures/{CAPTURE_ID}/tiles/cover-r0.jpg"' in client.get(f"/review/{cover['id']}").text
    assert f'src="/api/captures/{SECOND_ID}/photo"' in client.get(f"/review/{shelf['id']}").text
    assert f'src="/api/captures/{THIRD_ID}/photo"' in client.get(f"/review/{bare['id']}").text


def test_detail_shows_both_readings_and_why_the_row_needs_a_look(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        (row,) = finish(db, [record("Zelený drak", other_reading="Zelený drak II", other_text="Pohádky", read_status="near",
                                    notes="The two reads differ by one letter.", language="cs")])
    page = client.get(f"/review/{row['id']}").text
    for text in ("Zelený drak", "Zelený drak II", "Pohádky", "near", "The two reads differ by one letter."):
        assert text in page
    assert 'lang="cs"' in page


def test_candidates_are_listed_with_a_button_that_fills_the_form(client, tmp_path):
    candidate = new_candidate("test", "1", title="Paper Moon", authors=["A. Writer", "B. Painter"], publisher="Moon Press",
                              year="2020", isbn="9780000000002", series="Night", language="en",
                              title_reading="Moon, Paper")
    with closing(store.open(tmp_path)) as db:
        (row,) = finish(db, [record("Paper Moon")])
    write_work(tmp_path, CAPTURE_ID, candidates=[{"item": 0, "title": "Paper Moon", "candidates": [candidate]}])
    page = client.get(f"/review/{row['id']}").text
    assert "Use this record" in page and "Moon Press" in page
    (button,) = [item for item in tags(page, "button") if "data-fill" in item]
    assert json.loads(button["data-fill"]) == {"title": "Paper Moon", "author": "A. Writer; B. Painter", "sort_key": "Moon, Paper", "publisher": "Moon Press",
                                               "year": "2020", "isbn": "9780000000002", "series": "Night", "language": "en",
                                               "source": "test", "source_id": "1"}
    (other,) = finish_other(tmp_path)
    assert "No catalogue candidates" in client.get(f"/review/{other['id']}").text


def finish_other(tmp_path):
    with closing(store.open(tmp_path)) as db:
        return finish(db, [record("Glass Cloud")], SECOND_ID, sha256="b" * 64)


def test_the_form_is_filled_from_the_record_the_capture_and_a_paired_barcode(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    page = client.get(f"/review/{cover[0]['id']}").text
    values = fields_of(page)
    assert values["title"] == "Paper Moon" and values["language"] == "en" and values["state"] == "Active"
    assert values["location_id"] == "1" and values["isbn"] == "9780000000002"
    assert 'id="approve-form"' in page and 'hx-post="/review/%d/approve"' % cover[0]["id"] in page
    assert [(item.get("value"), "checked" in item) for item in tags(page, "input") if item.get("name") == "also"] == [
        (str(barcode[0]["id"]), True)]
    barcode_page = client.get(f"/review/{barcode[0]['id']}").text
    assert fields_of(barcode_page)["title"] == "Paper Moon"
    assert [item.get("value") for item in tags(barcode_page, "input") if item.get("name") == "also"] == [str(cover[0]["id"])]
    assert not [item for item in tags(client.get(f"/review/{shelf[0]['id']}").text, "input") if item.get("name") == "also"]


def test_the_form_starts_the_same_whichever_photo_of_the_book_is_opened_and_follows_the_store_rule(client, tmp_path):
    _, cover, barcode = stock(tmp_path)
    from_cover = fields_of(client.get(f"/review/{cover[0]['id']}").text)
    from_barcode = fields_of(client.get(f"/review/{barcode[0]['id']}").text)
    from_cover.pop("also"), from_barcode.pop("also")
    assert from_cover == from_barcode
    assert from_cover["language"] == "en"  # the cover was photographed first; the barcode row's "cs" does not win
    with closing(store.open(tmp_path)) as db:
        expected = store.default_fields(db, [cover[0]["id"], barcode[0]["id"]])
    for key in ("title", "sort_key", "author", "isbn", "language", "state", "source", "source_id", "notes"):
        assert from_cover[key] == expected[key], key
    assert from_cover["location_id"] == str(expected["location_id"])


def test_detail_knows_the_next_and_previous_open_observation(client, tmp_path):
    shelf, cover, barcode = stock(tmp_path)
    order = [cover[0]["id"], barcode[0]["id"], shelf[0]["id"], shelf[1]["id"]]

    def neighbours(id):
        (holder,) = [item for item in tags(client.get(f"/review/{id}").text, "div") if item.get("id") == "review"]
        return holder.get("data-prev"), holder.get("data-next")

    assert neighbours(order[0]) == (None, f"/review/{order[1]}")
    assert neighbours(order[2]) == (f"/review/{order[1]}", f"/review/{order[3]}")
    assert neighbours(order[3]) == (f"/review/{order[2]}", None)


def test_a_dealt_with_or_unknown_observation_offers_no_actions(client, tmp_path):
    shelf, _, _ = stock(tmp_path)
    with closing(store.open(tmp_path)) as db:
        book = store.approve(db, [shelf[0]["id"]], {}, "parent")
    page = client.get(f"/review/{shelf[0]['id']}")
    assert page.status_code == 200 and "already used" in page.text and f'href="/books/{book["id"]}"' in page.text
    assert 'id="approve-form"' not in page.text
    assert client.get("/review/999").status_code == 404
    assert client.get("/review/wrong").status_code == 400


def test_a_barcode_only_observation_is_headed_by_the_catalogue_title(client, tmp_path):
    _, cover, barcode = stock(tmp_path)
    page = client.get(f"/review/{barcode[0]['id']}").text
    (heading,) = page.split("<h1")[1:2]
    heading = heading.split("</h1>")[0]
    assert "Paper Moon (catalogue)" in heading and "nothing read" not in heading
    assert "(empty)" not in page and "nothing read, barcode only" in page
    bare = client.get(f"/review/{cover[0]['id']}").text
    assert "nothing read, barcode only" not in bare and "(empty)" not in bare


def test_keyboard_hints_are_hidden_on_touch_screens(client, tmp_path):
    from pathlib import Path

    with closing(store.open(tmp_path)) as db:
        (row,) = finish(db, [record("Paper Moon")])
    for path in ("/review", f"/review/{row['id']}"):
        assert any("key-hints" in item.get("class", "").split() for item in tags(client.get(path).text, "div"))
    css = (Path(__file__).resolve().parent.parent / "src/home_library/web/static/app.css").read_text()
    rule = css[css.index("@media (hover: none) and (pointer: coarse)"):]
    hidden = rule[:rule.index("}") + 1]
    assert ".key-hints" in hidden and ".button kbd" in hidden and "button kbd" in hidden and "display: none" in hidden
