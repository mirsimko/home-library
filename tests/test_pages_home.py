"""The home page and the vendored static files every page loads."""
from contextlib import closing

from store_helpers import finish, record
from web_helpers import anonymous as anonymous
from web_helpers import client as client

from home_library import store


def test_home_links_to_every_page_and_counts_open_observations(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        finish(db, [record("Paper Moon"), record("Glass Cloud")])
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert '<html lang="en">' in page
    for path in ("/capture", "/review", "/books", "/locations", "/status"):
        assert f'href="{path}"' in page
    assert 'data-open-count="2"' in page
    assert "Paper Moon" not in page


def test_home_is_empty_but_working_before_anything_is_uploaded(client):
    assert 'data-open-count="0"' in client.get("/").text


def test_pages_need_the_same_access_as_the_api(anonymous):
    assert anonymous.get("/").status_code == 401
    assert anonymous.get("/static/app.css").status_code == 401


def test_static_files_carry_the_vendored_htmx_with_its_version_and_licence(client):
    script = client.get("/static/htmx.min.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    top = script.text[:400]
    assert top.startswith("/*") and "htmx.org 2." in top and "0BSD" in top
    assert "var htmx=" in script.text
    assert client.get("/static/app.css").status_code == 200
    assert '<script src="/static/htmx.min.js"' in client.get("/").text
