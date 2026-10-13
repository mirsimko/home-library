"""Build the private web app shared by the JSON routes and the pages."""
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from home_library import store
from home_library.web.api import router
from home_library.web.auth import Access
from home_library.web.pages import router as pages
from home_library.web.render import render

HEADINGS = {400: "Something is wrong with this request", 404: "Not found", 409: "Someone else changed this"}


def fail(request, message, status):
    """Answer a browser navigation with a page, and scripts, the API and HTMX with JSON."""
    wants_page = ("text/html" in request.headers.get("accept", "") and "hx-request" not in request.headers
                  and not request.url.path.startswith("/api/"))
    if wants_page:
        return render(request, "error.html", status=status, heading=HEADINGS.get(status, "Something went wrong"),
                      message=message)
    return JSONResponse({"error": message}, status_code=status)


def create_app(data_root, users, dev_user=None):
    """Initialise a private data root and protect every route with the access rules."""
    with closing(store.open(data_root)):
        pass
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.data_root = Path(data_root).resolve()
    app.add_middleware(Access, data_root=app.state.data_root, users=users, dev_user=dev_user)
    for error, status in ((store.Invalid, 400), (store.NotFound, 404), (store.Conflict, 409)):
        async def store_error(request, exception, status=status):
            return fail(request, str(exception), status)
        app.add_exception_handler(error, store_error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exception):
        return fail(request, exception.errors()[0]["msg"], 400)

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        return fail(request, str(exception.detail), exception.status_code)

    app.include_router(router)
    app.include_router(pages)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app
