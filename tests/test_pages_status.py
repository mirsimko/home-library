"""The status page: queue counts, the worker's heartbeat, failed jobs with a retry, and photo sizes."""
from contextlib import closing

from store_helpers import CAPTURE_ID, NOW, SECOND_ID, capture, fail_for_good
from web_helpers import anonymous as anonymous
from web_helpers import client as client
from web_helpers import photo

from home_library import store
from home_library.web.status_pages import ago


def test_ago_says_how_long_in_plain_words():
    assert [ago(seconds) for seconds in (0, 9, 10, 59, 60, 119, 3600, 7300, 86400, 3 * 86400)] == [
        "just now", "just now", "10 seconds ago", "59 seconds ago", "1 minute ago", "1 minute ago",
        "1 hour ago", "2 hours ago", "1 day ago", "3 days ago"]


def upload(client, id, size):
    client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    return client.post("/api/captures", data={"id": id, "kind": "shelf", "location_id": "1"},
                       files={"file": ("invented.jpg", photo(size=size), "image/jpeg")})


def test_status_page_counts_the_queue_and_shows_the_workers_last_heartbeat(client, tmp_path):
    upload(client, CAPTURE_ID, (400, 300))
    with closing(store.open(tmp_path)) as db:
        capture(db, SECOND_ID)
        store.claim_job(db)
    page = client.get("/status").text
    assert 'data-queued="1"' in page and 'data-running="1"' in page and 'data-failed="0"' in page
    assert "Worker last seen" in page and "just now" in page


def test_status_page_without_a_worker_says_so(client):
    assert "The worker has not been seen yet" in client.get("/status").text


def test_recent_captures_show_the_received_size_and_flag_small_photos(client):
    upload(client, CAPTURE_ID, (4080, 3072))
    upload(client, SECOND_ID, (800, 600))
    page = client.get("/status").text
    assert "4080 × 3072" in page and "800 × 600" in page
    assert page.count("smaller than 3000 px") == 1
    assert page.index("800 × 600") < page.index("4080 × 3072")  # newest first
    (client.app.state.data_root / "captures" / f"{CAPTURE_ID}.jpg").unlink()
    assert "file missing" in client.get("/status").text


def test_failed_jobs_show_their_error_and_can_be_retried(client, tmp_path):
    upload(client, CAPTURE_ID, (400, 300))
    with closing(store.open(tmp_path)) as db:
        fail_for_good(db, "invented failure <b>text</b>")
    page = client.get("/status").text
    assert "invented failure &lt;b&gt;text&lt;/b&gt;" in page and 'hx-post="/status/jobs/1/retry"' in page
    retried = client.post("/status/jobs/1/retry", headers={"HX-Request": "true"})
    assert retried.status_code == 200 and "queued again" in retried.text and "<html" not in retried.text
    with closing(store.open(tmp_path)) as db:
        assert store.jobs(db)[0]["status"] == "queued" and store.jobs(db)[0]["attempts"] == 0
    again = client.post("/status/jobs/1/retry", headers={"HX-Request": "true"})
    assert again.status_code == 409 and "only a failed job" in again.text
    assert client.post("/status/jobs/99/retry").status_code == 404
    assert 'data-failed="0"' in client.get("/status/panel").text


def test_a_job_waiting_out_its_retry_delay_says_when_it_may_run_again(client, tmp_path):
    upload(client, CAPTURE_ID, (400, 300))
    upload(client, SECOND_ID, (400, 300))
    with closing(store.open(tmp_path)) as db:
        for _ in range(2):
            job = store.claim_job(db)
            store.fail_job(db, job["id"], job["owner"], "rate limited", NOW if job["capture_id"] == SECOND_ID else None)
        waiting = store.jobs(db)[0]
    page = client.get("/status").text
    assert 'data-queued="2"' in page and 'data-failed="0"' in page
    assert page.count("retrying after") == 1
    assert f"retrying after {store.retry_at(waiting):%H:%M} UTC" in page


def test_status_pages_need_access(anonymous):
    for path in ("/status", "/status/panel"):
        assert anonymous.get(path).status_code == 401
    assert anonymous.post("/status/jobs/1/retry").status_code == 401


def test_only_a_small_shelf_photo_is_flagged_not_a_cover_or_a_barcode(client):
    client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    for number, kind in enumerate(("shelf", "cover", "barcode"), start=1):
        client.post("/api/captures", data={"id": f"10000000-0000-4000-8000-00000000000{number}", "kind": kind, "location_id": "1"},
                    files={"file": ("invented.jpg", photo(size=(800, 600)), "image/jpeg")})
    page = client.get("/status").text
    assert page.count("800 × 600") == 3
    assert page.count("smaller than 3000 px") == 1
    assert "for a shelf photo" in page
