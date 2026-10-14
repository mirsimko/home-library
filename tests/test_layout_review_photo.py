"""The review detail page in a real browser: the evidence photo must not fill an iPad's portrait screen.

Needs Playwright and its Chromium; the module skips when either is missing.
Run it with `uv run --with playwright pytest tests/test_layout_review_photo.py`.
"""
import json
import socket
import threading
import time
from contextlib import closing

import pytest
import uvicorn
from PIL import Image
from store_helpers import SECOND_ID, finish, record

from home_library import store
from home_library.web import create_app

sync_api = pytest.importorskip("playwright.sync_api")

FIRST_ID = "10000000-0000-4000-8000-000000000001"
IPAD_PORTRAIT = {"width": 810, "height": 1080}
IPAD_LANDSCAPE = {"width": 1080, "height": 810}
PHONES = [{"width": 384, "height": 832}, {"width": 412, "height": 915}]


def stock(root):
    """Two invented shelf observations: one shows a tall tile, the other the whole 4080 x 3072 photo."""
    (root / "captures").mkdir(parents=True)
    tiles = root / "work" / FIRST_ID / "tiles"
    tiles.mkdir(parents=True)
    Image.new("RGB", (1200, 1600), "tan").save(tiles / "r1c1-r0.jpg")
    (root / "work" / FIRST_ID / "tiles.json").write_text(json.dumps({"tiles": [{"file": "r1c1-r0.jpg"}]}))
    for id in (FIRST_ID, SECOND_ID):
        Image.new("RGB", (4080, 3072), "tan").save(root / "captures" / f"{id}.jpg")
    with closing(store.open(root)) as db:
        (tile,) = finish(db, [record("Paper Moon", language="en", where="r1c1-r0.jpg, left")], FIRST_ID,
                         media_type="image/jpeg")
        (whole,) = finish(db, [record("Moon Boat", language="en", where="")], SECOND_ID,
                          now="2026-01-03T00:00:00Z", sha256="b" * 64)
    return {"tile": tile["id"], "whole": whole["id"]}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout")
    ids = stock(root)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(root, [], dev_user="parent"), port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", ids
    server.should_exit = True
    thread.join(10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"Chromium cannot launch: {error}")
        yield chromium
        chromium.close()


def open_review(browser, site, which, viewport):
    base, ids = site
    page = browser.new_page(viewport=viewport)
    page.goto(f"{base}/review/{ids[which]}")
    page.wait_for_function("document.querySelector('.evidence img').complete")
    return page


def box(page, selector):
    """top, height, left and right of the first match, in CSS pixels from the page's top left."""
    return page.eval_on_selector(selector, "(e) => { const r = e.getBoundingClientRect(); return [r.top + scrollY, r.height, r.left, r.right]; }")


@pytest.mark.parametrize("which", ["tile", "whole"])
def test_ipad_portrait_caps_the_photo_so_the_form_starts_on_the_first_screen(browser, site, which):
    page = open_review(browser, site, which, IPAD_PORTRAIT)
    _, height, _, _ = box(page, ".evidence img")
    assert height <= 0.45 * IPAD_PORTRAIT["height"]
    assert page.eval_on_selector(".evidence img", "(e) => getComputedStyle(e).objectFit") == "contain"
    assert box(page, "#f-title")[0] <= 1.6 * IPAD_PORTRAIT["height"]
    assert page.locator("text=Open the full photo").is_visible()
    page.close()


@pytest.mark.parametrize("viewport", PHONES, ids=lambda size: f"{size['width']}x{size['height']}")
@pytest.mark.parametrize("which", ["tile", "whole"])
def test_phones_keep_the_photo_within_the_cap_and_the_page_within_the_width(browser, site, which, viewport):
    page = open_review(browser, site, which, viewport)
    _, height, left, right = box(page, ".evidence img")
    assert height <= 0.45 * viewport["height"]
    assert 0 <= left and right <= viewport["width"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.close()


@pytest.mark.parametrize("which", ["tile", "whole"])
def test_ipad_landscape_keeps_the_photo_left_of_the_form(browser, site, which):
    page = open_review(browser, site, which, IPAD_LANDSCAPE)
    _, _, _, photo_right = box(page, ".evidence img")
    title_top, _, title_left, _ = box(page, "#f-title")
    assert photo_right <= title_left
    assert title_top < IPAD_LANDSCAPE["height"]
    page.close()
