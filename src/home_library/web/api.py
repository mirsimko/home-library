"""JSON routes backed by the shared catalogue store."""
from contextlib import closing

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from home_library import records, store
from home_library.web.files import (
    checked_file,
    observation_candidates,
    photo_path,
    photo_response,
    tile_response,
)
from home_library.web.uploads import image_info, incoming, publish

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


@router.post("/api/books/move")
def move_books(request: Request, body: dict):
    return call(request, store.move_books, body.get("book_ids"), body.get("location_id"), body.get("state"),
                by=request.state.user)


@router.get("/api/books/{id}")
def book(request: Request, id: int):
    return call(request, store.book, id)


@router.patch("/api/books/{id}")
def update_book(request: Request, id: int, body: dict):
    return call(request, store.update_book, id, body.get("version"), body.get("changes"), request.state.user)


@router.post("/api/captures")
async def add_capture(request: Request):
    try:
        async with incoming(request) as (path, upload):
            receipt = await run_in_threadpool(publish, request.app.state.data_root, path, upload, request.state.user)
    except OSError as error:
        raise HTTPException(503, "the photo could not be stored; retry the upload") from error
    return JSONResponse(receipt, status_code=201 if receipt["created"] else 200)


@router.get("/api/captures")
def captures(request: Request, ids: str | None = None):
    return call(request, store.captures, None if ids is None else ids.split(",") if ids else [])


@router.get("/api/captures/{id}")
def capture(request: Request, id: str):
    receipt = call(request, store.capture, id)
    root = request.app.state.data_root
    path = checked_file(photo_path(root, receipt["capture"]), root / "captures")
    return {**receipt, "image": image_info(path)}


@router.get("/api/captures/{id}/photo")
def capture_photo(request: Request, id: str):
    return photo_response(request.app.state.data_root, call(request, store.capture, id)["capture"])


@router.get("/api/captures/{id}/tiles/{file}")
def capture_tile(request: Request, id: str, file: str):
    return tile_response(request.app.state.data_root, call(request, store.capture, id)["capture"], file)


@router.get("/api/observations")
def observations(request: Request, status: str = "open", capture_id: str | None = None):
    return call(request, store.observations, status, capture_id)


@router.post("/api/observations/approve", status_code=201)
def approve(request: Request, body: dict):
    return call(request, store.approve, body.get("observation_ids"), body.get("fields", {}), request.state.user)


@router.post("/api/observations/attach")
def attach(request: Request, body: dict):
    return call(request, store.attach, body.get("observation_ids"), body.get("book_id"), request.state.user)


@router.post("/api/observations/dismiss")
def dismiss(request: Request, body: dict):
    return call(request, store.dismiss, body.get("observation_ids"), request.state.user)


@router.get("/api/observations/{id}/candidates")
def candidates(request: Request, id: int):
    return observation_candidates(request.app.state.data_root, call(request, store.observation, id))


@router.get("/api/jobs")
def jobs(request: Request):
    return call(request, store.jobs)


@router.post("/api/jobs/{id}/retry")
def retry_job(request: Request, id: int):
    return call(request, store.retry_job, id)


@router.get("/export.json")
def export_json(request: Request):
    return JSONResponse(call(request, store.export_books), headers={"Cache-Control": "private"})


@router.get("/export.csv")
def export_csv(request: Request):
    rows = call(request, store.export_rows)
    columns = records.COLUMNS[:records.COLUMNS.index("photo")]
    return Response(records.csv_text(rows, columns), media_type="text/csv", headers={"Cache-Control": "private"})
