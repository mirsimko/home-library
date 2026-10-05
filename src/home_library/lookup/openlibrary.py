"""Open Library: ISBN look-up (api/books) and title search (search.json)."""
import json
import re
from urllib.parse import urlencode

from home_library.lookup.candidate import new_candidate

MAX_SUBJECTS = 10


def _year(text):
    match = re.search(r"\d{4}", text or "")
    return match.group(0) if match else ""


def _from_edition(record, isbn):
    key = record.get("key", "").rsplit("/", 1)[-1]
    publishers = record.get("publishers") or []
    return new_candidate(
        "openlibrary",
        key,
        url=record.get("url", ""),
        title=record.get("title", ""),
        authors=[a.get("name", "") for a in record.get("authors", [])],
        publisher=publishers[0].get("name", "") if publishers else "",
        year=_year(record.get("publish_date")),
        isbn=isbn,
        subjects=[s.get("name", "") for s in record.get("subjects", [])][:MAX_SUBJECTS],
    )


def by_isbn(isbn, fetch):
    params = {"bibkeys": "ISBN:" + isbn, "format": "json", "jscmd": "data"}
    answer = json.loads(fetch("https://openlibrary.org/api/books?" + urlencode(params)))
    return [_from_edition(record, isbn) for record in answer.values()]
