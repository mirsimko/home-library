"""Tables on phones: the Books list and the Status page fit a phone, and an iPad still gets a real table.

The app runs for real on a free port and headless Chromium looks at it at the family's device widths.
The module skips when Playwright or its Chromium build is missing.
"""
import socket
import threading
import time
from contextlib import closing
from io import BytesIO

import httpx
import pytest
import uvicorn
from PIL import Image
from store_helpers import CAPTURE_ID, SECOND_ID, fail_for_good, typed_book

from home_library import store
from home_library.web import create_app

sync_api = pytest.importorskip("playwright.sync_api")

PHONES = [(384, 832), (412, 915)]
IPAD = (810, 1080)
LONG_TITLE = "Harry Potter and the Philosopher's Stone"
CZECH_TITLE = "Měsíční člun"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def jpeg(size):
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, "JPEG")
    return output.getvalue()


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout-tables")
    with closing(store.open(root)) as db:
        typed_book(db, title=LONG_TITLE, author="J. K. Invented", language="en", tags="school, magic")
        typed_book(db, title=CZECH_TITLE, author="Karel Novák", language="cs", state="Stored")
        typed_book(db, title="月とうさぎ", author="山田花子", language="ja")
    server = uvicorn.Server(uvicorn.Config(create_app(root, [], dev_user="parent"), port=(port := free_port()),
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    with httpx.Client(base_url=url, headers={"Sec-Fetch-Site": "same-origin"}) as http:
        for id, size in ((CAPTURE_ID, (4080, 3072)), (SECOND_ID, (800, 600))):
            http.post("/api/captures", data={"id": id, "kind": "shelf", "location_id": "1"},
                      files={"file": ("invented.jpg", jpeg(size), "image/jpeg")}).raise_for_status()
    with closing(store.open(root)) as db:
        fail_for_good(db, "invented failure with a fairly long explanation text")
    yield url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except Exception as error:  # no Chromium build on this machine
            pytest.skip(f"Chromium cannot launch: {str(error)[:80]}")
        yield chromium
        chromium.close()


def open_page(browser, base_url, path, size):
    context = browser.new_context(viewport={"width": size[0], "height": size[1]}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.goto(base_url + path)
    page.wait_for_load_state("networkidle")
    return page


def overflows(page):
    """What sticks out sideways: the page itself, or any table past the box that holds it."""
    return page.evaluate("""() => {
        const problems = [];
        if (document.documentElement.scrollWidth > innerWidth) problems.push('page');
        for (const table of document.querySelectorAll('table')) {
            const wrap = table.parentElement;
            if (table.getBoundingClientRect().width > wrap.clientWidth + 1) problems.push('table wider than its box');
            if (wrap.scrollWidth > wrap.clientWidth + 1) problems.push('table box scrolls sideways');
        }
        return problems;
    }""")


def broken_words(page, selector):
    """Latin words of the matching elements that are split over two lines."""
    return page.evaluate("""(selector) => {
        const broken = [];
        for (const element of document.querySelectorAll(selector)) {
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            for (let node; (node = walker.nextNode());) {
                for (const found of node.data.matchAll(/[A-Za-z\\u00C0-\\u017F']+/g)) {
                    const range = document.createRange();
                    range.setStart(node, found.index);
                    range.setEnd(node, found.index + found[0].length);
                    if (range.getClientRects().length > 1) broken.push(found[0]);
                }
            }
        }
        return broken;
    }""", selector)


@pytest.mark.parametrize("size", PHONES)
@pytest.mark.parametrize("path", ["/books", "/status", "/locations"])
def test_no_phone_page_has_sideways_overflow(browser, base_url, path, size):
    page = open_page(browser, base_url, path, size)
    assert overflows(page) == []


@pytest.mark.parametrize("size", PHONES)
def test_book_titles_wrap_only_between_words_on_a_phone(browser, base_url, size):
    page = open_page(browser, base_url, "/books", size)
    assert LONG_TITLE in page.inner_text("table") and CZECH_TITLE in page.inner_text("table")
    assert broken_words(page, "a.title") == []


@pytest.mark.parametrize("size", PHONES)
def test_book_rows_still_show_author_and_place_on_a_phone(browser, base_url, size):
    page = open_page(browser, base_url, "/books", size)
    row = page.locator("tbody tr", has_text=LONG_TITLE).first
    assert "J. K. Invented" in row.inner_text() and "Shelf A" in row.inner_text()


@pytest.mark.parametrize("size", PHONES)
def test_recent_photos_stay_readable_on_a_phone(browser, base_url, size):
    page = open_page(browser, base_url, "/status", size)
    text = page.inner_text("#status-panel")
    for wanted in ("4080 × 3072", "800 × 600", "smaller than 3000 px", "Shelf A", "invented failure"):
        assert wanted in text
    assert page.locator("button", has_text="Retry").first.is_visible()


@pytest.mark.parametrize("path", ["/books", "/status"])
def test_an_ipad_still_shows_a_proper_table(browser, base_url, path):
    page = open_page(browser, base_url, path, IPAD)
    assert overflows(page) == []
    table = page.locator("table").last
    assert table.evaluate("table => getComputedStyle(table).display") == "table"
    headings = table.locator("thead th")
    assert headings.count() >= 4
    assert all(headings.nth(index).is_visible() for index in range(1, headings.count()))
    if path == "/books":
        assert broken_words(page, "a.title") == []
