"""Catalogue requests use store rules and the authenticated person's name."""
from web_helpers import client as client


def test_locations_and_books_can_be_created_read_renamed_and_edited(client):
    shelf = client.post("/api/locations", json={"name": " Shelf A ", "kind": "shelf"})
    assert shelf.status_code == 201
    assert shelf.json()["name"] == "Shelf A"
    id = shelf.json()["id"]
    assert client.get("/api/locations").json() == [shelf.json()]
    assert client.patch(f"/api/locations/{id}", json={"name": "Shelf B"}).json()["name"] == "Shelf B"
    added = client.post("/api/books", json={"title": "Paper Moon", "location_id": id})
    assert added.status_code == 201
    book = added.json()
    assert book["created_by"] == book["reviewed_by"] == "parent"
    assert client.get(f"/api/books/{book['id']}").json() == book
    assert client.get("/api/books").json() == [book]
    changed = client.patch(f"/api/books/{book['id']}", json={"version": book["version"],
                                                          "changes": {"notes": "Keep this copy"}})
    assert changed.status_code == 200
    assert changed.json()["notes"] == "Keep this copy" and changed.json()["version"] == 2
    stale = client.patch(f"/api/books/{book['id']}", json={"version": 1, "changes": {"title": "Another moon"}})
    assert stale.status_code == 409
    assert stale.json() == {"error": "this book has changed; read its current version before editing"}


def test_store_and_request_errors_are_actionable_json(client):
    response = client.post("/api/locations", json={"name": " ", "kind": "shelf"})
    assert response.status_code == 400 and response.json() == {"error": "location name must not be empty"}
    response = client.get("/api/books/999")
    assert response.status_code == 404 and response.json() == {"error": "books: 999 was not found"}
    for method, path, options in [
        ("get", "/api/books/no", {}), ("get", "/api/books?limit=wrong", {}),
        ("post", "/api/books", {"json": []}), ("post", "/api/locations", {"json": {}}),
        ("post", "/api/books", {"content": "{", "headers": {"Content-Type": "application/json"}}),
    ]:
        response = getattr(client, method)(path, **options)
        assert response.status_code == 400
        assert list(response.json()) == ["error"]
    assert client.get("/missing").status_code == 404
    assert list(client.get("/missing").json()) == ["error"]
