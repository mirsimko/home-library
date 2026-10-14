"""The review pages: the inbox of open observations, one observation at a time, and the actions on it."""
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from home_library import store
from home_library.web.api import call
from home_library.web.book_pages import posted_fields
from home_library.web.files import observation_candidates, read_json
from home_library.web.render import form_data, redirect, render
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


def heading(record):
    """The page heading: what was read, else the catalogue's title for a barcode alone, else a plain note."""
    title, language, _ = display_title(record)
    return {"title": title, "language": language}


def row_view(observation):
    title, language, note = display_title(observation["record"])
    return {"id": observation["id"], "number": observation["row"] + 1, "title": title, "language": language,
            "note": note, "isbn": observation["record"].get("isbn", ""), "status": observation["read_status"], "kind": observation["capture"]["kind"]}


def landing_notice(request, outcome, book_id):
    """What to say after an action, from the `done` and `book` the redirect carried."""
    if outcome not in NOTICES:
        return None
    try:
        found = call(request, store.book, book_id) if book_id else None
    except store.NotFound:
        found = None
    return {"text": NOTICES[outcome], "book": found}


@router.get("/review")
def inbox(request: Request, done: str = "", book: int | None = None):
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
    return render(request, "review.html", active="review", groups=groups, notice=landing_notice(request, done, book),
                  open_count=sum(len(group["rows"]) for group in groups))


# ---- one observation ----------------------------------------------------------------------------------

FORM_FIELDS = (*store.TEXT_FIELDS, "age_from", "age_to", "state", "location_id")
NOTICES = {"approved": "Approved as a new book", "attached": "Attached to the book", "dismissed": "Dismissed",
           "added": "Book added by hand"}


def evidence(root, observation):
    """The picture to look at: the tile named in `where`, else a cover's one tile, else the whole photo."""
    capture = observation["capture"]
    photo = f"/api/captures/{capture['id']}/photo"
    manifest = read_json(root / "work" / capture["id"] / "tiles.json", {})
    entries = manifest.get("tiles", []) if isinstance(manifest, dict) else []
    files = [entry["file"] for entry in entries if isinstance(entry, dict) and isinstance(entry.get("file"), str)] \
        if isinstance(entries, list) else []
    words = re.split(r"[\s,;]+", str(observation["record"].get("where") or "").strip())
    is_cover = isinstance(manifest, dict) and manifest.get("kind") == "cover"
    tile = words[0] if words[0] in files else files[0] if files and is_cover else None
    return {"src": f"/api/captures/{capture['id']}/tiles/{tile}" if tile else photo, "photo": photo,
            "tile": tile is not None}


def prefill(suggested):
    """The book form's starting values: what the store's rule suggests for this evidence, as the form's text."""
    values = dict.fromkeys(FORM_FIELDS, "")
    for key in FORM_FIELDS:
        if suggested.get(key) not in (None, ""):
            values[key] = str(suggested[key])
    return values


def fill_from(candidate):
    """What "Use this record" puts into the form: the candidate's non-empty catalogue fields."""
    fill = {"title": candidate.get("title"), "author": "; ".join(candidate.get("authors") or []),
            "sort_key": candidate.get("title_reading"),
            "publisher": candidate.get("publisher"), "year": candidate.get("year"), "isbn": candidate.get("isbn"),
            "series": candidate.get("series"), "language": candidate.get("language"),
            "source": candidate.get("source"), "source_id": candidate.get("source_id")}
    return {key: value for key, value in fill.items() if value}


def neighbours(order, id):
    """The links to the observation before and after this one in the inbox order."""
    if id not in order:
        return None, None
    index = order.index(id)
    return (f"/review/{order[index - 1]}" if index else None,
            f"/review/{order[index + 1]}" if index + 1 < len(order) else None)


