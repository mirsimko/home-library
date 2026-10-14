"""Layout in a real browser: the pages fit the family's devices (see layout_helpers)."""
import pytest
from layout_helpers import PHONES, VIEWPORTS
from layout_helpers import browser as browser
from layout_helpers import open_page as open_page
from layout_helpers import site as site


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


@pytest.mark.parametrize("device", PHONES)
@pytest.mark.parametrize("path", ["/review/{middle}", "/review", "/capture", "/books", "/status"])
def test_no_page_is_wider_than_the_phone(open_page, device, path):
    page = open_page(device, path)
    assert page.evaluate("document.documentElement.scrollWidth") <= VIEWPORTS[device][0]
    pager = page.evaluate("""() => Array.from(document.querySelectorAll('.pager a')).map((a) => a.getBoundingClientRect().right)""")
    assert all(right <= VIEWPORTS[device][0] for right in pager)
