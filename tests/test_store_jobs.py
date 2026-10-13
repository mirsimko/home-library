"""The catalog store keeps private evidence separate from books."""
from datetime import datetime, timedelta, timezone

import pytest
from store_helpers import (
    CAPTURE_ID,
    NOW,
    SECOND_ID,
    capture,
    finish,
    record,
    typed_book,
)
from store_helpers import db as db

from home_library import store


def test_claims_are_oldest_first_and_carry_capture_and_location(db):
    later = capture(db, now="2026-01-02T03:04:06Z")
    earlier = capture(db, SECOND_ID)
    statements = []
    db.set_trace_callback(statements.append)
    job = store.claim_job(db, NOW)
    db.set_trace_callback(None)
    assert "BEGIN IMMEDIATE" in statements
    assert job["id"] == earlier["job"]["id"]
    assert job["capture"] == earlier["capture"]
    assert job["location"] == "Shelf A"
    assert (job["status"], job["attempts"], job["heartbeat_at"], job["started_at"]) == ("running", 1, NOW, NOW)
    assert job["owner"]
    second = store.claim_job(db, NOW)
    assert second["id"] == later["job"]["id"]
    assert second["owner"] != job["owner"]
    assert store.claim_job(db, NOW) is None


def test_stale_jobs_are_reclaimed_only_after_twenty_minutes(db):
    capture(db)
    first = store.claim_job(db, NOW)
    assert store.claim_job(db, "2026-01-02T03:24:05Z") is None
    second = store.claim_job(db, "2026-01-02T03:24:06Z")
    assert second["id"] == first["id"]
    assert second["attempts"] == 2
    assert second["owner"] != first["owner"]
    assert not store.heartbeat(db, first["id"], first["owner"], "2026-01-02T03:30:00Z")
    assert store.heartbeat(db, second["id"], second["owner"], "2026-01-02T03:30:00Z")
    assert store.claim_job(db, "2026-01-02T03:49:59Z") is None
    third = store.claim_job(db, "2026-01-02T03:50:01Z")
    assert third["attempts"] == 3
    capture(db, SECOND_ID)
    next_job = store.claim_job(db, "2026-01-02T04:11:00Z")
    assert next_job["capture_id"] == SECOND_ID
    failed = capture(db)["job"]
    assert failed["status"] == "failed"
    assert failed["error"] == "the worker stopped responding 3 times"
    assert failed["finished_at"] == "2026-01-02T04:11:00Z"
    assert not store.heartbeat(db, failed["id"], third["owner"], "2026-01-02T04:12:00Z")


def test_failure_requeues_twice_then_stays_visible_until_retry(db):
    receipt = capture(db)
    for attempt in range(1, 4):
        job = store.claim_job(db, NOW)
        assert job["attempts"] == attempt
        failed = store.fail_job(db, job["id"], job["owner"], "invented failure", NOW)
        assert failed["status"] == ("queued" if attempt < 3 else "failed")
        assert failed["error"] == "invented failure"
        assert not store.heartbeat(db, job["id"], job["owner"], NOW)
    assert store.claim_job(db, NOW) is None
    retried = store.retry_job(db, receipt["job"]["id"])
    assert retried["status"] == "queued" and retried["attempts"] == 0
    assert retried["owner"] is None and retried["finished_at"] is None
    assert store.claim_job(db, NOW)["attempts"] == 1


def test_a_superseded_worker_cannot_fail_or_retry_a_running_job(db):
    capture(db)
    old = store.claim_job(db, NOW)
    current = store.claim_job(db, "2026-01-02T03:25:00Z")
    before = capture(db)["job"]
    with pytest.raises(store.Conflict):
        store.fail_job(db, old["id"], old["owner"], "late failure", NOW)
    assert capture(db)["job"] == before
    with pytest.raises(store.Invalid):
        store.retry_job(db, current["id"])
    assert capture(db)["job"] == before
    with pytest.raises(store.NotFound):
        store.fail_job(db, 999, "absent", "failure", NOW)
    with pytest.raises(store.NotFound):
        store.retry_job(db, 999)


