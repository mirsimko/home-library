"""The candidate shape of docs/pipeline.md, Stage 5."""

FIELD_ORDER = (
    "url", "title", "title_reading", "authors", "publisher", "year", "isbn",
    "series", "language", "audience", "age_note", "subjects", "summary",
)
LIST_FIELDS = ("authors", "subjects")


def _text(value):
    return "" if value is None else str(value)


def _strings(value):
    return [member for member in value if isinstance(member, str)] if isinstance(value, (list, tuple)) else []


def new_candidate(source, source_id, **fields):
    """A candidate with every field present. Text fields are str and the list fields lists of str:
    a field not given, or None, is empty; a list loses its members that are not str."""
    unknown = set(fields) - set(FIELD_ORDER)
    if unknown:
        raise TypeError("unknown candidate fields: %s" % sorted(unknown))
    source_id = _text(source_id)
    candidate = {"id": "%s:%s" % (source, source_id), "source": source, "source_id": source_id}
    for name in FIELD_ORDER:
        candidate[name] = _strings(fields.get(name)) if name in LIST_FIELDS else _text(fields.get(name))
    return candidate
