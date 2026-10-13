"""Identify tailnet people and agents before serving private data."""
import hashlib
import hmac
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse


class Access:
    """Apply authentication and the browser cross-site rule to every HTTP route."""

    def __init__(self, app, *, data_root, users, dev_user=None):
        self.app = app
        self.data_root = data_root
        self.users = set(users)
        self.dev_user = dev_user

    def identity(self, request):
        authorization = request.headers.get("authorization", "")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token:
                try:
                    expected = (self.data_root / "agent-token").read_text(encoding="ascii").strip()
                except (OSError, UnicodeError):
                    expected = ""
                actual = hashlib.sha256(token.encode()).hexdigest()
                if hmac.compare_digest(actual, expected):
                    return "agent", True
        if self.dev_user:
            return self.dev_user, False
        login = request.headers.get("tailscale-user-login")
        return (login if login in self.users else None), False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if request.method == "GET" and request.url.path == "/health":
            await self.app(scope, receive, send)
            return
        user, bearer = self.identity(request)
        if user is None:
            await JSONResponse({"error": "authentication required"}, status_code=401)(scope, receive, send)
            return
        if not bearer and request.method not in ("GET", "HEAD"):
            try:
                origin = urlsplit(request.headers.get("origin", ""))
                same_host = (origin.scheme in ("http", "https") and origin.username is None
                             and bool(origin.netloc) and origin.netloc.lower() == request.headers.get("host", "").lower())
            except ValueError:
                same_host = False
            if not same_host and request.headers.get("sec-fetch-site") != "same-origin":
                await JSONResponse({"error": "a same-origin request is required"}, status_code=403)(
                    scope, receive, send)
                return
        scope.setdefault("state", {})["user"] = user
        await self.app(scope, receive, send)