def test_finishing_imports_whole_records_as_open_evidence_and_no_books(db):
    receipt = capture(db)
    job = store.claim_job(db, NOW)
    rows = [record(other_reading="Měsíční loď"), record("", read_status="unreadable")]
    done = store.finish_job(db, job["id"], job["owner"], rows, NOW)
    assert done["status"] == "done" and done["finished_at"] == NOW
    observations = store.observations(db)
    assert [r["record"] for r in observations] == rows
    assert [(r["attempt"], r["row"], r["status"]) for r in observations] == [(1, 0, "open"), (1, 1, "open")]
    assert observations[0]["capture"] == receipt["capture"]
    assert observations[0]["other_reading"] == "Měsíční loď"
    assert observations[0]["created_at"] == NOW
    assert store.observations(db, capture_id=SECOND_ID) == []
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0
    assert not store.heartbeat(db, job["id"], job["owner"], NOW)


def test_a_late_finish_changes_nothing(db):
    capture(db)
    old = store.claim_job(db, NOW)
    store.claim_job(db, "2026-01-02T03:25:00Z")
    before = capture(db)["job"]
    with pytest.raises(store.Conflict):
        store.finish_job(db, old["id"], old["owner"], [record()], NOW)
    assert capture(db)["job"] == before
    assert store.observations(db) == []


@pytest.mark.parametrize("rows", [{}, [None], [record(), {"title": 3}], [record(), {"title": "x", "notes": object()}]])
def test_a_bad_import_leaves_the_job_and_all_observations_unchanged(db, rows):
    capture(db)
    job = store.claim_job(db, NOW)
    before = capture(db)["job"]
    with pytest.raises(store.Invalid):
        store.finish_job(db, job["id"], job["owner"], rows, NOW)
    assert store.observations(db) == []
    assert capture(db)["job"] == before


def test_reruns_keep_evidence_and_supersede_earlier_open_rows(db):
    (old,) = finish(db, [record()])
    store.retry_job(db, capture(db)["job"]["id"])
    job = store.claim_job(db, NOW)
    assert job["attempts"] == 1
    store.finish_job(db, job["id"], job["owner"], [record("Hvězdná bárka")], NOW)
    (new,) = store.observations(db)
    assert (new["attempt"], new["row"]) == (2, 0)
    assert new["title"] == "Hvězdná bárka"
    assert store.observations(db, "superseded")[0]["id"] == old["id"]
    store.retry_job(db, job["id"])
    third = store.claim_job(db, NOW)
    store.finish_job(db, third["id"], third["owner"], [], NOW)
    assert store.observations(db) == []
    assert len(store.observations(db, "superseded")) == 2


def test_every_stamped_write_accepts_an_injected_utc_time(db):
    local = datetime(2026, 1, 2, 12, 4, 5, tzinfo=timezone(timedelta(hours=9)))
    assert store.add_location(db, "Shelf A", "shelf", now=local)["created_at"] == NOW
    receipt = capture(db, now=local)
    assert receipt["capture"]["created_at"] == NOW
    job = store.claim_job(db, local)
    assert job["started_at"] == job["heartbeat_at"] == NOW
    assert store.heartbeat(db, job["id"], job["owner"], local + timedelta(seconds=1))
    assert capture(db)["job"]["heartbeat_at"] == "2026-01-02T03:04:06Z"
    assert store.fail_job(db, job["id"], job["owner"], "test", local)["finished_at"] == NOW
    job = store.claim_job(db, local)
    assert store.finish_job(db, job["id"], job["owner"], [record()], local)["finished_at"] == NOW
    (observation,) = store.observations(db)
    assert observation["created_at"] == NOW
    approved = store.approve(db, [observation["id"]], {}, "reviewer", now=local)
    assert approved["created_at"] == approved["updated_at"] == NOW
    added = typed_book(db)
    calls = []

    def clock():
        calls.append(1)
        return local + timedelta(days=1)

    updated = store.update_book(db, added["id"], 1, {"notes": "Timed edit"}, "editor", now=clock)
    assert updated["updated_at"] == "2026-01-03T03:04:05Z" and calls == [1]
    (cover,) = finish(db, [record()], SECOND_ID, kind="cover", now=local)
    attached = store.attach(db, [cover["id"]], added["id"], "reviewer", now=local)
    assert attached["updated_at"] == NOW
    moved = store.move_books(db, [added["id"], approved["id"]], state="Gone", by="mover", now=clock)
    assert [b["updated_at"] for b in moved] == ["2026-01-03T03:04:05Z"] * 2
    assert calls == [1, 1]


