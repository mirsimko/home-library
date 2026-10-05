"""Stage 5, look-up: candidate catalogue records for a title (docs/pipeline.md)."""
from home_library.lookup import ndl

SOURCES = {"ja": [ndl]}


def find_candidates(title, language, *, author=None, isbn=None, fetch, run_yaz, max_per_source=10):
    queries, candidates = [], []
    for source in SOURCES.get(language, []):
        found = source.search(title, None, fetch)
        queries.append({"source": "ndl", "step": "title", "status": "ok", "count": len(found)})
        candidates.extend(found)
    return {"queries": queries, "candidates": candidates}
