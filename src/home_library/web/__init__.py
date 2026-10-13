"""Build the private web app shared by JSON routes and future pages."""
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI

from home_library import store
from home_library.web.api import router
from home_library.web.auth import Access


def create_app(data_root, users, dev_user=None):
    """Initialise a private data root and protect every route with the access rules."""
    with closing(store.open(data_root)):
        pass
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.data_root = Path(data_root).resolve()
    app.add_middleware(Access, data_root=app.state.data_root, users=users, dev_user=dev_user)
    app.include_router(router)
    return app
