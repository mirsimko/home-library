"""The locations page: list, add, and rename in place with HTMX."""
from fastapi import APIRouter, Depends, Request

from home_library import store
from home_library.web.api import call
from home_library.web.render import form_data, render

router = APIRouter()


def listing(request, status=200, error=None):
    """The whole list as the fragment HTMX swaps in after an add."""
    return render(request, "locations_list.html", status=status, error=error,
                  locations=call(request, store.locations_with_counts))


def row(request, id, template="location_row.html", status=200, error=None, name=None):
    found = next((location for location in call(request, store.locations_with_counts) if location["id"] == id), None)
    if found is None:
        raise store.NotFound(f"locations: {id} was not found")
    if name is not None:
        found = {**found, "name": name}
    return render(request, template, status=status, error=error, location=found)


@router.get("/locations")
def locations(request: Request):
    return render(request, "locations.html", active="locations", error=None,
                  locations=call(request, store.locations_with_counts))


@router.post("/locations")
def add_location(request: Request, form=Depends(form_data)):
    try:
        call(request, store.add_location, form.get("name"), form.get("kind"))
    except store.Invalid as error:
        return listing(request, 400, str(error))
    return listing(request)


@router.get("/locations/{id}/row")
def location_row(request: Request, id: int):
    return row(request, id)


@router.get("/locations/{id}/edit")
def edit_location(request: Request, id: int):
    return row(request, id, "location_edit.html")


@router.post("/locations/{id}/rename")
def rename_location(request: Request, id: int, form=Depends(form_data)):
    try:
        call(request, store.rename_location, id, form.get("name"))
    except store.Invalid as error:
        return row(request, id, "location_edit.html", 400, str(error), form.get("name"))
    return row(request, id)
