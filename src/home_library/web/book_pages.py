"""The books pages: live search, filters, and moving or changing the state of several books at once."""
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Request

from home_library import store
from home_library.web.api import call
from home_library.web.render import form_data, redirect, render

router = APIRouter()

PAGE = 100


def count_of(name, number):
    return f"{number} {name}{'' if number == 1 else 's'}"


def search_values(values, prefix=""):
    """The search a person asked for as plain strings; blank means no filter."""
    return {key: (values.get(prefix + key) or "").strip() for key in ("q", "state", "location_id", "tag")}


def search_books(request, values, offset=0):
    """One page of results, with whether more follow; a bad filter is reported as a store.Invalid."""
    location = values["location_id"]
    if location and not location.isdecimal():
        raise store.Invalid("location must be one of the listed locations")
    found = call(request, store.search_books, values["q"], values["state"] or None,
                 int(location) if location else None, values["tag"] or None, PAGE + 1, offset)
    return found[:PAGE], len(found) > PAGE


def results(request, values, offset=0, template="books_results.html", status=200, message=None, error=None, **extra):
    """Render results for a search, or the reason it could not run."""
    books, more = [], False
    try:
        books, more = search_books(request, values, offset)
    except store.Invalid as problem:
        status, error = 400, str(problem)
    more_url = "/books/rows?" + urlencode({"offset": offset + PAGE, **{k: v for k, v in values.items() if v}})
    names = {row["id"]: row["name"] for row in call(request, store.locations)}
    return render(request, template, status=status, books=books, more_url=more_url if more else None,
                  values=values, locations=call(request, store.locations), names=names, states=store.STATES,
                  message=message, error=error, **extra)


@router.get("/books")
def books(request: Request):
    values = search_values(request.query_params)
    return results(request, values, template="books.html", active="books")


@router.get("/books/results")
def books_results(request: Request):
    return results(request, search_values(request.query_params))


@router.get("/books/rows")
def books_rows(request: Request, offset: int = 0):
    return results(request, search_values(request.query_params), offset, "books_rows.html")


@router.post("/books/move")
def move_books(request: Request, form=Depends(form_data)):
    values = search_values(form, "filter_")
    location, state = (form.get("location_id") or "").strip(), (form.get("state") or "").strip()
    try:
        if not all(id.isdecimal() for id in form.getlist("book_ids")):
            raise store.Invalid("book ids must be numbers")
        if location and not location.isdecimal():
            raise store.Invalid("choose a location from the list")
        moved = call(request, store.move_books, [int(id) for id in form.getlist("book_ids")],
                     int(location) if location else None, state or None, by=request.state.user)
    except store.Invalid as problem:
        return results(request, values, status=400, error=str(problem))
    except store.NotFound as problem:
        return results(request, values, status=404, error=str(problem))
    words = []
    if location:
        place = next(row["name"] for row in call(request, store.locations) if row["id"] == int(location))
        words.append(f"Moved {count_of('book', len(moved))} to {place}")
    if state:
        words.append(f"changed {'them' if location else count_of('book', len(moved))} to {state}")
    return results(request, values, message=" and ".join(words) if location else words[0][:1].upper() + words[0][1:])


# ---- adding and editing one book ----------------------------------------------------------------------

FIELDS = (*store.TEXT_FIELDS, "age_from", "age_to", "state", "location_id", "needs_review")
LABELS = {"title": "Title", "sort_key": "Sort as", "author": "Author", "illustrator": "Illustrator",
          "publisher": "Publisher", "year": "Year", "language": "Language", "isbn": "ISBN", "series": "Series",
          "tags": "Tags", "source": "Catalogue source", "source_id": "Catalogue id", "notes": "Notes",
          "age_from": "Age from", "age_to": "Age to", "state": "State", "location_id": "Location",
          "needs_review": "Needs review"}


def display(book):
    """A book's editable fields as the strings a form holds; the checkbox is 1 or 0."""
    return {key: "" if book[key] is None else ("1" if book[key] else "0") if isinstance(book[key], bool)
            else str(book[key]) for key in FIELDS}


