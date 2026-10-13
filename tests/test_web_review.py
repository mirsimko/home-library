"""Review actions turn evidence into books only through the store."""
from contextlib import closing

from store_helpers import CAPTURE_ID, SECOND_ID, finish, record
from web_helpers import client as client

from home_library import store


def test_review_can_approve_attach_and_dismiss_observations(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        rows = finish(db, [record("Paper Moon"), record("Glass Cloud"), record("Tin Comet")], kind="cover")
    listed = client.get("/api/observations").json()
    assert listed == rows
    assert client.get(f"/api/observations?capture_id={SECOND_ID}").json() == []
    approved = client.post("/api/observations/approve", json={"observation_ids": [rows[0]["id"]],
                                                           "fields": {"notes": "Seen by a person"}})
    assert approved.status_code == 201
    book = approved.json()
    assert book["title"] == "Paper Moon" and book["reviewed_by"] == "parent" and book["needs_review"] is False
    assert book["cover_capture_id"] == CAPTURE_ID
    attached = client.post("/api/observations/attach", json={"observation_ids": [rows[1]["id"]], "book_id": book["id"]})
    assert attached.status_code == 200 and attached.json() == book
    dismissed = client.post("/api/observations/dismiss", json={"observation_ids": [rows[2]["id"]]})
    assert dismissed.status_code == 200 and dismissed.json()[0]["status"] == "dismissed"
    assert client.get("/api/observations").json() == []
    assert [o["book_id"] for o in client.get("/api/observations?status=used").json()] == [book["id"], book["id"]]
    assert len(client.get("/api/observations?status=dismissed").json()) == 1
    assert client.get("/api/observations?status=wrong").status_code == 400
    assert client.get("/api/observations?capture_id=wrong").status_code == 400
    assert client.post("/api/observations/approve", json={"observation_ids": [rows[0]["id"]], "fields": {}}).status_code == 400
    assert client.post("/api/observations/dismiss", json={"observation_ids": [999]}).status_code == 404
    assert client.post("/api/observations/attach", json={"observation_ids": []}).status_code == 400
