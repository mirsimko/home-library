"""Stage 5, look-up: candidate catalogue records for a title (docs/pipeline.md)."""
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
        steps.append(("isbn", lambda fetch: source.by_isbn(isbn, fetch)))
    if hasattr(source, "search"):
        if author:
            steps.append(("title+author", lambda fetch: source.search(title, author, fetch)))
        steps.append(("title", lambda fetch: source.search(title, None, fetch)))
        short_title = _short_title(title)
        if short_title:
            steps.append(("short-title", lambda fetch: source.search(short_title, None, fetch)))
    return steps


def find_candidates(title, language, *, author=None, isbn=None, fetch, run_yaz, max_per_source=10):
    isbn = normalize_isbn(isbn) if isbn else None
    queries, candidates = [], []
    for source in SOURCES.get(language, []):
        name = source.__name__.rsplit(".", 1)[-1]
        for step, run in _steps(source, title, author, isbn)[:MAX_REQUESTS_PER_SOURCE]:
            try:
                found = run(run_yaz if source is nkcr else fetch)
            except (RateLimited, Unavailable) as failure:
                status = "rate_limited" if isinstance(failure, RateLimited) else "unavailable"
                queries.append({"source": name, "step": step, "status": status, "count": 0})
                break  # asking the same source again would not help
            except Exception:  # a failing source must never stop the run
                queries.append({"source": name, "step": step, "status": "error", "count": 0})
                continue
            found = _unique(found)[:max_per_source]
            status = "ok" if found else "no_match"
            queries.append({"source": name, "step": step, "status": status, "count": len(found)})
            candidates.extend(found)
            if found:
                break
    return {"queries": queries, "candidates": candidates}