def convert(key, text):
    """One posted value as the store expects it; the store itself checks the rest."""
    if key == "location_id":
        if not text.isdecimal():
            raise store.Invalid("choose a location")
        return int(text)
    if key == "needs_review":
        return text == "1"
    return text


def posted_fields(form):
    """Every book field the form carries, as the store expects it."""
    return {key: convert(key, form[key]) for key in FIELDS if key in form}


def posted_changes(form):
    """Only the fields that differ from what the person first saw, so a save never rewrites other people's work."""
    return {key: value for key, value in posted_fields(form).items()
            if f"was_{key}" not in form or form[f"was_{key}"] != form[key]}


def safe_next(url):
    """Where to go after adding a book; only a plain path on this site.

    A browser reads `/\\host` like `//host`, and drops tabs and newlines inside a URL, so a path that holds a
    backslash or a control character, or that `urlsplit` gives a host, is not followed.
    """
    if not url or not url.startswith("/") or url.startswith("//") or "\\" in url:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        return None
    parts = urlsplit(url)
    return url if not parts.netloc and not parts.scheme else None


def book_form(request, book, values, was, error=None, status=200, notice=None, next=None):
    return render(request, "book_form.html", status=status, active="books", book=book, v=values, was=was,
                  error=error, notice=notice, next=next, locations=call(request, store.locations),
                  states=store.STATES, fields=FIELDS)


@router.get("/books/new")
def new_book(request: Request, location_id: str = "", next: str = ""):
    values = dict.fromkeys(FIELDS, "") | {"state": "Active", "needs_review": "0", "location_id": location_id}
    return book_form(request, None, values, values, next=safe_next(next))


@router.post("/books")
def add_book(request: Request, form=Depends(form_data)):
    values = {key: form.get(key, "") for key in FIELDS}
    try:
        book = call(request, store.add_book, posted_fields(form), request.state.user)
    except store.Invalid as problem:
        return book_form(request, None, values, values, str(problem), 400, next=safe_next(form.get("next")))
    return redirect(request, safe_next(form.get("next")) or f"/books/{book['id']}")


@router.get("/books/{id}")
def book_page(request: Request, id: int, saved: str = ""):
    book = call(request, store.book, id)
    return book_form(request, book, display(book), display(book), notice="Saved." if saved else None)


def conflict_page(request, id, mine):
    """Both versions of what this person changed, beside each other, with a way to apply it to the stored book."""
    stored = call(request, store.book, id)
    rows = [{"key": key, "label": LABELS[key], "stored": display(stored)[key], "mine": display({**stored, key: value})[key]}
            for key, value in mine.items()]
    return render(request, "book_conflict.html", status=409, active="books", book=stored, rows=rows)


@router.post("/books/{id}")
def save_book(request: Request, id: int, form=Depends(form_data)):
    current = call(request, store.book, id)
    version = form.get("version", "")
    changes = posted_changes(form)
    try:
        if not version.isdecimal():
            raise store.Invalid("version must be a number")
        if changes:
            call(request, store.update_book, id, int(version), changes, request.state.user)
    except store.Conflict:
        return conflict_page(request, id, changes)
    except store.Invalid as problem:
        values = {key: form.get(key, display(current)[key]) for key in FIELDS}
        was = {key: form.get(f"was_{key}", display(current)[key]) for key in FIELDS}
        return book_form(request, {**current, "version": version}, values, was, str(problem), 400)
    return redirect(request, f"/books/{id}?saved=1" if changes else f"/books/{id}")


@router.post("/books/{id}/reapply")
def reapply(request: Request, id: int, form=Depends(form_data)):
    changes = posted_fields(form)
    try:
        if not form.get("version", "").isdecimal():
            raise store.Invalid("version must be a number")
        call(request, store.update_book, id, int(form["version"]), changes, request.state.user)
    except store.Conflict:
        return conflict_page(request, id, changes)
    return redirect(request, f"/books/{id}?saved=1")
