"""The capture page: setup, the two photo inputs, and the script that uploads."""
from contextlib import closing

from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import tags

from home_library import store


def test_capture_page_has_setup_modes_and_both_photo_inputs(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        store.add_location(db, "Shelf A", "shelf")
        store.add_location(db, "Box 3", "box")
    response = client.get("/capture")
    assert response.status_code == 200
    page = response.text
    options = {option["value"]: option for option in tags(page, "option")}
    assert {"1", "2", "Active", "Stored", "Retired", "Gone"} <= set(options)
    assert "Shelf A" in page and "Box 3" in page
    assert '<a href="/locations">' in page
    inputs = {item.get("id"): item for item in tags(page, "input")}
    camera, gallery = inputs["camera"], inputs["gallery"]
    assert camera["type"] == "file" and camera["accept"] == "image/*" and camera["capture"] == "environment"
    assert "multiple" not in camera
    assert gallery["type"] == "file" and gallery["accept"] == "image/*" and "multiple" in gallery
    assert "capture" not in gallery
    buttons = {button.get("data-mode") for button in tags(page, "button")}
    assert {"shelf", "book"} <= buttons
    assert '<script src="/static/capture.js"' in page
    assert 'id="photos"' in page


def test_capture_page_without_a_location_asks_for_one_first(client):
    page = client.get("/capture").text
    assert "Add a location first" in page
    assert 'href="/locations"' in page


def test_capture_page_needs_access(anonymous):
    assert anonymous.get("/capture").status_code == 401