@pytest.mark.parametrize("now", ["bad time", "2026-01-02T03:04:05", datetime(2026, 1, 2), 42])
def test_naive_or_malformed_times_do_not_create_a_location(db, now):
    with pytest.raises(store.Invalid, match="time"):
        store.add_location(db, "Shelf A", "shelf", now=now)
    assert store.locations(db) == []


def test_claim_order_and_the_stale_boundary_preserve_microseconds(db):
    capture(db, now="2026-01-02T03:04:05.000002Z")
    capture(db, SECOND_ID, now="2026-01-02T03:04:05.000001Z")
    first = store.claim_job(db, NOW)
    assert first["capture_id"] == SECOND_ID
    second = store.claim_job(db, NOW)
    assert second["capture_id"] == CAPTURE_ID
    assert store.claim_job(db, "2026-01-02T03:24:05Z") is None
    reclaimed = store.claim_job(db, "2026-01-02T03:24:05.000001Z")
    assert reclaimed["id"] == first["id"] and reclaimed["attempts"] == 2


def test_two_connections_contending_for_one_job_never_share_an_owner(db, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    capture(db)
    ready = Barrier(2)

    def worker():
        connection = store.open(tmp_path / "private")
        try:
            ready.wait(timeout=5)
            return store.claim_job(connection, NOW)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: worker(), range(2)))
    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1 and claimed[0]["attempts"] == 1
    assert capture(db)["job"]["owner"] == claimed[0]["owner"]


def test_releasing_a_job_puts_it_back_in_the_queue_without_costing_an_attempt(db):
    capture(db)
    job = store.claim_job(db, NOW)
    assert job["attempts"] == 1
    released = store.release_job(db, job["id"], job["owner"])
    assert (released["status"], released["attempts"], released["owner"], released["heartbeat_at"]) == (
        "queued", 0, None, None)
    assert released["error"] is None
    again = store.claim_job(db, NOW)  # no need to wait for a lease to go stale
    assert again["id"] == job["id"] and again["attempts"] == 1 and again["owner"] != job["owner"]


def test_a_release_gives_back_one_attempt_and_never_goes_below_zero(db):
    capture(db)
    store.claim_job(db, NOW)
    second = store.claim_job(db, "2026-01-02T03:24:06Z")
    assert second["attempts"] == 2
    assert store.release_job(db, second["id"], second["owner"])["attempts"] == 1
    db.execute("UPDATE jobs SET status = 'running', owner = 'x', attempts = 0 WHERE id = ?", (second["id"],))
    assert store.release_job(db, second["id"], "x")["attempts"] == 0


def test_only_the_owner_of_a_running_job_can_release_it(db):
    capture(db)
    job = store.claim_job(db, NOW)
    for owner in ("someone else", None):
        with pytest.raises(store.Conflict):
            store.release_job(db, job["id"], owner)
    with pytest.raises(store.NotFound):
        store.release_job(db, 999, job["owner"])
    store.finish_job(db, job["id"], job["owner"], [record()], NOW)
    with pytest.raises(store.Conflict):
        store.release_job(db, job["id"], job["owner"])
