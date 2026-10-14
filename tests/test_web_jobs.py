"""Queue status and retries expose failures without hiding evidence."""
from contextlib import closing

from store_helpers import CAPTURE_ID, SECOND_ID, capture, fail_for_good, finish, record
from web_helpers import client as client

from home_library import store


def test_queue_heartbeats_and_retries_use_the_shared_store(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        finish(db, [record("Paper Moon")])
        queued = capture(db, SECOND_ID)
        last = fail_for_good(db)
    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert [job["status"] for job in jobs] == ["done", "failed"]
    assert jobs[1]["heartbeat_at"] == last and jobs[1]["error"] == "invented failure"
    health = client.get("/health").json()
    assert health == {"ok": True, "worker_seen": last, "queued": 0, "failed": 1}
    done = client.post(f"/api/jobs/{jobs[0]['id']}/retry")  # finished work is not redone
    assert done.status_code == 409 and "only a failed or waiting job" in done.json()["error"]
    retried = client.post(f"/api/jobs/{jobs[1]['id']}/retry")
    assert retried.status_code == 200 and retried.json()["status"] == "queued"
    assert retried.json()["attempts"] == 0
    assert client.get("/health").json()["queued"] == 1
    assert client.post(f"/api/jobs/{queued['job']['id']}/retry").status_code == 409
    assert client.post("/api/jobs/999/retry").status_code == 404
    assert len(client.get(f"/api/observations?capture_id={CAPTURE_ID}").json()) == 1
