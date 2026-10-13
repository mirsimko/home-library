"""Public store reads used by the web app."""
import pytest
from store_helpers import CAPTURE_ID, NOW, SECOND_ID, capture, finish, record
from store_helpers import db as db

from home_library import store


def test_capture_reads_include_jobs_and_open_counts_in_recent_order(db):
    finish(db, [record(), record("Paper Moon")])
    capture(db, SECOND_ID, now="2026-01-03T00:00:00Z")
    receipts = store.captures(db)
    assert [r["capture"]["id"] for r in receipts] == [SECOND_ID, CAPTURE_ID]
    assert [r["open_observations"] for r in receipts] == [0, 2]
    assert [r["job"]["status"] for r in receipts] == ["queued", "done"]
    assert store.captures(db, [CAPTURE_ID]) == [receipts[1]]
    assert store.captures(db, []) == []
    assert store.capture(db, CAPTURE_ID) == receipts[1]
    with pytest.raises(store.Invalid, match="UUID"):
        store.capture(db, "../outside")
    with pytest.raises(store.NotFound):
        store.capture(db, "10000000-0000-4000-8000-000000000009")


def test_queue_and_single_observation_reads_include_only_their_public_data(db):
    rows = finish(db, [record()])
    capture(db, SECOND_ID)
    assert store.observation(db, rows[0]["id"]) == rows[0]
    with pytest.raises(store.NotFound):
        store.observation(db, 999)
    assert [j["status"] for j in store.jobs(db)] == ["done", "queued"]
    assert store.health(db) == {"ok": True, "worker_seen": NOW, "queued": 1, "failed": 0}
    assert "title" not in str(store.health(db))


def test_json_exports_include_distinct_evidence_and_cover_capture_ids(db):
    first = finish(db, [record("Paper Moon"), record("Paper Moon")], kind="cover")
    second = finish(db, [record("", read_status="barcode")], SECOND_ID, kind="barcode")
    book = store.approve(db, [o["id"] for o in first + second], {}, "parent")
    manual = store.add_book(db, {"title": "Glass Cloud", "location_id": 1}, "parent")
    exported = store.export_books(db)
    assert [row["title"] for row in exported] == [manual["title"], book["title"]]
    assert [row["capture_ids"] for row in exported] == [[], [CAPTURE_ID, SECOND_ID]]
    assert [{key: value for key, value in row.items() if key != "capture_ids"}
            for row in exported] == store.export_rows(db)


def test_web_upload_preflight_preserves_uploader_normalisation(db):
    receipt = capture(db, uploaded_by=" parent ")
    assert receipt["capture"]["uploaded_by"] == "parent"


def test_health_chooses_the_latest_heartbeat_at_full_saved_precision(db):
    capture(db)
    first = store.claim_job(db, "2026-01-02T03:04:05Z")
    capture(db, SECOND_ID)
    second = store.claim_job(db, "2026-01-02T03:04:05.000001Z")
    assert first["id"] != second["id"]
    assert store.health(db)["worker_seen"] == "2026-01-02T03:04:05.000001Z"
