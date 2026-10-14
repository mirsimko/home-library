"""The status page: what the queue and the worker are doing, and the size of each received photo."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from PIL import Image

from home_library import maintenance, store
from home_library.web.api import call
from home_library.web.files import photo_path
from home_library.web.render import render

router = APIRouter()

RECENT = 20
SMALL_SIDE = 3000
BACKUP_STALE = 2 * 86400


def ago(seconds):
    """How long ago, in the largest whole unit, for a person to read at a glance."""
    if seconds < 10:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        if seconds >= size:
            count = int(seconds // size)
            return f"{count} {unit}{'' if count == 1 else 's'} ago"


def within(seconds):
    """How soon, in whole minutes rounded up, so a wait never reads as over before it is."""
    count = max(1, -int(-seconds // 60))
    return f"{count} minute{'' if count == 1 else 's'}"


def seconds_since(stamp, now):
    return max(0, (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds())


def image_size(path):
    """The pixel size of a stored photo, read from its header; None when the file is gone or unreadable."""
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        return None


def panel_context(request):
    """Everything the status panel shows, read in one pass."""
    now = datetime.now(timezone.utc)
    root = request.app.state.data_root
    jobs = call(request, store.jobs)
    health = call(request, store.health)
    names = {row["id"]: row["name"] for row in call(request, store.locations)}
    recent = []
    for receipt in call(request, store.captures)[:RECENT]:
        capture = receipt["capture"]
        size = image_size(photo_path(root, capture))
        retry = store.retry_at(receipt["job"], now)
        recent.append({"id": capture["id"], "kind": capture["kind"], "location": names.get(capture["location_id"], ""),
                       "when": ago(seconds_since(capture["created_at"], now)), "job": receipt["job"]["status"],
                       "retry": within((retry - now).total_seconds()) if retry else None,
                       "open": receipt["open_observations"], "size": size,
                       "small": capture["kind"] == "shelf" and size is not None and max(size) < SMALL_SIDE})
    seen = health["worker_seen"]
    held = call(request, store.held_by, now)
    if held:
        held["wait"] = within((held["retry_at"] - now).total_seconds())
    return {"counts": {status: sum(job["status"] == status for job in jobs)
                       for status in ("queued", "running", "done", "failed")},
            "held": held, "backup": backup_context(request),
            "worker_seen": ago(seconds_since(seen, now)) if seen else None,
            "failed": [job for job in jobs if job["status"] == "failed"], "recent": recent}


def backup_context(request):
    """When the last backup worked, whether that is too long ago, and why the latest one was refused, if it was."""
    record = maintenance.backup_record(request.app.state.data_root)
    now = datetime.now(timezone.utc)
    try:
        since = seconds_since(record["last_success"], now) if record.get("last_success") else None
        failed = ago(seconds_since(record["failed_at"], now)) if record.get("failed_at") else None
    except ValueError:
        return {"state": "none", "last": None, "old": False, "failed": None, "error": None}
    error = record.get("error") if failed else None
    return {"state": "failed" if failed else "none" if since is None else "old" if since > BACKUP_STALE else "ok",
            "last": ago(since) if since is not None else None, "old": since is not None and since > BACKUP_STALE,
            "failed": failed, "error": error}


@router.get("/status")
def status(request: Request):
    return render(request, "status.html", active="status", **panel_context(request))


@router.get("/status/panel")
def panel(request: Request):
    return render(request, "status_panel.html", **panel_context(request))


@router.post("/status/jobs/{id}/retry")
def retry(request: Request, id: int, then: str = "row"):
    """Retry a failed job, or end the wait of the job that holds the queue (`then=panel` answers with the panel)."""
    try:
        job = call(request, store.retry_job, id)
    except store.Conflict as error:
        return render(request, "status_retried.html", status=409, job={"id": id}, error=str(error))
    if then == "panel":
        return render(request, "status_panel.html", **panel_context(request))
    return render(request, "status_retried.html", job=job, error=None)
