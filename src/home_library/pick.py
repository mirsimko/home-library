"""Stage 6: pick the catalogue candidate that is the book."""
import hashlib
import json
import subprocess
from pathlib import Path

from home_library.merge import match_key
from home_library.workspace import refuse_inside_checkout

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
    for number, book in enumerate(_books_with_candidates(candidates), start=1):
        lines = [f"Book {number}", f"  Title as read: {book['title']}", f"  Language: {book['language']}"]
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
            except (ValueError, RecursionError):
                continue
            if isinstance(value, dict) and isinstance(value.get("picks"), list):
                return value
    return None


def _none(item: int, reason: str) -> dict:
    return {"item": item, "verdict": "none", "candidate_id": None, "reason": reason}


def _check(book: dict, pick) -> dict:
    item, ids = book["item"], {cand["id"] for cand in book["candidates"]}
    if pick is None:
        return _none(item, "The model gave no answer for this book.")
    echoed = pick.get("title")
    if not isinstance(echoed, str) or match_key(echoed) != match_key(book["title"]):
        return _none(item, f"The model answered for the title {echoed!r}, not this book's; the answer was rejected.")
    verdict = pick.get("verdict")
    reason = pick.get("reason")
    reason = reason if isinstance(reason, str) else ""
    if verdict not in ("match", "ambiguous", "none"):
        return _none(item, f"The model gave an unknown verdict: {verdict!r}.")
    if verdict == "match":
        cid = pick.get("candidate_id")
        if not isinstance(cid, str) or cid not in ids:
            return _none(item, f"The model named candidate {cid}, which was not fetched for this book; the answer was rejected.")
        return {"item": item, "verdict": verdict, "candidate_id": cid, "reason": reason}
    return {"item": item, "verdict": verdict, "candidate_id": None, "reason": reason}


def _books_with_candidates(candidates: dict) -> list:
    return [book for book in candidates["books"] if book["candidates"]]


def _none_for_all(candidates: dict, reason: str) -> dict:
    return {"file": candidates["file"], "picks": [_none(book["item"], reason) for book in _books_with_candidates(candidates)]}


def parse_picks(raw: str, candidates: dict) -> dict:
    answer = _find_object(raw)
    if answer is None:
        return _none_for_all(candidates, "The answer could not be read as a list of picks.")
    # The model numbers the books by position, as the prompt does, and echoes each title as a check.
    by_number = {pick["book"]: pick for pick in answer["picks"]
                 if isinstance(pick, dict) and type(pick.get("book")) is int}
    picks = [_check(book, by_number.get(number))
             for number, book in enumerate(_books_with_candidates(candidates), start=1)]
    return {"file": candidates["file"], "picks": picks}


def _made_for(merged: dict, candidates: dict) -> str:
    """A fingerprint of everything the pick model is shown: the readings and the candidates."""
    return hashlib.sha256(build_prompt(merged, candidates).encode("utf-8")).hexdigest()


def stored_picks(photo_dir, merged: dict, candidates: dict):
    """The stored picks.json, if it was made for exactly these readings and candidates; otherwise None."""
    try:
        picks = json.loads((Path(photo_dir) / "lookup" / "picks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(picks, dict) or picks.get("made_for") != _made_for(merged, candidates):
        return None
    return picks


def run_pick(photo_dir, *, run=subprocess.run, timeout=300) -> dict:
    """Ask the model once and write picks.json. A model call that fails gives `none` for every book."""
    photo_dir = refuse_inside_checkout(photo_dir)
    lookup_dir = photo_dir / "lookup"
    merged = json.loads((photo_dir / "merged.json").read_text(encoding="utf-8"))
    candidates = json.loads((lookup_dir / "candidates.json").read_text(encoding="utf-8"))
    failure = None
    if not _books_with_candidates(candidates):
        picks = {"file": candidates["file"], "picks": []}
    else:
        raw, failure = _ask(lookup_dir, build_prompt(merged, candidates), run, timeout)
        if failure:
            picks = _none_for_all(candidates, f"The pick step failed: {failure}.")
        else:
            picks = parse_picks(raw, candidates)
    picks.update(made_for=_made_for(merged, candidates), failed=failure is not None)
    text = json.dumps(picks, indent=2, ensure_ascii=False) + "\n"
    (lookup_dir / "picks.json").write_text(text, encoding="utf-8")
    return picks


def _ask(lookup_dir: Path, prompt: str, run, timeout):
    """Run the model once. Returns (answer, None), or (None, why it failed)."""
    raw_file = lookup_dir / "picks.raw.txt"
    command = ["codex", "exec", "--ignore-user-config", "-m", "gpt-6.1-sol",
               "-c", 'model_reasoning_effort="low"', "-s", "read-only", "--skip-git-repo-check",
               "--ephemeral", "-C", str(lookup_dir), "-o", str(raw_file), "-"]
    raw_file.unlink(missing_ok=True)  # an answer of an earlier run must not be taken for this one
    try:
        done = run(command, input=prompt, cwd=str(lookup_dir), timeout=timeout,
                   capture_output=True, text=True, encoding="utf-8")
    except subprocess.TimeoutExpired:
        return None, f"codex timed out after {timeout} seconds"
    except OSError as error:
        return None, f"codex not found or could not be run: {error}"
    if done.returncode != 0:
        return None, f"codex exit code {done.returncode}"
    try:
        return raw_file.read_text(encoding="utf-8"), None
    except OSError:
        return None, "no answer file from codex"
