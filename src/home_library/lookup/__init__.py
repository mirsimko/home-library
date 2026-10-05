"""Stage 5, look-up: candidate catalogue records for a title (docs/pipeline.md)."""
import hashlib
import json
import os
from pathlib import Path

from home_library.lookup import loc, ndl, nkcr, openbd, openlibrary
from home_library.lookup.errors import RateLimited, Unavailable
from home_library.lookup.isbn import normalize_isbn

MAX_REQUESTS_PER_SOURCE = 3
SOURCES = {"ja": [ndl, openbd], "cs": [nkcr], "en": [openlibrary, loc]}


def _unique(candidates):
    seen, unique = set(), []
    for candidate in candidates:
        if candidate["id"] not in seen:
            seen.add(candidate["id"])
            unique.append(candidate)
    return unique


def _short_title(title):
    words = title.split()
    if len(words) > 3:
        return " ".join(words[:3])
    if len(words) == 1 and len(words[0]) >= 6:
        return words[0][: len(words[0]) // 2]
    return None


def _steps(source, title, author, isbn):
    steps = []
    if isbn:
        steps.append(("isbn", [isbn], lambda fetch: source.by_isbn(isbn, fetch)))
    if hasattr(source, "search"):
        if author:
            steps.append(("title+author", [title, author], lambda fetch: source.search(title, author, fetch)))
        steps.append(("title", [title], lambda fetch: source.search(title, None, fetch)))
        short_title = _short_title(title)
        if short_title:
            steps.append(("short-title", [short_title], lambda fetch: source.search(short_title, None, fetch)))
    return steps


def _cache_path(cache_dir, name, step, values):
    key = json.dumps([name, step, values], ensure_ascii=False)
    return Path(cache_dir) / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")


def _write_cache(path, found):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
    os.replace(partial, path)


def _failure_status(failure):
    if isinstance(failure, RateLimited):
        return "rate_limited"
    return "unavailable" if isinstance(failure, Unavailable) else "error"


def find_candidates(
    title, language, *, author=None, isbn=None, fetch, run_yaz, max_per_source=10, cache_dir=None, skip=()
):
    isbn = normalize_isbn(isbn) if isbn else None
    queries, candidates = [], []
    for source in SOURCES.get((language or "").strip().lower(), []):
        name = source.__name__.rsplit(".", 1)[-1]
        if name in skip:
            queries.append({"source": name, "step": "skipped", "status": "unavailable", "count": 0})
            continue
        for step, values, run in _steps(source, title, author, isbn)[:MAX_REQUESTS_PER_SOURCE]:
            path = _cache_path(cache_dir, name, step, values) if cache_dir is not None else None
            try:
                if path is not None and path.exists():
                    found = json.loads(path.read_text(encoding="utf-8"))
                else:
                    found = run(run_yaz if source is nkcr else fetch)
                    if path is not None:
                        _write_cache(path, found)
            except Exception as failure:  # a failing source must never stop the run
                status = _failure_status(failure)
                queries.append({"source": name, "step": step, "status": status, "count": 0})
                break  # asking the same source again would not help
            found = _unique(found)[:max_per_source]
            status = "ok" if found else "no_match"
            queries.append({"source": name, "step": step, "status": status, "count": len(found)})
            candidates.extend(found)
            if found:
                break
    return {"queries": queries, "candidates": candidates}
