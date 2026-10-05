"""Stage 6: pick the catalogue candidate that is the book."""
import json
from pathlib import Path

_FIELDS = ("title", "title_reading", "authors", "publisher", "year", "series", "isbn")


def _candidate_lines(cand: dict) -> list:
    lines = [f"  Candidate {cand['id']}"]
    for field in _FIELDS:
        value = cand.get(field)
        if isinstance(value, list):
            value = "; ".join(value)
        if value:
            lines.append(f"    {field}: {value}")
    return lines


def build_prompt(merged: dict, candidates: dict) -> str:
    parts = [(Path(__file__).parent / "prompts" / "pick.txt").read_text(encoding="utf-8")]
    for book in candidates["books"]:
        if not book["candidates"]:
            continue
        lines = [f"Book {book['item']}", f"  Title as read: {book['title']}", f"  Language: {book['language']}"]
        for reading in merged["items"][book["item"]]["readings"]:
            lines.append(f"  Other text on the book ({reading['read_id']}): {reading['other_text']}")
        for cand in book["candidates"]:
            lines.extend(_candidate_lines(cand))
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def _find_object(raw: str):
    decoder = json.JSONDecoder()
    for start, ch in enumerate(raw):
        if ch == "{":
            try:
                value, _ = decoder.raw_decode(raw, start)
            except ValueError:
                continue
            if isinstance(value, dict) and isinstance(value.get("picks"), list):
                return value
    return None


def _none(item: int, reason: str) -> dict:
    return {"item": item, "verdict": "none", "candidate_id": None, "reason": reason}


def _check(item: int, pick: dict, ids: set) -> dict:
    if pick is None:
        return _none(item, "The model gave no answer for this book.")
    if pick["verdict"] == "match" and pick["candidate_id"] not in ids:
        return _none(item, f"The model named candidate {pick['candidate_id']}, which was not fetched for this book; the answer was rejected.")
    return pick


def parse_picks(raw: str, candidates: dict) -> dict:
    answer = _find_object(raw)
    by_item = {pick["item"]: pick for pick in answer["picks"]}
    picks = []
    for book in candidates["books"]:
        if book["candidates"]:
            ids = {c["id"] for c in book["candidates"]}
            picks.append(_check(book["item"], by_item.get(book["item"]), ids))
    return {"file": candidates["file"], "picks": picks}
