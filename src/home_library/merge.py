"""Stage 4: compare two reads of the same photo."""
import unicodedata


def match_key(title: str) -> str:
    folded = unicodedata.normalize("NFKC", title).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def _reading(read_id: str, entry: dict) -> dict:
    return {"read_id": read_id, **entry}


def merge_reads(read_a: dict, read_b: dict) -> dict:
    entries_b = list(read_b["books"])
    items = []
    for entry in read_a["books"]:
        key = match_key(entry["title"])
        for other in entries_b:
            if match_key(other["title"]) == key:
                entries_b.remove(other)
                items.append({
                    "status": "accepted", "reason": "agreed", "title": entry["title"],
                    "language": entry["language"], "exact": True,
                    "readings": [_reading(read_a["read_id"], entry), _reading(read_b["read_id"], other)],
                })
                break
    return {"file": read_a["file"], "reads": [read_a["read_id"], read_b["read_id"]], "items": items,
            "unreadable": [], "parse_errors": []}
