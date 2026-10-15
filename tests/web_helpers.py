"""Temporary private data and generated uploads for HTTP tests."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from home_library.web import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, [], dev_user="parent"),
                    headers={"Sec-Fetch-Site": "same-origin"}) as client:
        yield client


def photo(format="JPEG", size=(4080, 3072), orientation=None):
    output = BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    Image.new("RGB", size, "white").save(output, format, exif=exif)
    return output.getvalue()


@pytest.fixture
def anonymous(tmp_path):
    """A client that no access rule lets in."""
    with TestClient(create_app(tmp_path, [])) as client:
        yield client


def tags(page, name):
    """The attributes of every <name> element of a page, as dicts, for asserting on markup."""
    from html.parser import HTMLParser

    found = []

    class Collect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == name:
                found.append({key: value for key, value in attrs})

    Collect().feed(page)
    return found


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
