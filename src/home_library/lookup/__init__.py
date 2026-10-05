"""Stage 5, look-up: candidate catalogue records for a title (docs/pipeline.md)."""
from home_library.lookup import ndl, openbd
from home_library.lookup.isbn import normalize_isbn

SOURCES = {"ja": [ndl, openbd]}


def _steps(source, title, isbn):
    steps = []
    if isbn:
        steps.append(("isbn", lambda fetch: source.by_isbn(isbn, fetch)))
    if hasattr(source, "search"):
        steps.append(("title", lambda fetch: source.search(title, None, fetch)))
    return steps


def find_candidates(title, language, *, author=None, isbn=None, fetch, run_yaz, max_per_source=10):
    isbn = normalize_isbn(isbn) if isbn else None
    queries, candidates = [], []
    for source in SOURCES.get(language, []):
        name = source.__name__.rsplit(".", 1)[-1]
        for step, run in _steps(source, title, isbn):
            found = run(fetch)
            queries.append({"source": name, "step": step, "status": "ok", "count": len(found)})
            candidates.extend(found)
            if found:
                break
    return {"queries": queries, "candidates": candidates}
