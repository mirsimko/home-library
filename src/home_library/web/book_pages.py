"""The books pages: live search, filters, and moving or changing the state of several books at once."""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from home_library import store
from home_library.web.api import call
from home_library.web.render import form_data, render

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
        moved = call(request, store.move_books, [int(id) for id in form.getlist("book_ids")],
                     int(location) if location.isdecimal() else None, state or None, by=request.state.user)
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
    return results(request, values, message=" and ".join(words) if location else words[0].capitalize())
