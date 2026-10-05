"""Stage 6: one record per book, as JSON and CSV."""
from __future__ import annotations

import csv
import json
import re

from home_library.workspace import refuse_inside_checkout


COLUMNS = ["title", "sort_key", "author", "illustrator", "publisher", "year", "language", "isbn", "series",
           "age_from", "age_to", "tags", "state", "location", "cover_photo", "source", "source_id",
           "needs_review", "notes", "photo", "read_status", "other_reading", "catalogue_title", "other_text",
           "where", "read_ids", "pick_verdict", "candidate_count"]


def _empty() -> dict:
    record = {column: "" for column in COLUMNS}
    record["needs_review"] = True
    record["candidate_count"] = 0
    return record


def _item_record(photo: str, item: dict, location: str) -> dict:
    first = item["readings"][0]
    record = _empty()
    record.update(title=item["title"], sort_key=item["title"], language=item["language"], photo=photo,
                  read_status=item["reason"], location=location, other_text=first["other_text"], where=first["where"],
                  read_ids="; ".join(r["read_id"] for r in item["readings"]))
    if len(item["readings"]) > 1 and item["readings"][1]["title"] != item["readings"][0]["title"]:
        record["other_reading"] = item["readings"][1]["title"]
    return record


def _unreadable_record(photo: str, entry: dict, location: str) -> dict:
    record = _empty()
    record.update(photo=photo, location=location, language=entry["language"], read_status="unreadable", other_text=entry["other_text"],
                  where=entry["where"], read_ids=entry["read_id"],
                  notes="Could not be read from the shelf photo; needs a cover photo.")
    return record


def _find(candidates: dict | None, picks: dict | None, index: int):
    """The book's candidate list and its pick, or empty values."""
    books = (candidates or {}).get("books", [])
    book = next((b for b in books if b["item"] == index), None)
    pick = next((p for p in (picks or {}).get("picks", []) if p["item"] == index), None)
    return (book["candidates"] if book else []), pick


def _fill_catalogue(record: dict, cand: dict) -> None:
    record.update(catalogue_title=cand["title"], author="; ".join(cand["authors"]), publisher=cand["publisher"],
                  year=cand["year"], isbn=cand["isbn"], series=cand["series"], source=cand["source"],
                  source_id=cand["source_id"])
    span = re.search(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)", cand["age_note"])
    first = re.search(r"\d+", cand["age_note"])
    record["age_from"] = span.group(1) if span else first.group(0) if first else ""
    record["age_to"] = span.group(2) if span else ""
    if cand["title_reading"]:
        record["sort_key"] = cand["title_reading"]


def _notes(item: dict, pick: dict | None, matched: dict | None) -> str:
    sentences = []
    if item["reason"] == "solo":
        sentences.append(f"Only {item['readings'][0]['read_id']} gave this title.")
    elif item["reason"] == "near":
        sentences.append("The two reads differ.")
    elif item["reason"] == "partial":
        sentences.append("Partly legible.")
    guess = next((r["inferred"] for r in item["readings"] if r["inferred"]), "")
    if guess:
        sentences.append(f"Guess: {guess}.")
    if pick and pick["verdict"] == "ambiguous":
        sentences.append(f"Catalogue match ambiguous: {pick['reason']}")
    if matched and matched["audience"]:
        sentences.append(f"Catalogue audience: {matched['audience']}.")
    if matched and matched["age_note"]:
        sentences.append(f"Catalogue age note: {matched['age_note']}.")
    return " ".join(sentences)


def build_records(merged: dict, candidates: dict | None = None, picks: dict | None = None, *,
                  location: str = "") -> list:
    records = []
    for index, item in enumerate(merged["items"]):
        record = _item_record(merged["file"], item, location)
        cands, pick = _find(candidates, picks, index)
        record["candidate_count"] = len(cands)
        matched = None
        if pick:
            record["pick_verdict"] = pick["verdict"]
            if pick["verdict"] == "match":
                matched = next((c for c in cands if c["id"] == pick["candidate_id"]), None)
            if matched:
                _fill_catalogue(record, matched)
        record["notes"] = _notes(item, pick, matched)
        records.append(record)
    first_read = merged["reads"][0] if merged["reads"] else None
    for entry in merged["unreadable"]:
        if entry["read_id"] == first_read:
            records.append(_unreadable_record(merged["file"], entry, location))
    return records


def _cell(value) -> str:
    if value is True:
        return "true"
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def write_records(photo_dir, records: list) -> None:
    photo_dir = refuse_inside_checkout(photo_dir)
    (photo_dir / "records.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with open(photo_dir / "records.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for record in records:
            writer.writerow([_cell(record[column]) for column in COLUMNS])
