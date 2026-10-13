"""JSON routes backed by the shared catalogue store."""
from contextlib import closing

from fastapi import APIRouter, Request

from home_library import store

router = APIRouter()


@router.get("/health")
def health(request: Request):
    with closing(store.open(request.app.state.data_root)) as db:
        return store.health(db)
