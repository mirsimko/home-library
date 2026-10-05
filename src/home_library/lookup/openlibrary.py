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


def _from_work(doc):
    key = doc.get("key", "").rsplit("/", 1)[-1]
    return new_candidate(
        "openlibrary",
        key,
        url="https://openlibrary.org/works/" + key,
        title=doc.get("title", ""),
        authors=doc.get("author_name", []),
        year=str(doc.get("first_publish_year", "")),
        subjects=doc.get("subject", [])[:MAX_SUBJECTS],
    )


def search(title, author, fetch):
    params = {"title": title}
    if author:
        params["author"] = author
    params["limit"] = 10
    params["fields"] = "key,title,author_name,first_publish_year,subject"
    answer = json.loads(fetch("https://openlibrary.org/search.json?" + urlencode(params)))
    return [_from_work(doc) for doc in answer.get("docs", [])]
