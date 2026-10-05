"""Stage 6: one record per book, as JSON and CSV."""
from __future__ import annotations

import re


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
    record.update(photo=photo, location=location, read_status="unreadable", other_text=entry["other_text"],
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
    ages = re.findall(r"\d+", cand["age_note"])
    record["age_from"] = ages[0] if ages else ""
    record["age_to"] = ages[1] if len(ages) > 1 else ""
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
        if pick:
            record["pick_verdict"] = pick["verdict"]
            matched = next((c for c in cands if c["id"] == pick["candidate_id"]), None)
            if pick["verdict"] != "match":
                matched = None
            if matched:
                _fill_catalogue(record, matched)
        else:
            matched = None
        record["notes"] = _notes(item, pick, matched)
        records.append(record)
    first_read = merged["reads"][0] if merged["reads"] else None
    for entry in merged["unreadable"]:
        if entry["read_id"] == first_read:
            records.append(_unreadable_record(merged["file"], entry, location))
    return records
