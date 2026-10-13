"""Queue status and retries expose failures without hiding evidence."""
from contextlib import closing

from store_helpers import CAPTURE_ID, NOW, SECOND_ID, capture, finish, record
from web_helpers import client as client

from home_library import store


def test_queue_heartbeats_and_retries_use_the_shared_store(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        finish(db, [record("Paper Moon")])
        queued = capture(db, SECOND_ID)
        for _ in range(3):
            job = store.claim_job(db, NOW)
            store.fail_job(db, job["id"], job["owner"], "invented failure", NOW)
    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert [job["status"] for job in jobs] == ["done", "failed"]
    assert jobs[1]["heartbeat_at"] == NOW and jobs[1]["error"] == "invented failure"
    health = client.get("/health").json()
    assert health == {"ok": True, "worker_seen": NOW, "queued": 0, "failed": 1}
    for job in jobs:
        retried = client.post(f"/api/jobs/{job['id']}/retry")
        assert retried.status_code == 200 and retried.json()["status"] == "queued"
        assert retried.json()["attempts"] == 0
    assert client.get("/health").json()["queued"] == 2
    assert client.post(f"/api/jobs/{queued['job']['id']}/retry").status_code == 400
    assert client.post("/api/jobs/999/retry").status_code == 404
    assert len(client.get(f"/api/observations?capture_id={CAPTURE_ID}").json()) == 1
