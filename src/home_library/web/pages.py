"""The server-rendered pages: one router that collects the page modules."""
from contextlib import closing

from fastapi import APIRouter, Request

from home_library import store
from home_library.web.install import router as install
from home_library.web.render import render

router = APIRouter()
router.include_router(install)


@router.get("/")
def home(request: Request):
    with closing(store.open(request.app.state.data_root)) as db:
        open_count = len(store.observations(db))
    return render(request, "home.html", active="home", open_count=open_count)
