"""The review inbox: open observations grouped by photo, and by book for one-book photos, newest first."""
from contextlib import closing

from store_helpers import CAPTURE_ID, NOW, SECOND_ID, finish, record
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import tags

from home_library import store

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
    assert "月とうさぎ" not in page and "Měsíční člun" not in page and 'data-open-count="3"' in page


def test_an_empty_inbox_says_so_and_pages_need_access(client, anonymous):
    assert "Nothing is waiting for review" in client.get("/review").text
    assert anonymous.get("/review").status_code == 401
