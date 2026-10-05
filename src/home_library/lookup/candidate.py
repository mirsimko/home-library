"""The candidate shape of docs/pipeline.md, Stage 5."""

FIELD_ORDER = (
    "url", "title", "title_reading", "authors", "publisher", "year", "isbn",
    "series", "language", "audience", "age_note", "subjects", "summary",
)
LIST_FIELDS = ("authors", "subjects")


def new_candidate(source, source_id, **fields):
    """A candidate with every field present; fields not given are empty."""
    unknown = set(fields) - set(FIELD_ORDER)
    if unknown:
        raise TypeError("unknown candidate fields: %s" % sorted(unknown))
    candidate = {"id": "%s:%s" % (source, source_id), "source": source, "source_id": source_id}
    for name in FIELD_ORDER:
        candidate[name] = fields.get(name, [] if name in LIST_FIELDS else "")
    return candidate
