"""Stage 3: turn a raw answer into a read, entry by entry."""
import json


def _whole_object(raw: str):
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except ValueError:
        return None


def parse_read(raw: str) -> dict:
    data = _whole_object(raw)
    return {"file": data["file"], "books": data["books"], "errors": [], "complete": True}
