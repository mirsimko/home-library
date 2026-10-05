"""Stage 4: compare two reads of the same photo."""
import difflib
import unicodedata


def match_key(title: str) -> str:
    folded = unicodedata.normalize("NFKC", title).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def _exact(title_a: str, title_b: str) -> bool:
    return unicodedata.normalize("NFC", title_a).strip() == unicodedata.normalize("NFC", title_b).strip()


def _reading(read_id: str, entry: dict) -> dict:
    return {"read_id": read_id, **entry}


def _solo(read_id: str, entry: dict) -> dict:
    return {"status": "review", "reason": "solo", "title": entry["title"], "language": entry["language"],
            "exact": False, "readings": [_reading(read_id, entry)]}


def _pair_equal_keys(keys_a: dict, keys_b: dict) -> dict:
    pairs = {}
    taken = set()
    for i, key in keys_a.items():
        for j, other in keys_b.items():
            if j not in taken and other == key:
                pairs[i] = j
                taken.add(j)
                break
    return pairs


def _pair_similar(keys_a: dict, keys_b: dict) -> dict:
    candidates = []
    for i, key in keys_a.items():
        for j, other in keys_b.items():
            ratio = difflib.SequenceMatcher(None, key, other).ratio()
            if ratio >= 0.9:
                candidates.append((-ratio, i, j))
    pairs, used_b = {}, set()
    for _, i, j in sorted(candidates):
        if i not in pairs and j not in used_b:
            pairs[i] = j
            used_b.add(j)
    return pairs


def merge_reads(read_a: dict, read_b: dict) -> dict:
    id_a, id_b = read_a["read_id"], read_b["read_id"]
    books_a, books_b = read_a["books"], read_b["books"]
    keys_a = {i: match_key(e["title"]) for i, e in enumerate(books_a)}
    keys_b = {j: match_key(e["title"]) for j, e in enumerate(books_b)}
    pairs = _pair_equal_keys(keys_a, keys_b)
    left_a = {i: k for i, k in keys_a.items() if i not in pairs}
    left_b = {j: k for j, k in keys_b.items() if j not in pairs.values()}
    near = _pair_similar(left_a, left_b)
    items = []
    for i, entry in enumerate(books_a):
        if i in pairs:
            other = books_b[pairs[i]]
            items.append({
                "status": "accepted", "reason": "agreed", "title": entry["title"],
                "language": entry["language"], "exact": _exact(entry["title"], other["title"]),
                "readings": [_reading(id_a, entry), _reading(id_b, other)],
            })
        elif i in near:
            other = books_b[near[i]]
            items.append({
                "status": "review", "reason": "near", "title": entry["title"],
                "language": entry["language"], "exact": False,
                "readings": [_reading(id_a, entry), _reading(id_b, other)],
            })
        else:
            items.append(_solo(id_a, entry))
    paired_b = set(pairs.values()) | set(near.values())
    for j, entry in enumerate(books_b):
        if j not in paired_b:
            items.append(_solo(id_b, entry))
    return {"file": read_a["file"], "reads": [id_a, id_b], "items": items,
            "unreadable": [], "parse_errors": []}
