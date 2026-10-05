"""Turn a MARC 21 record into a candidate. Used by the loc and nkcr sources.

A record is a dict: {"control": {"001": "...", "008": "..."}, "fields": [(tag, ind1, ind2, [(code, value), ...])]}.
"""
import re

from home_library.lookup.candidate import new_candidate
from home_library.lookup.isbn import normalize_isbn

LANGUAGES = {"cze": "cs", "eng": "en", "jpn": "ja", "chi": "zh"}
AUDIENCES = {
    "a": "preschool", "b": "primary", "c": "pre-adolescent", "d": "adolescent",
    "e": "adult", "f": "specialized", "g": "general", "j": "juvenile",
}
ROLES = {"aut": "author", "ill": "illustrator", "trl": "translator", "edt": "editor"}


def _clean(text, dots=False):
    """Drop the ISBD punctuation that ends a MARC subfield. A final full stop goes only when dots is true."""
    return text.strip().rstrip(" ,/:;." if dots else " ,/:;").strip()


def _fields(record, tag):
    return [f for f in record["fields"] if f[0] == tag]


def _subfields(field, *codes):
    return [value for code, value in field[3] if code in codes]


def _first(record, tag, *codes):
    for field in _fields(record, tag):
        values = _subfields(field, *codes)
        if values:
            return _clean(" ".join(values))
    return ""


def _name(field):
    return _clean(" ".join(_subfields(field, "a", "d")), dots=True)


def _roles(field):
    roles = [ROLES.get(code, code) for code in _subfields(field, "4")]
    for word in _subfields(field, "e"):
        word = _clean(word, dots=True).lower()
        roles.append(word)
    unique = []
    for role in roles:
        if role not in unique:
            unique.append(role)
    return unique


def _authors(record):
    authors = []
    for field in _fields(record, "100") + _fields(record, "700"):
        if _subfields(field, "t"):  # an author-title added entry: a work, not an author of this book
            continue
        name = _name(field)
        roles = _roles(field)
        if name and roles and roles != ["author"]:
            name += " (%s)" % ", ".join(roles)
        if name:
            authors.append(name)
    return authors


def _subjects(record):
    subjects = []
    for field in _fields(record, "650") + _fields(record, "655"):
        parts = [_clean(v, dots=True) for v in _subfields(field, "a", "v", "x", "y", "z")]
        subject = " -- ".join(p for p in parts if p)
        if subject and subject not in subjects:
            subjects.append(subject)
    return subjects


def _publication(record):
    for field in _fields(record, "264"):
        if field[2] == "1":
            return field
    for tag in ("260", "264"):
        fields = _fields(record, tag)
        if fields:
            return fields[0]
    return None


def _isbn(record):
    for field in _fields(record, "020"):
        for value in _subfields(field, "a"):
            isbn = normalize_isbn(value.split()[0]) if value.split() else None
            if isbn:
                return isbn
    return ""


def candidate_from_marc(source, record, url=""):
    control = record["control"]
    f008 = control.get("008", "").ljust(40)
    publication = _publication(record)
    year = re.search(r"\d{4}", " ".join(_subfields(publication, "c"))) if publication else None
    return new_candidate(
        source,
        control.get("001", ""),
        url=url,
        title=_clean(" ".join(_subfields(_fields(record, "245")[0], "a", "b"))) if _fields(record, "245") else "",
        authors=_authors(record),
        publisher=_clean(" ".join(_subfields(publication, "b"))) if publication else "",
        year=year.group(0) if year else "",
        isbn=_isbn(record),
        series=_first(record, "490", "a"),
        language=LANGUAGES.get(f008[35:38], f008[35:38].strip()),
        audience=AUDIENCES.get(f008[22], ""),
        age_note=_first(record, "521", "a"),
        subjects=_subjects(record),
        summary=" ".join(v.strip() for f in _fields(record, "520") for v in _subfields(f, "a")),
    )
