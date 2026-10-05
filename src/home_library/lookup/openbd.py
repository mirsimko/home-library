"""openBD: ISBN look-up for Japanese books. There is no search endpoint."""
import json
from urllib.parse import urlencode

from home_library.lookup.candidate import new_candidate

BASE = "https://api.openbd.jp/v1/get"


def _get(record, *path):
    for key in path:
        if isinstance(record, list):
            record = record[0] if record else None
        if not isinstance(record, dict):
            return ""
        record = record.get(key)
    return record or ""


def _candidate(record):
    summary = record.get("summary") or {}
    onix = record.get("onix") or {}
    isbn = summary.get("isbn", "")
    return new_candidate(
        "openbd",
        isbn,
        url=BASE + "?" + urlencode({"isbn": isbn}),
        title=summary.get("title", ""),
        title_reading=_get(onix, "DescriptiveDetail", "TitleDetail", "TitleElement", "TitleText", "collationkey"),
        authors=summary.get("author", "").split(),
        publisher=summary.get("publisher", ""),
        year=summary.get("pubdate", "")[:4],
        isbn=isbn,
        series=summary.get("series", ""),
        language="ja",
        summary=_get(onix, "CollateralDetail", "TextContent", "Text"),
    )


def by_isbn(isbn, fetch):
    records = json.loads(fetch(BASE + "?" + urlencode({"isbn": isbn})))
    return [_candidate(r) for r in records if r]
