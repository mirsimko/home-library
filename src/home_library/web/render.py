"""Shared Jinja2 setup for the pages: one template folder, one way to render and to redirect."""
from pathlib import Path

from markupsafe import Markup
from starlette.responses import RedirectResponse, Response
from starlette.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

# The reader's language codes (pipeline.md, "language"); anything else gets no lang attribute.
LANGUAGES = ("ja", "cs", "en", "zh")


def lang(code):
    """A lang attribute for text in a known language, so Japanese and Czech titles get the right fonts."""
    return Markup(f' lang="{code}"') if code in LANGUAGES else Markup("")


TEMPLATES.env.globals["lang"] = lang


def render(request, name, status=200, **context):
    """Render one template with the signed-in person's name available to it."""
    context.setdefault("user", request.state.user)
    return TEMPLATES.TemplateResponse(request, name, context, status_code=status)


def redirect(request, url):
    """Send the browser on to a page: HTMX asks for a client redirect, a plain form post gets a 303."""
    if request.headers.get("hx-request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)
