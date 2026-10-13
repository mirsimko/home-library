"""Run the private app with explicit binding and proxy trust."""
import os
from pathlib import Path

import uvicorn

from home_library.web import create_app


def serve(args, parser):
    """Resolve environment settings and reject unsafe implicit binding before startup."""
    host = args.host if args.host is not None else os.environ.get("UVICORN_HOST", "127.0.0.1")
    if host != "127.0.0.1" and args.host is None:
        parser.error("a non-loopback address requires an explicit --host")
    dev_user = os.environ.get("HL_DEV_USER") or None
    if dev_user and host != "127.0.0.1":
        parser.error("HL_DEV_USER requires --host 127.0.0.1")
    if dev_user and os.environ.get("HL_USERS", "").strip():
        parser.error("set HL_DEV_USER or HL_USERS, not both: a development identity would let every request in")
    if not host or not 1 <= args.port <= 65535:
        parser.error("choose a host and a port between 1 and 65535")
    root = args.data_root if args.data_root is not None else os.environ.get("HL_DATA") or Path.home() / "home-library"
    users = [login.strip() for login in os.environ.get("HL_USERS", "").split(",") if login.strip()]
    try:
        app = create_app(root, users, dev_user)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    # Query strings can contain titles, so the HTTP access log must be disabled.
    uvicorn.run(app, host=host, port=args.port, proxy_headers=True, forwarded_allow_ips="127.0.0.1", access_log=False)
    return 0
