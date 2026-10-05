"""Stage 3: turn a raw answer into a read, entry by entry."""
import json
import re

_DECODER = json.JSONDecoder()
_BOOKS = re.compile(r'"books"\s*:\s*\[')
_FILE = re.compile(r'"file"\s*:\s*("(?:[^"\\]|\\.)*")')


def _whole_object(raw: str):
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except ValueError:
        return None


def _file_name(raw: str) -> str:
    found = _FILE.search(raw)
    return json.loads(found.group(1)) if found else ""


def _next_decodable_object(raw: str, after: int) -> int:
    """Offset of the next '{' after `after` that starts an object that decodes, or -1."""
    pos = raw.find("{", after)
    while pos >= 0:
        try:
            _DECODER.raw_decode(raw, pos)
            return pos
        except ValueError:
            pos = raw.find("{", pos + 1)
    return -1


def _scan_entries(raw: str, start: int):
    books, errors = [], []
    pos = start
    position = 0
    closed = False
    while True:
        while pos < len(raw) and raw[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(raw):
            break
        if raw[pos] == "]":
            closed = True
            break
        position += 1
        try:
            value, end = _DECODER.raw_decode(raw, pos)
            books.append(value)
            pos = end
        except ValueError as exc:
            nxt = _next_decodable_object(raw, pos + 1)
            end = nxt if nxt >= 0 else len(raw)
            errors.append({"position": position, "offset": pos, "reason": exc.msg,
                           "raw": raw[pos:end].rstrip(" \t\r\n,")})
            pos = end
    return books, errors, closed


def parse_read(raw: str) -> dict:
    found = _BOOKS.search(raw)
    books, errors, closed = _scan_entries(raw, found.end())
    return {"file": _file_name(raw), "books": books, "errors": errors, "complete": closed and not errors}
