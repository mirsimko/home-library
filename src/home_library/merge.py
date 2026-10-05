"""Stage 4: compare two reads of the same photo."""
import difflib
import unicodedata


_SIGNS = str.maketrans("", "", "™®©℠")  # NFKC would turn ™ into the letters TM


def match_key(title: str) -> str:
    folded = unicodedata.normalize("NFKC", title.translate(_SIGNS)).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def _exact(title_a: str, title_b: str) -> bool:
    return unicodedata.normalize("NFC", title_a).strip() == unicodedata.normalize("NFC", title_b).strip()


def _reading(read_id: str, entry: dict) -> dict:
    return {"read_id": read_id, **entry}


def _eligible(entry: dict) -> bool:
    return entry["readable"] == "yes" and match_key(entry["title"]) != "" and entry["inferred"] == ""


def _item(status: str, reason: str, entry: dict, readings: list, exact: bool) -> dict:
    return {"status": status, "reason": reason, "title": entry["title"], "language": entry["language"],
            "exact": exact, "readings": readings}


def _solo(read_id: str, entry: dict) -> dict:
    return _item("review", "solo" if _eligible(entry) else "partial", entry, [_reading(read_id, entry)], False)


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


def _words_found(entry: dict, other: dict) -> bool:
    words = [key for key in map(match_key, entry["title"].split()) if key]
    everything = match_key(other["title"] + " " + other["other_text"])
    return bool(words) and all(word in everything for word in words)


def _pair_same_words(books_a: dict, books_b: dict) -> dict:
    """Pairs that hold the same words but divide them differently between title and other_text."""
    pairs, used_b = {}, set()
    for i, entry in books_a.items():
        for j, other in books_b.items():
            if j not in used_b and _words_found(entry, other) and _words_found(other, entry):
                pairs[i] = j
                used_b.add(j)
                break
    return pairs


def merge_reads(read_a: dict, read_b: dict) -> dict:
    id_a, id_b = read_a["read_id"], read_b["read_id"]
    if id_a == id_b:
        raise ValueError(f"cannot merge read {id_a!r} with itself: one read agreeing with itself is not two reads")
    file_a, file_b = read_a["file"], read_b["file"]
    if file_a and file_b and file_a != file_b:
        raise ValueError(f"reads are of different photos: {file_a!r} and {file_b!r}")
    unreadable = []
    titled = []
    for read_id, read in ((id_a, read_a), (id_b, read_b)):
        titled_books = []
        for entry in read["books"]:
            if entry["title"].strip() == "":
                unreadable.append(_reading(read_id, entry))
            else:
                titled_books.append(entry)
        titled.append(titled_books)
    books_a, books_b = titled
    keys_a = {i: match_key(e["title"]) for i, e in enumerate(books_a)}
    keys_b = {j: match_key(e["title"]) for j, e in enumerate(books_b)}
    pairs = _pair_equal_keys({i: k for i, k in keys_a.items() if _eligible(books_a[i])},
                             {j: k for j, k in keys_b.items() if _eligible(books_b[j])})
    left_a = {i: k for i, k in keys_a.items() if i not in pairs and k}
    left_b = {j: k for j, k in keys_b.items() if j not in pairs.values() and k}
    near = _pair_similar(left_a, left_b)
    split = _pair_same_words({i: books_a[i] for i in left_a if i not in near},
                             {j: books_b[j] for j in left_b if j not in near.values()})
    items = []
    for i, entry in enumerate(books_a):
        if i in pairs:
            other = books_b[pairs[i]]
            items.append(_item("accepted", "agreed", entry, [_reading(id_a, entry), _reading(id_b, other)],
                               _exact(entry["title"], other["title"])))
        elif i in near:
            other = books_b[near[i]]
            reason = "near" if _eligible(entry) and _eligible(other) else "partial"
            items.append(_item("review", reason, entry, [_reading(id_a, entry), _reading(id_b, other)],
                               _exact(entry["title"], other["title"])))
        elif i in split:
            other = books_b[split[i]]
            reason = "split" if _eligible(entry) and _eligible(other) else "partial"
            items.append(_item("review", reason, entry, [_reading(id_a, entry), _reading(id_b, other)], False))
        else:
            items.append(_solo(id_a, entry))
    paired_b = set(pairs.values()) | set(near.values()) | set(split.values())
    for j, entry in enumerate(books_b):
        if j not in paired_b:
            items.append(_solo(id_b, entry))
    parse_errors = [{"read_id": read_id, **error}
                    for read_id, read in ((id_a, read_a), (id_b, read_b)) for error in read["errors"]]
    return {"file": file_a or file_b, "reads": [id_a, id_b], "items": items,
            "unreadable": unreadable, "parse_errors": parse_errors}