def detail(request, id, status=200, without=(), **extra):
    """Render one observation with everything a person needs to decide, or why it has no actions."""
    root = request.app.state.data_root
    observation = call(request, store.observation, id)
    capture = observation["capture"]
    open_ones = call(request, store.observations)
    order = [o["id"] for members in inbox_order(open_ones) for o in members]
    siblings = [o for o in open_ones if capture["group_id"] and o["capture"]["group_id"] == capture["group_id"]
                and o["id"] != id]
    siblings.sort(key=lambda o: (captured_at(o), o["row"]))
    current = call(request, store.candidate_observation, id)
    candidates = observation_candidates(root, current) if current is not None else []
    previous, following = neighbours(order, id)
    names = {row["id"]: row["name"] for row in call(request, store.locations)}
    book = call(request, store.book, observation["book_id"]) if observation["book_id"] else None
    return render(request, "review_detail.html", status=status, active="review", observation=observation,
                  record=observation["record"], heading=heading(observation["record"]), capture=capture, location=names.get(capture["location_id"], ""),
                  evidence=evidence(root, observation), book=book,
                  siblings=[{**row_view(o), "photo": f"/api/captures/{o['capture_id']}/photo", "included": o["id"] not in without}
                            for o in siblings],
                  candidates=[{**c, "fill": fill_from(c)} for c in candidates],
                  values=prefill(call(request, store.default_fields, [id, *(o['id'] for o in siblings if o['id'] not in without)])), locations=call(request, store.locations),
                  states=store.STATES, previous=previous, following=following,
                  position=order.index(id) + 1 if id in order else None, total=len(order), **extra)


@router.get("/review/{id}")
def review_detail(request: Request, id: int, done: str = "", book: int | None = None, without: str = ""):
    """`without` lists, comma-separated, the paired photos the person unticked: the form leaves them out."""
    ids = [part for part in without.split(",") if part.strip()]
    if not all(part.strip().isdecimal() for part in ids):
        raise store.Invalid("without must list observation ids")
    return detail(request, id, without={int(part) for part in ids}, notice=landing_notice(request, done, book))


# ---- the actions ---------------------------------------------------------------------------------------


def open_order(request):
    """The ids of every open observation in the order the inbox shows them."""
    return [o["id"] for members in inbox_order(call(request, store.observations)) for o in members]


def next_after(order, consumed, current):
    """The open observation to show after an action: the next one, else the nearest one before."""
    index = order.index(current) if current in order else len(order)
    return next((id for id in [*order[index + 1:], *reversed(order[:index])] if id not in consumed), None)


def done(request, order, consumed, current, outcome, book_id=None):
    """Go to the next open observation, or to the inbox when none is left, saying what just happened."""
    query = urlencode({"done": outcome, **({"book": book_id} if book_id else {})})
    target = next_after(order, set(consumed), current)
    return redirect(request, f"/review/{target}?{query}" if target else f"/review?{query}")


def refused(request, status, problem):
    return render(request, "review_error.html", status=status, error=str(problem))


def chosen(id, form):
    """The observation on this page and any others the person ticked for the same book."""
    if not all(other.isdecimal() for other in form.getlist("also")):
        raise store.Invalid("observation ids must be numbers")
    return [id, *(int(other) for other in form.getlist("also"))]


@router.post("/review/{id}/approve")
def approve(request: Request, id: int, form=Depends(form_data)):
    order = open_order(request)
    try:
        ids = chosen(id, form)
        book = call(request, store.approve, ids, posted_fields(form), request.state.user)
    except store.Invalid as problem:
        return refused(request, 400, problem)
    except store.NotFound as problem:
        return refused(request, 404, problem)
    return done(request, order, ids, id, "approved", book["id"])


@router.post("/review/{id}/dismiss")
def dismiss(request: Request, id: int):
    order = open_order(request)
    try:
        call(request, store.dismiss, [id], request.state.user)
    except store.Invalid as problem:
        return refused(request, 400, problem)
    except store.NotFound as problem:
        return refused(request, 404, problem)
    return done(request, order, [id], id, "dismissed")


@router.get("/review/{id}/attach-search")
def attach_search(request: Request, id: int, q: str = ""):
    names = {row["id"]: row["name"] for row in call(request, store.locations)}
    books = call(request, store.search_books, q.strip(), None, None, None, 8) if q.strip() else None
    return render(request, "review_attach_results.html", observation_id=id, books=books, names=names)


@router.post("/review/{id}/attach")
def attach(request: Request, id: int, form=Depends(form_data)):
    order = open_order(request)
    try:
        book_id = form.get("book_id", "")
        if not book_id.isdecimal():
            raise store.Invalid("choose a book to attach this to")
        ids = chosen(id, form)
        book = call(request, store.attach, ids, int(book_id), request.state.user)
    except store.Invalid as problem:
        return refused(request, 400, problem)
    except store.NotFound as problem:
        return refused(request, 404, problem)
    return done(request, order, ids, id, "attached", book["id"])
