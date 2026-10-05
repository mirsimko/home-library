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
                  read_status=item["reason"], location=location, other_text=first["other_text"],
                  where=first["where"],
                  read_ids="; ".join(r["read_id"] for r in item["readings"]))
    if len(item["readings"]) > 1 and item["readings"][1]["title"] != item["readings"][0]["title"]:
        record["other_reading"] = item["readings"][1]["title"]
    return record


def _unreadable_record(photo: str, entry: dict, location: str) -> dict:
    notes = "Could not be read from the shelf photo; needs a cover photo."
    if entry["inferred"]:
        notes += f" Guess: {entry['inferred']}."
    record = _empty()
    record.update(photo=photo, location=location, language=entry["language"], read_status="unreadable",
                  other_text=entry["other_text"], where=entry["where"], read_ids=entry["read_id"], notes=notes)
    return record


def _lost_records(photo: str, merged: dict, location: str) -> list:
    """Rows for what a read lost: each entry that could not be parsed, and each read that was cut off."""
    records = []
    for error in merged["parse_errors"]:
        record = _empty()
        record.update(photo=photo, location=location, read_status="unparsed", read_ids=error["read_id"],
                      other_text=error["raw"],
                      notes=f"One entry of {error['read_id']}'s answer could not be read as data "
                            f"({error['reason']}). Its text is in other_text.")
        records.append(record)
    listed = {error["read_id"] for error in merged["parse_errors"]}
    for read_id in merged.get("incomplete", []):
        if read_id not in listed:
            record = _empty()
            record.update(photo=photo, location=location, read_status="incomplete", read_ids=read_id,
                          notes=f"The answer of {read_id} was cut off or damaged. Books may be missing from "
                                "this photo; run that read again.")
            records.append(record)
    return records


def _find(candidates: dict | None, picks: dict | None, index: int):
    """The book's look-up entry and its pick, or None for each."""
    book = next((b for b in (candidates or {}).get("books", []) if b["item"] == index), None)
    pick = next((p for p in (picks or {}).get("picks", []) if p["item"] == index), None)
    return book, pick


_AGES = (re.compile(r"(?<!\d)(\d{1,2})(?:\s*(?:[-\u2013\u2014]|do)\s*(\d{1,2}))?\s+let\b"),  # od 3 let, 5-8 let
         re.compile(r"\bages?\s+(\d{1,2})(?:\s*(?:[-\u2013\u2014]|to)\s*(\d{1,2}))?", re.IGNORECASE))


def _ages(age_note: str):
    """An age in years from a catalogue's note. A grade, a reading level or a year is not an age."""
    for pattern in _AGES:
        found = pattern.search(age_note)
        if found:
            return found.group(1), found.group(2) or ""
    return "", ""


def _fill_catalogue(record: dict, cand: dict) -> None:
    record.update(catalogue_title=cand["title"], author="; ".join(cand["authors"]), publisher=cand["publisher"],
                  year=cand["year"], isbn=cand["isbn"], series=cand["series"], source=cand["source"],
                  source_id=cand["source_id"])
    record["age_from"], record["age_to"] = _ages(cand["age_note"])
    if cand["title_reading"]:
        record["sort_key"] = cand["title_reading"]


def _lookup_note(item: dict, book: dict | None):
    if book is None:
        return None
    failed = [f"{q['source']} {q['status']}" for q in book["queries"] if q["status"] not in ("ok", "no_match")]
    if failed:
        return f"Catalogue look-up failed: {', '.join(failed)}."
    if not book["queries"] and not book["candidates"]:
        return f"Not looked up: no catalogue for the language {item['language']}."
    return None


def _notes(item: dict, book: dict | None, pick: dict | None, matched: dict | None) -> str:
    sentences = []
    if item["reason"] == "solo":
        sentences.append(f"Only {item['readings'][0]['read_id']} gave this title.")
    elif item["reason"] == "near":
        sentences.append("The two reads differ.")
    elif item["reason"] == "split":
        sentences.append("The two reads agree on the words but not on which of them are the title.")
    elif item["reason"] == "partial":
        sentences.append("Partly legible.")
    guess = next((r["inferred"] for r in item["readings"] if r["inferred"]), "")
    if guess:
        sentences.append(f"Guess: {guess}.")
    lookup = _lookup_note(item, book)
    if lookup:
        sentences.append(lookup)
    if pick and pick["verdict"] == "ambiguous":
        sentences.append(f"Catalogue match ambiguous: {pick['reason']}")
    if pick and pick["verdict"] == "none":
        sentences.append(f"No catalogue match: {pick['reason']}")
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
        book, pick = _find(candidates, picks, index)
        cands = book["candidates"] if book else []
        record["candidate_count"] = len(cands)
        matched = None
        if pick:
            record["pick_verdict"] = pick["verdict"]
            if pick["verdict"] == "match":
                matched = next((c for c in cands if c["id"] == pick["candidate_id"]), None)
            if matched:
                _fill_catalogue(record, matched)
        record["notes"] = _notes(item, book, pick, matched)
        records.append(record)
    first_read = merged["reads"][0] if merged["reads"] else None
    for entry in merged["unreadable"]:
        if entry["read_id"] == first_read:
            records.append(_unreadable_record(merged["file"], entry, location))
    return records + _lost_records(merged["file"], merged, location)


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
