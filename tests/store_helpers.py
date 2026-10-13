"""Invented records and temporary databases shared by store tests."""
from importlib.resources import files

import pytest

from home_library import store


@pytest.fixture
def db(tmp_path):
    connection = store.open(tmp_path / "private")
    yield connection
    connection.close()


CAPTURE_ID = "10000000-0000-4000-8000-000000000001"


SECOND_ID = "10000000-0000-4000-8000-000000000002"


NOW = "2026-01-02T03:04:05Z"


def capture(db, id=CAPTURE_ID, **changes):
    if not store.locations(db):
        store.add_location(db, "Shelf A", "shelf", now=NOW)
    fields = dict(id=id, kind="shelf", location_id=1, default_state="Active", uploaded_by="parent",
                  original_name="generated.jpg", media_type="image/jpeg", sha256="a" * 64, bytes=120, now=NOW)
    fields.update(changes)
    return store.add_capture(db, **fields)


RECORD_COLUMNS = (
    "title sort_key author illustrator publisher year language isbn series age_from age_to tags state location "
    "cover_photo source source_id needs_review notes photo read_status other_reading catalogue_title other_text "
    "where read_ids pick_verdict candidate_count").split()


def record(title="Měsíční člun", **changes):
    row = dict.fromkeys(RECORD_COLUMNS, "")
    row.update(title=title, sort_key=title, language="cs", read_status="agreed", needs_review=True,
               candidate_count=0, photo="generated.jpg", where="r1c1-r0.jpg, #1", read_ids="a; b")
    row.update(changes)
    return row


def finish(db, rows, id=CAPTURE_ID, **changes):
    receipt = capture(db, id, **changes)
    job = store.claim_job(db, NOW)
    assert job["id"] == receipt["job"]["id"]
    store.finish_job(db, job["id"], job["owner"], rows, NOW)
    return store.observations(db, capture_id=id)


def typed_book(db, **changes):
    if not store.locations(db):
        store.add_location(db, "Shelf A", "shelf", now=NOW)
    return store.add_book(db, {"title": " Měsíční člun ", "location_id": 1, **changes}, "parent", now=NOW)


EXPORT_COLUMNS = (
    "title sort_key author illustrator publisher year language isbn series age_from age_to tags "
    "state location cover_photo source source_id needs_review notes").split()


def migration_directory(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    for resource in files("home_library.migrations").iterdir():
        if resource.name.endswith(".sql"):
            (directory / resource.name).write_text(resource.read_text(encoding="utf-8"))
    return directory
