"""The server-rendered pages: one router that collects the page modules."""
from contextlib import closing

from fastapi import APIRouter, Request

from home_library import store
from home_library.web.api import call
from home_library.web.book_pages import router as book_pages
from home_library.web.install import router as install
from home_library.web.location_pages import router as location_pages
from home_library.web.render import render
from home_library.web.status_pages import router as status_pages

router = APIRouter()
router.include_router(install)
router.include_router(book_pages)
router.include_router(location_pages)
router.include_router(status_pages)


@router.get("/")
def home(request: Request):
    with closing(store.open(request.app.state.data_root)) as db:
        open_count = len(store.observations(db))
    return render(request, "home.html", active="home", open_count=open_count)


@router.get("/capture")
def capture(request: Request):
    return render(request, "capture.html", active="capture", locations=call(request, store.locations),
                  states=store.STATES)
