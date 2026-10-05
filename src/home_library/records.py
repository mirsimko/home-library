"""Stage 6: one record per book, as JSON and CSV."""
from __future__ import annotations


COLUMNS = ["title", "sort_key", "author", "illustrator", "publisher", "year", "language", "isbn", "series",
           "age_from", "age_to", "tags", "state", "location", "cover_photo", "source", "source_id",
           "needs_review", "notes", "photo", "read_status", "other_reading", "catalogue_title", "other_text",
           "where", "read_ids", "pick_verdict", "candidate_count"]


def _empty() -> dict:
    record = {column: "" for column in COLUMNS}
    record["needs_review"] = True
    record["candidate_count"] = 0
    return record


def _item_record(photo: str, item: dict) -> dict:
    first = item["readings"][0]
    record = _empty()
    record.update(title=item["title"], sort_key=item["title"], language=item["language"], photo=photo,
                  read_status=item["reason"], other_text=first["other_text"], where=first["where"],
                  read_ids="; ".join(r["read_id"] for r in item["readings"]))
    return record


def build_records(merged: dict, candidates: dict | None = None, picks: dict | None = None, *,
                  location: str = "") -> list:
    return [_item_record(merged["file"], item) for item in merged["items"]]
