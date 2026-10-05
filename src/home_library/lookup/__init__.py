"""Stage 5, look-up: candidate catalogue records for a title (docs/pipeline.md)."""
from home_library.lookup import ndl, openbd
from home_library.lookup.isbn import normalize_isbn

SOURCES = {"ja": [ndl, openbd]}


def _steps(source, title, author, isbn):
    steps = []
    if isbn:
        steps.append(("isbn", lambda fetch: source.by_isbn(isbn, fetch)))
    if hasattr(source, "search"):
        if author:
            steps.append(("title+author", lambda fetch: source.search(title, author, fetch)))
        steps.append(("title", lambda fetch: source.search(title, None, fetch)))
    return steps


def find_candidates(title, language, *, author=None, isbn=None, fetch, run_yaz, max_per_source=10):
    isbn = normalize_isbn(isbn) if isbn else None
    queries, candidates = [], []
    for source in SOURCES.get(language, []):
        name = source.__name__.rsplit(".", 1)[-1]
        for step, run in _steps(source, title, author, isbn):
            found = run(fetch)
            status = "ok" if found else "no_match"
            queries.append({"source": name, "step": step, "status": status, "count": len(found)})
            candidates.extend(found)
            if found:
                break
    return {"queries": queries, "candidates": candidates}
