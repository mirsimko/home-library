"""Layout in a real browser: the pages fit the family's devices (Pixel 8, Galaxy A55, iPad 9th generation).

Needs Playwright and its Chromium build; without them these tests skip, so the suite passes on a machine
without browsers. Invented titles only.
"""
import socket
import threading
import time
from contextlib import closing

import pytest

pytest.importorskip("playwright")
import uvicorn  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from store_helpers import NOW, capture, finish, record, typed_book  # noqa: E402

from home_library import store  # noqa: E402
from home_library.web import create_app  # noqa: E402

VIEWPORTS = {"a55": (384, 832), "pixel8": (412, 915), "ipad": (810, 1080), "ipad-landscape": (1080, 810)}
PHONES = ["a55", "pixel8"]
SHELF_ID = "10000000-0000-4000-8000-0000000000a1"
COVER_ID = "10000000-0000-4000-8000-0000000000a2"
BARCODE_ID = "10000000-0000-4000-8000-0000000000a3"
FAILED_ID = "10000000-0000-4000-8000-0000000000a4"
GROUP = "20000000-0000-4000-8000-0000000000a1"


def seed(root):
    """A few books, a shelf photo with three readings, small cover and barcode photos, and a failed job."""
    with closing(store.open(root)) as db:
        store.add_location(db, "Shelf A1", "shelf", now=NOW)
        store.add_location(db, "Box 1", "box", now=NOW)
        typed_book(db, title="Harry Potter and the Philosopher's Stone", author="J. K. Rowling", language="en", tags="magic, school")
        typed_book(db, title="Měsíční člun", author="Karel Novák", language="cs", state="Stored", location_id=2, tags="boat, night")
        typed_book(db, title="Pohádky o dvanácti měsíčkách a kouzelném lese", author="Jana Malá", language="cs")
        typed_book(db, title="Paper Moon", author="A. Writer", language="en")
        typed_book(db, title="月とうさぎ", author="山田花子", language="ja", tags="night")
        shelf = finish(db, [record("つきのふね", language="ja", where="r1c1-r0.jpg, left", notes="The two reads differ by one letter.",
                                   read_status="near", other_reading="つきのぶね"),
                            record("Zelený drak", language="cs", where="r1c1-r0.jpg, middle", author="Jana Malá"),
                            record("The Quiet Fox", language="en", where="r1c1-r0.jpg, right")], SHELF_ID)
        finish(db, [], COVER_ID, kind="cover", group_id=GROUP, sha256="b" * 64, now="2026-01-03T00:00:00Z")
        finish(db, [], BARCODE_ID, kind="barcode", group_id=GROUP, sha256="c" * 64, now="2026-01-03T00:00:05Z")
        capture(db, FAILED_ID, sha256="d" * 64, now="2026-01-04T00:00:00Z")
        for _ in range(3):
            job = store.claim_job(db, NOW)
            store.fail_job(db, job["id"], job["owner"], "the reader did not answer", NOW)
        book_ids = [book["id"] for book in store.search_books(db)]
    for id, size in ((SHELF_ID, (4080, 3072)), (COVER_ID, (1600, 1200)), (BARCODE_ID, (800, 600)), (FAILED_ID, (4080, 3072))):
        image = Image.new("RGB", size, (200, 180, 150))
        ImageDraw.Draw(image).rectangle([size[0] // 5, size[1] // 8, size[0] // 2, size[1] * 7 // 8], fill=(60, 120, 160))
        image.save(root / "captures" / f"{id}.jpg")
    tiles = root / "work" / SHELF_ID / "tiles"
    tiles.mkdir(parents=True)
    Image.open(root / "captures" / f"{SHELF_ID}.jpg").resize((1360, 1024)).save(tiles / "r1c1-r0.jpg")
    (root / "work" / SHELF_ID / "tiles.json").write_text('{"tiles": [{"file": "r1c1-r0.jpg"}]}')
    return {"middle": shelf[1]["id"], "book": book_ids[0]}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout")
    ids = seed(root)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(root, [], dev_user="parent"), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    yield {"base": f"http://127.0.0.1:{port}", **ids}
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except Exception as error:  # the browser build is not installed on this machine
            pytest.skip(f"Chromium is not available: {str(error).splitlines()[0]}")
        yield chromium
        chromium.close()


@pytest.fixture
def open_page(browser, site):
    contexts = []

    def open(device, path):
        width, height = VIEWPORTS[device]
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2, is_mobile=True, has_touch=True)
        contexts.append(context)
        page = context.new_page()
        page.goto(site["base"] + path.format(**site))
        return page

    yield open
    for context in contexts:
        context.close()


PAGES = ["/", "/capture", "/review", "/review/{middle}", "/books", "/books/{book}", "/books/new", "/locations", "/status"]


@pytest.mark.parametrize("device", VIEWPORTS)
def test_every_menu_link_is_visible_and_tappable(open_page, device):
    page = open_page(device, "/books")
    width = VIEWPORTS[device][0]
    links = page.evaluate("""() => Array.from(document.querySelectorAll('header nav a')).map((a) => {
        const box = a.getBoundingClientRect();
        return {text: a.textContent.trim(), left: box.left, right: box.right, top: box.top, bottom: box.bottom, height: box.height};
    })""")
    assert [link["text"] for link in links] == ["Capture", "Review", "Books", "Locations", "Status"]
    for link in links:
        assert 0 <= link["left"] and link["right"] <= width, link
        assert link["height"] >= 44, link
    assert page.evaluate("document.querySelector('header nav').scrollWidth <= document.querySelector('header nav').clientWidth")
