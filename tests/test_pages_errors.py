"""A person who follows a bad link sees a page; the API and HTMX keep their JSON errors."""
from web_helpers import client as client

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def test_a_missing_record_in_the_browser_is_a_page_with_a_way_back(client):
    response = client.get("/books/99", headers=BROWSER)
    assert response.status_code == 404 and response.headers["content-type"].startswith("text/html")
    assert "books: 99 was not found" in response.text and 'href="/"' in response.text
    assert "Not found" in response.text
    assert client.get("/review/999", headers=BROWSER).status_code == 404


def test_a_malformed_address_in_the_browser_is_a_page_too(client):
    response = client.get("/review/wrong", headers=BROWSER)
    assert response.status_code == 400 and response.headers["content-type"].startswith("text/html")
    assert "Something is wrong with this request" in response.text


def test_scripts_the_api_and_htmx_still_get_json(client):
    assert client.get("/books/99").json() == {"error": "books: 99 was not found"}
    assert client.get("/api/books/99", headers=BROWSER).json() == {"error": "books: 99 was not found"}
    assert client.get("/books/99", headers={**BROWSER, "HX-Request": "true"}).headers["content-type"] == "application/json"
    assert client.get("/no/such/page", headers=BROWSER).status_code == 404
    assert client.get("/no/such/page", headers=BROWSER).headers["content-type"].startswith("text/html")
