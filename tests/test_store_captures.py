"""The catalog store keeps private evidence separate from books."""

import pytest
from store_helpers import (
    CAPTURE_ID,
    NOW,
    SECOND_ID,
    capture,
)
from store_helpers import db as db

from home_library import store


def test_a_capture_and_its_single_job_have_an_idempotent_receipt(db):
    receipt = capture(db)
    assert receipt["created"] is True
    assert isinstance(receipt["capture"], dict) and isinstance(receipt["job"], dict)
    assert receipt["capture"]["created_at"] == NOW
    assert receipt["job"]["capture_id"] == CAPTURE_ID
    assert (receipt["job"]["status"], receipt["job"]["attempts"]) == ("queued", 0)
    repeated = capture(db, uploaded_by="other", original_name="changed.jpg")
    assert repeated == {**receipt, "created": False}
    with pytest.raises(store.Conflict, match="different"):
        capture(db, sha256="b" * 64)
    duplicate = capture(db, SECOND_ID)
    assert duplicate["duplicate_of"] == [CAPTURE_ID]
    assert duplicate["created"] is True
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2


@pytest.mark.parametrize("changes", [
    {"id": "../escape"}, {"id": CAPTURE_ID.upper().replace("10000000", "ABCDEF00")},
    {"id": CAPTURE_ID.replace("-", "")}, {"id": "{" + CAPTURE_ID + "}"}, {"id": " " + CAPTURE_ID},
    {"id": None}, {"kind": "portrait"}, {"default_state": "active"}, {"default_state": "Lost"},
    {"group_id": "../group"},
])
def test_capture_ids_kinds_states_and_group_ids_are_validated(db, changes):
    with pytest.raises(store.Invalid):
        capture(db, **changes)
    assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_a_capture_requires_an_existing_location(db):
    with pytest.raises(store.NotFound):
        capture(db, location_id=999)
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


@pytest.mark.parametrize("changes", [
    {"sha256": "not a hash"}, {"sha256": None}, {"bytes": -1}, {"bytes": "120"},
    {"media_type": "application/pdf"}, {"uploaded_by": " "}, {"original_name": None},
])
def test_bad_capture_metadata_is_invalid_and_never_queues_work(db, changes):
    with pytest.raises(store.Invalid):
        capture(db, **changes)
    assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
