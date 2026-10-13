"""Build the private web app shared by JSON routes and future pages."""
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

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
    for error, status in ((store.Invalid, 400), (store.NotFound, 404), (store.Conflict, 409)):
        async def store_error(request, exception, status=status):
            return JSONResponse({"error": str(exception)}, status_code=status)
        app.add_exception_handler(error, store_error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exception):
        return JSONResponse({"error": exception.errors()[0]["msg"]}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        return JSONResponse({"error": str(exception.detail)}, status_code=exception.status_code)

    app.include_router(router)
    return app
