"""The review pages: the inbox of open observations, one observation at a time, and the actions on it."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from home_library import store
from home_library.web.api import call
from home_library.web.render import render
from home_library.web.status_pages import ago, seconds_since

router = APIRouter()

KIND_LABELS = {"shelf": "Shelf photo", "cover": "Cover photo", "barcode": "Barcode photo"}


def captured_at(observation):
    return datetime.fromisoformat(observation["capture"]["created_at"].replace("Z", "+00:00"))


def inbox_order(open_observations):
    """Group open observations by one-book group, else by capture; newest group first, rows in photo order."""
    groups = {}
    for observation in open_observations:
        capture = observation["capture"]
        groups.setdefault(capture["group_id"] or capture["id"], []).append(observation)
    for members in groups.values():
        members.sort(key=lambda o: (captured_at(o), o["capture_id"], o["row"]))
    return sorted(groups.values(), key=lambda members: max(captured_at(o) for o in members), reverse=True)


def display_title(record):
    """What to call a row in a list: the reading, else the catalogue's title, else the barcode."""
    if record.get("title"):
        return record["title"], record.get("language", ""), ""
    if record.get("catalogue_title"):
        return record["catalogue_title"], record.get("language", ""), "catalogue"
    if record.get("isbn"):
        return record["isbn"], "", "ISBN"
    return "(nothing read)", "", ""


def row_view(observation):
    title, language, note = display_title(observation["record"])
    return {"id": observation["id"], "number": observation["row"] + 1, "title": title, "language": language,
            "note": note, "isbn": observation["record"].get("isbn", ""), "status": observation["read_status"], "kind": observation["capture"]["kind"]}


@router.get("/review")
def inbox(request: Request):
    now = datetime.now(timezone.utc)
    names = {row["id"]: row["name"] for row in call(request, store.locations)}
    groups = []
    for members in inbox_order(call(request, store.observations)):
        capture = members[0]["capture"]
        grouped = capture["group_id"] is not None
        groups.append({
            "label": "One book" if grouped else KIND_LABELS[capture["kind"]],
            "location": names.get(capture["location_id"], ""), "by": capture["uploaded_by"],
            "when": ago(seconds_since(max(o["capture"]["created_at"] for o in members), now)),
            "rows": [row_view(o) for o in members]})
    return render(request, "review.html", active="review", groups=groups,
                  open_count=sum(len(group["rows"]) for group in groups))
