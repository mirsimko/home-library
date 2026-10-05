"""Stage 3: turn a raw answer into a read, entry by entry."""
import json
import re

_DECODER = json.JSONDecoder()
_OUTER_OBJECT = re.compile(r'\{\s*"')
_FIELDS = ["n", "where", "visible", "title", "other_text", "language", "readable", "confidence", "inferred"]
_WHITESPACE = " \t\r\n"


def _decode(raw: str, start: int):
    """Decode one JSON value at `start`. Returns (value, end, None) or (None, start, reason)."""
    try:
        value, end = _DECODER.raw_decode(raw, start)
        return value, end, None
    except (ValueError, RecursionError) as exc:
        return None, start, getattr(exc, "msg", None) or str(exc) or type(exc).__name__


def _skip_space(raw: str, pos: int) -> int:
    while pos < len(raw) and raw[pos] in _WHITESPACE:
        pos += 1
    return pos


def _skip_value(raw: str, pos: int, stops: str) -> int:
    """End of the value at `pos`, found by tracking strings, escapes and nesting.

    Stops at a depth-0 character in `stops`. A raw newline inside a string ends the value there, because JSON
    forbids one inside a string; that keeps one missing quote from swallowing the lines below it.
    """
    depth = 0
    in_string = False
    while pos < len(raw):
        ch = raw[pos]
        if in_string:
            if ch == "\\":
                pos += 1
            elif ch == '"':
                in_string = False
            elif ch == "\n":
                return pos
        elif ch == '"':
            in_string = True
        elif depth == 0 and ch in stops:
            return pos
        elif ch in "{[":
            depth += 1
        elif ch in "}]" and depth > 0:
            depth -= 1
        pos += 1
    return len(raw)


def _text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _normalise(entry: dict, position: int) -> dict:
    book = {name: _text(entry.get(name)) for name in _FIELDS}
    if book["readable"] not in ("yes", "partial", "no"):
        book["readable"] = "partial"
    n = entry.get("n")
    book["n"] = n if isinstance(n, int) and not isinstance(n, bool) else position
    return book


def _scan_entries(raw: str, pos: int):
    """Entries of the list whose '[' just ended at `pos`. Returns (books, errors, end, closed)."""
    books, errors = [], []
    position = 0
    after_comma = False
    while True:
        pos = _skip_space(raw, pos)
        if pos >= len(raw):
            return books, errors, pos, False
        if raw[pos] == "]" and not after_comma:
            return books, errors, pos + 1, True
        position += 1
        if raw[pos] in ",]":  # no entry between the delimiters: one was lost
            errors.append({"position": position, "offset": pos, "reason": "Empty entry", "raw": ""})
            if raw[pos] == "]":
                return books, errors, pos + 1, True
            pos += 1
            after_comma = True
            continue
        end = _skip_value(raw, pos, ",]")
        span = raw[pos:end].rstrip(_WHITESPACE + ",")
        value, used, reason = _decode(span, 0)
        if reason is None and used < len(span):
            reason = "Extra data"
        if reason is None and not isinstance(value, dict):
            reason = "Entry is not an object"
        if reason is None:
            try:
                books.append(_normalise(value, position))
            except Exception as exc:  # e.g. RecursionError from json.dumps on a deeply nested title
                reason = str(exc) or type(exc).__name__
        if reason is not None:
            errors.append({"position": position, "offset": pos, "reason": reason, "raw": span})
        pos = _skip_space(raw, end)
        after_comma = raw[pos:pos + 1] == ","
        pos += after_comma


def _no_books(raw: str, file_name: str) -> dict:
    error = {"position": 0, "offset": 0, "reason": 'No "books" list found', "raw": raw}
    return {"file": file_name, "books": [], "errors": [error], "complete": False}


def parse_read(raw: str) -> dict:
    """Read the outer object member by member; decode `books` entry by entry. Never raises, never repairs."""
    start = _OUTER_OBJECT.search(raw)
    if start is None:
        return _no_books(raw, "")
    pos = start.start() + 1
    file_name, books, errors = "", None, []
    closed, complete = False, True
    while True:
        pos = _skip_space(raw, pos)
        while pos < len(raw) and raw[pos] == ",":
            pos = _skip_space(raw, pos + 1)
        if pos >= len(raw):
            complete = False
            break
        if raw[pos] == "}":
            closed = True
            break
        key, pos, reason = _decode(raw, pos)
        pos = _skip_space(raw, pos)
        if reason is not None or not isinstance(key, str) or raw[pos:pos + 1] != ":":
            complete = False
            break
        pos = _skip_space(raw, pos + 1)
        if key == "books" and books is None and raw[pos:pos + 1] == "[":
            books, errors, pos, list_closed = _scan_entries(raw, pos + 1)
            complete = complete and list_closed
            continue
        end = _skip_value(raw, pos, ",}")
        if key == "file":
            value, _, reason = _decode(raw[pos:end].rstrip(_WHITESPACE), 0)
            if reason is None and isinstance(value, str):
                file_name = value
            else:
                complete = False
        pos = end
    if books is None:
        return _no_books(raw, file_name)
    return {"file": file_name, "books": books, "errors": errors, "complete": complete and closed and not errors}
