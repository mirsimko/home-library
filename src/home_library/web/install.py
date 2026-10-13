"""What a phone needs to install the app: a manifest, icons drawn on demand, and an idle service worker."""
import json
from functools import cache
from io import BytesIO

from fastapi import APIRouter, HTTPException
from PIL import Image, ImageDraw
from starlette.responses import Response

router = APIRouter()

SIZES = (180, 192, 512)
BACKGROUND = "#2d6a58"
PAGE = "#f6efe0"
RIBBON = "#e0a63a"

SERVICE_WORKER = """// Installs, claims the open pages and caches nothing: it exists only so that phones offer to install the app.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
// A fetch handler that does nothing leaves every request to the browser's own network handling.
self.addEventListener("fetch", () => {});
"""


@cache
def icon(size):
    """An open book on the app's green, drawn at four times the size and scaled down for smooth edges.

    The drawing stays inside the middle 80 per cent so that a phone may crop the icon to a circle.
    """
    scale = 4 * size

    def point(x, y):
        return (x * scale, y * scale)

    image = Image.new("RGB", (scale, scale), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.polygon([point(0.22, 0.32), point(0.49, 0.38), point(0.49, 0.70), point(0.22, 0.64)], fill=PAGE)
    draw.polygon([point(0.78, 0.32), point(0.51, 0.38), point(0.51, 0.70), point(0.78, 0.64)], fill=PAGE)
    for step in range(4):
        drop = 0.06 * step
        draw.line([point(0.28, 0.42 + drop), point(0.44, 0.46 + drop)], fill=BACKGROUND, width=max(2, scale // 60))
        draw.line([point(0.72, 0.42 + drop), point(0.56, 0.46 + drop)], fill=BACKGROUND, width=max(2, scale // 60))
    draw.polygon([point(0.62, 0.34), point(0.68, 0.35), point(0.68, 0.50), point(0.65, 0.47), point(0.62, 0.50)],
                 fill=RIBBON)
    output = BytesIO()
    image.resize((size, size), Image.LANCZOS).save(output, "PNG", optimize=True)
    return output.getvalue()


@router.get("/icons/icon-{size}.png")
def icon_file(size: int):
    if size not in SIZES:
        raise HTTPException(404, "there is no icon of that size")
    return Response(icon(size), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/manifest.webmanifest")
def manifest():
    body = {
        "name": "Home library", "short_name": "Library", "start_url": "/capture", "scope": "/",
        "display": "standalone", "theme_color": BACKGROUND, "background_color": "#f5f3ee",
        "icons": [{"src": f"/icons/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png",
                   "purpose": "any maskable"} for size in (192, 512)],
    }
    return Response(json.dumps(body), media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    return Response(SERVICE_WORKER, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
