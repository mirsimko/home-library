"""Stage 6: pick the catalogue candidate that is the book."""
import json
import subprocess
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


def _check(item: int, pick, ids: set) -> dict:
    if pick is None:
        return _none(item, "The model gave no answer for this book.")
    if not isinstance(pick, dict):
        return _none(item, "The model's answer for this book was not an object.")
    verdict = pick.get("verdict")
    reason = pick.get("reason")
    reason = reason if isinstance(reason, str) else ""
    if verdict not in ("match", "ambiguous", "none"):
        return _none(item, f"The model gave an unknown verdict: {verdict!r}.")
    if verdict == "match":
        cid = pick.get("candidate_id")
        if cid not in ids:
            return _none(item, f"The model named candidate {cid}, which was not fetched for this book; the answer was rejected.")
        return {"item": item, "verdict": verdict, "candidate_id": cid, "reason": reason}
    return {"item": item, "verdict": verdict, "candidate_id": None, "reason": reason}


def books_with_candidates(candidates: dict) -> list:
    return [book for book in candidates["books"] if book["candidates"]]


def none_for_all(candidates: dict, reason: str) -> dict:
    return {"file": candidates["file"], "picks": [_none(book["item"], reason) for book in books_with_candidates(candidates)]}


def parse_picks(raw: str, candidates: dict) -> dict:
    answer = _find_object(raw)
    if answer is None:
        return none_for_all(candidates, "The answer could not be read as a list of picks.")
    by_item = {pick["item"]: pick for pick in answer["picks"]
               if isinstance(pick, dict) and type(pick.get("item")) is int}
    picks = []
    for book in books_with_candidates(candidates):
        ids = {c["id"] for c in book["candidates"]}
        picks.append(_check(book["item"], by_item.get(book["item"]), ids))
    return {"file": candidates["file"], "picks": picks}


def _write_picks(lookup_dir: Path, picks: dict) -> None:
    text = json.dumps(picks, indent=2, ensure_ascii=False) + "\n"
    (lookup_dir / "picks.json").write_text(text, encoding="utf-8")


def run_pick(photo_dir, *, run=subprocess.run, timeout=300) -> dict:
    photo_dir = Path(photo_dir)
    lookup_dir = photo_dir / "lookup"
    merged = json.loads((photo_dir / "merged.json").read_text(encoding="utf-8"))
    candidates = json.loads((lookup_dir / "candidates.json").read_text(encoding="utf-8"))
    if not books_with_candidates(candidates):
        picks = {"file": candidates["file"], "picks": []}
    else:
        raw_file = lookup_dir / "picks.raw.txt"
        command = ["codex", "exec", "--ignore-user-config", "-m", "gpt-6.1-sol",
                   "-c", 'model_reasoning_effort="low"', "-s", "read-only", "--skip-git-repo-check",
                   "--ephemeral", "-C", str(lookup_dir), "-o", str(raw_file), "-"]
        run(command, input=build_prompt(merged, candidates), cwd=str(lookup_dir), timeout=timeout,
            capture_output=True, text=True, encoding="utf-8")
        picks = parse_picks(raw_file.read_text(encoding="utf-8"), candidates)
    _write_picks(lookup_dir, picks)
    return picks
