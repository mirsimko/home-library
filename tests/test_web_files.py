"""Capture receipts and manifest-listed images stay behind access checks."""
import json
from contextlib import closing

from fastapi.testclient import TestClient
from store_helpers import CAPTURE_ID, SECOND_ID
from web_helpers import client as client
from web_helpers import photo

from home_library import store
from home_library.web import create_app


def captured(client):
    client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    return client.post("/api/captures", data={"id": CAPTURE_ID, "kind": "shelf", "location_id": "1"},
                       files={"file": ("invented.png", photo("PNG", size=(30, 20)), "text/plain")}).json()


def test_capture_details_listing_and_photos_report_the_stored_content(client, tmp_path):
    receipt = captured(client)
    details = client.get(f"/api/captures/{CAPTURE_ID}")
    assert details.status_code == 200
    assert details.json() == {**receipt, "created": False, "open_observations": 0}
    assert details.json()["image"]["orientation"] is None
    with closing(store.open(tmp_path)) as db:
        job = store.claim_job(db)
        store.finish_job(db, job["id"], job["owner"], [{"title": "Paper Moon"}])
    listed = client.get("/api/captures").json()
    assert len(listed) == 1 and listed[0]["open_observations"] == 1 and listed[0]["job"]["status"] == "done"
    assert client.get(f"/api/captures?ids={CAPTURE_ID}").json() == listed
    assert client.get(f"/api/captures?ids={SECOND_ID}").json() == []
    assert client.get("/api/captures?ids=wrong").status_code == 400
    response = client.get(f"/api/captures/{CAPTURE_ID}/photo")
    assert response.content == photo("PNG", size=(30, 20))
    assert response.headers["content-type"] == "image/png" and response.headers["cache-control"] == "private"
    unauthenticated = TestClient(create_app(tmp_path, []))
    assert unauthenticated.get(f"/api/captures/{CAPTURE_ID}/photo").status_code == 401
    assert client.get(f"/api/captures/{SECOND_ID}").status_code == 404
    (tmp_path / "captures" / f"{CAPTURE_ID}.png").unlink()
    assert client.get(f"/api/captures/{CAPTURE_ID}/photo").status_code == 404


def test_only_manifest_tiles_inside_the_tile_directory_can_be_served(client, tmp_path):
    captured(client)
    directory = tmp_path / "work" / CAPTURE_ID
    tiles = directory / "tiles"
    tiles.mkdir(parents=True)
    (tiles / "r1c1-r0.jpg").write_bytes(photo(size=(10, 10)))
    (tiles / "unlisted.jpg").write_bytes(photo(size=(10, 10)))
    (directory / "secret.jpg").write_bytes(b"private")
    (tiles / "linked.jpg").symlink_to(directory / "secret.jpg")
    (directory / "tiles.json").write_text(json.dumps({"tiles": [
        {"file": "r1c1-r0.jpg"}, {"file": "../secret.jpg"}, {"file": "linked.jpg"}]}))
    response = client.get(f"/api/captures/{CAPTURE_ID}/tiles/r1c1-r0.jpg")
    assert response.status_code == 200 and response.content == photo(size=(10, 10))
    assert response.headers["content-type"] == "image/jpeg" and response.headers["cache-control"] == "private"
    for name in ("unlisted.jpg", "missing.jpg", "linked.jpg", "%2E%2E%2Fsecret.jpg"):
        assert client.get(f"/api/captures/{CAPTURE_ID}/tiles/{name}").status_code == 404
    anonymous = TestClient(create_app(tmp_path, []))
    assert anonymous.get(f"/api/captures/{CAPTURE_ID}/tiles/r1c1-r0.jpg").status_code == 401
    (directory / "tiles.json").unlink()
    assert client.get(f"/api/captures/{CAPTURE_ID}/tiles/r1c1-r0.jpg").status_code == 404
