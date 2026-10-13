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


def test_candidates_match_record_item_order_even_when_titles_repeat(client, tmp_path):
    import json

    with closing(store.open(tmp_path)) as db:
        rows = finish(db, [record("Paper Moon"), record("Paper Moon"), record("", read_status="unreadable")])
    directory = tmp_path / "work" / CAPTURE_ID / "lookup"
    directory.mkdir(parents=True)
    candidates = directory / "candidates.json"
    candidates.write_text(json.dumps({"books": [
        {"item": 1, "title": "Paper Moon", "candidates": [{"id": "test:second"}]},
        {"item": 0, "title": "Paper Moon", "candidates": [{"id": "test:first"}]},
    ]}))
    assert client.get(f"/api/observations/{rows[0]['id']}/candidates").json() == [{"id": "test:first"}]
    assert client.get(f"/api/observations/{rows[1]['id']}/candidates").json() == [{"id": "test:second"}]
    assert client.get(f"/api/observations/{rows[2]['id']}/candidates").json() == []
    assert client.get("/api/observations/999/candidates").status_code == 404
    candidates.unlink()
    assert client.get(f"/api/observations/{rows[0]['id']}/candidates").json() == []


def test_old_observations_never_get_candidates_from_a_newer_attempt(client, tmp_path):
    import json

    with closing(store.open(tmp_path)) as db:
        (old,) = finish(db, [record("Paper Moon")])
        store.approve(db, [old["id"]], {}, "parent")
        store.retry_job(db, store.capture(db, CAPTURE_ID)["job"]["id"])
        job = store.claim_job(db)
        store.finish_job(db, job["id"], job["owner"], [record("Glass Cloud")])
        (new,) = store.observations(db)
    directory = tmp_path / "work" / CAPTURE_ID / "lookup"
    directory.mkdir(parents=True)
    (directory / "candidates.json").write_text(json.dumps({"books": [
        {"item": 0, "title": "Glass Cloud", "candidates": [{"id": "test:new"}]}]}))
    assert client.get(f"/api/observations/{old['id']}/candidates").json() == []
    assert client.get(f"/api/observations/{new['id']}/candidates").json() == [{"id": "test:new"}]
