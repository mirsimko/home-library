"""Stage 3: turn a raw model answer into a read, entry by entry."""
import json


def parse_read(raw: str) -> dict:
    data = json.loads(raw)
    return {"file": data["file"], "books": data["books"], "errors": [], "complete": True}
