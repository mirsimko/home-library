"""JSON routes backed by the shared catalogue store."""
from contextlib import closing

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from home_library import store
from home_library.web.uploads import incoming, publish

router = APIRouter()


@router.get("/health")
def health(request: Request):
    with closing(store.open(request.app.state.data_root)) as db:
        return store.health(db)


def call(request, function, *args, **kwargs):
    """Keep each store connection within the thread that uses it."""
    with closing(store.open(request.app.state.data_root)) as db:
        return function(db, *args, **kwargs)


@router.get("/api/locations")
def locations(request: Request):
    return call(request, store.locations)


@router.post("/api/locations", status_code=201)
def add_location(request: Request, body: dict):
    return call(request, store.add_location, body.get("name"), body.get("kind"))


@router.patch("/api/locations/{id}")
def rename_location(request: Request, id: int, body: dict):
    return call(request, store.rename_location, id, body.get("name"))


@router.get("/api/books")
def books(request: Request, q: str = "", state: str | None = None, location_id: int | None = None,
          tag: str | None = None, limit: int = 50, offset: int = 0):
    return call(request, store.search_books, q, state, location_id, tag, limit, offset)


@router.post("/api/books", status_code=201)
def add_book(request: Request, body: dict):
    return call(request, store.add_book, body, request.state.user)


@router.get("/api/books/{id}")
def book(request: Request, id: int):
    return call(request, store.book, id)


@router.patch("/api/books/{id}")
def update_book(request: Request, id: int, body: dict):
    return call(request, store.update_book, id, body.get("version"), body.get("changes"), request.state.user)


@router.post("/api/captures")
async def add_capture(request: Request):
    async with incoming(request) as (path, upload):
        receipt = await run_in_threadpool(publish, request.app.state.data_root, path, upload, request.state.user)
    return JSONResponse(receipt, status_code=201 if receipt["created"] else 200)
