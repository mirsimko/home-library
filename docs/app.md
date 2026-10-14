# Capture and review app: contract

This is the contract of the app built on top of the shelf-photo pipeline: the catalog store, the job queue and worker, cover and barcode photos, the HTTP API, the pages, and how it runs. Why it is shaped this way is in the [implementation plan](plans/home-library-app-plan-20261013.html) (decisions D1 to D10) and the [framework research](research/app-framework.md). The pipeline's own contract is [pipeline.md](pipeline.md); the app depends only on the `hl` command line and the files it writes.

Status: built on branch `app/phase-1` on 2026-10-13 and reviewed by a council of three models (Opus 5.5, Fable 5.1, Grok 4.7). Not yet tried on the real devices (plan, phase 0).

## Rules that hold everywhere

- Everything in [pipeline.md](pipeline.md), "Rules that hold everywhere", holds here too. In particular: **no private data in this repository**, and tests use generated images and invented titles.
- **Three kinds of thing** (plan D4). A *capture* is one uploaded photo. An *observation* is one row of a capture's `records.json`: evidence, never a book. A *book* is one physical copy, and exists only once a person (or an agent through the API) approves it, with a state and a location.
- **Every write goes through `home_library.store`.** The HTTP API, the pages, the worker and `hl catalog` all call the same functions, so the same checks hold for all of them (plan D10). Nothing else writes `catalog.db`.
- **Nothing is lost silently.** A failed job, an unreadable barcode and an observation nobody has looked at stay visible in the app until a person deals with them.
- **No titles and no photo content in logs.** Logs name captures by id only.

## Data root

One directory holds everything private. It is `$HL_DATA`, or `~/home-library/` by default, and it must not lie inside a git checkout (`workspace.refuse_inside_checkout`).

```text
<data-root>/
  catalog.db              SQLite, WAL mode; the catalog and the job queue
  captures/<id>.jpg       uploaded photos, named by capture id; .png and .webp are kept as uploaded
  work/<id>/              the pipeline's work directory of each capture (pipeline.md, "Work directory")
  agent-token             sha256 of the bearer token agents use (see Access); absent means no agent access
```

Because a capture's file is named by its id, the pipeline's work directory is `work/<id>/` and two uploads can never share one, whatever their original file names (plan D5).

## Store (`home_library.store`)

`store.open(data_root)` opens or creates `catalog.db`, applies the numbered migrations in `home_library/migrations/NNNN_*.sql` that have not run yet (tracked in `PRAGMA user_version`), and returns a connection with foreign keys on and WAL mode. It reads `user_version` first and takes the write lock (`BEGIN IMMEDIATE`) only when a migration is pending, checking the version again inside the transaction, so opening an up-to-date store never waits for another writer. Times are ISO 8601 UTC strings.

### Tables

| Table | Columns |
|---|---|
| `locations` | `id` integer key; `name` unique, not empty, trimmed; `kind` `shelf` or `box`; `created_at` |
| `captures` | `id` text key, a lowercase canonical UUID from the client; `kind` `shelf`, `cover` or `barcode`; `location_id`; `default_state`; `group_id` text or null, a UUID pairing a cover with its barcode; `uploaded_by`; `original_name`; `media_type`; `sha256`; `bytes`; `created_at` |
| `jobs` | `id` integer key; `capture_id` unique; `status` `queued`, `running`, `done` or `failed`; `attempts`; `owner` text or null; `heartbeat_at`; `started_at`; `finished_at`; `error` text |
| `observations` | `id` integer key; `capture_id`; `attempt`; `row` (index in `records.json`); `read_status`; `title`; `other_reading`; `record` (the whole row as JSON); `status` `open`, `used`, `dismissed` or `superseded`; `book_id` or null; `created_at`; unique (`capture_id`, `attempt`, `row`) |
| `books` | `id` integer key; the fields of spec 2.1: `title`, `sort_key`, `author`, `illustrator`, `publisher`, `year`, `language`, `isbn`, `series`, `age_from`, `age_to` (integers or null), `tags` (comma-separated), `state`, `location_id` (not null), `cover_capture_id`, `source`, `source_id`, `needs_review`, `notes`; then `version`, `created_by`, `reviewed_by`, `created_at`, `updated_at` |
| `books_fts` | FTS5, tokenizer `trigram`, over `title`, `sort_key`, `author`, `series`, `isbn`, kept in step with `books` by triggers |

States are `Active`, `Stored`, `Retired` and `Gone` (a book that left the house keeps its record; plan question 6). A book's `title` must not be empty and its `location_id` must name a location.

### Functions

Every function takes the connection first. A rule that is broken raises `store.Invalid` (a `ValueError`) with a message a person can act on; a stale `version` raises `store.Conflict`; a missing row raises `store.NotFound`.

- **Locations:** `add_location(name, kind)`, `rename_location(id, name)`, `locations()`.
- **Captures:** `add_capture(id, kind, location_id, default_state, uploaded_by, original_name, media_type, sha256, bytes, group_id=None)` inserts the capture and its `queued` job in one transaction and returns the receipt `{"capture": ..., "job": ..., "created": True}`. The same id again with the same sha256 returns the stored receipt with `created` false and adds nothing; with another sha256 it raises `Conflict`. Another capture with the same sha256 is allowed: the receipt then lists it under `"duplicate_of"` so the page can warn.
- **Jobs:**
  - `claim_job(now)` takes, in one `BEGIN IMMEDIATE` transaction, the oldest job that is `queued`, or `running` with a heartbeat older than 20 minutes (its worker died). It sets `running`, adds one to `attempts`, sets a fresh random `owner` and the heartbeat, and returns the job with its capture and location name. A stale job that has already had 3 attempts is set `failed` instead, with the error "the worker stopped responding 3 times". Returns None when there is nothing to do.
  - `heartbeat(job_id, owner, now)` refreshes the heartbeat only while `owner` still holds the job; returns whether it did.
  - `finish_job(job_id, owner, records, now)` imports the rows of `records.json` as `open` observations of this attempt, marks the capture's earlier `open` observations `superseded`, and sets the job `done`, all in one transaction. If `owner` no longer holds the job it changes nothing and raises `Conflict`: a late write from a superseded attempt is refused. Observations that are `used` or `dismissed`, and every book, are never touched.
  - `fail_job(job_id, owner, error, now)` puts the job back to `queued` while it has had fewer than 3 attempts, else sets it `failed`; the error is kept either way. Same owner rule.
  - `release_job(job_id, owner)` puts a `running` job that `owner` holds back to `queued`, gives back its attempt (one fewer, never below 0) and clears its owner and heartbeat; any other caller raises `Conflict`. The worker calls it when it stops on SIGTERM or SIGINT.
  - `retry_job(job_id)` sets a `failed` job back to `queued` with `attempts` 0; any other job raises `Conflict` (409 over HTTP). A `done` capture is not read again, because importing it a second time would re-open rows that were already approved as duplicates.
- **Observations:** `observations(status="open", capture_id=None)`; `dismiss(observation_ids, by)`.
- **Books:**
  - `default_fields(observation_ids)` is the one rule that fills a book from evidence; `approve` and the review page both use it. For each catalogue field (`sort_key`, `author`, `illustrator`, `publisher`, `year`, `language`, `isbn`, `series`, `source`, `source_id`, `age_from`, `age_to`) it takes the first non-empty value from the rows that matched a catalogue record (their `source` is not empty), else the first non-empty value from any row; so a decoded ISBN from a barcode that matched nothing is kept, and a blank in the catalogue's record does not hide a value that was read. The title is the first non-empty read title, else the first non-empty catalogue title; `sort_key` falls back to the title; `tags` come from the first row that has them; `notes` are empty (the pipeline's notes say why a row needs a look, and are not about the book). `location_id` and `state` come from the first capture, and a cover capture becomes `cover_capture_id`. The evidence counts in the order it was photographed (capture time, then row), whichever way the ids are given, so the result does not depend on which observation a person opened.
  - `approve(observation_ids, fields, by)` creates one book from one or more open observations (for example a cover and its barcode, or a shelf row and a cover), marks them `used` with the new `book_id`, and returns the book. Every field not in `fields` is taken from `default_fields`. The new book has `needs_review` false and `reviewed_by` set.
  - `attach(observation_ids, book_id, by)` marks open observations `used` by an existing book, and sets its cover if it has none and one of them is a cover.
  - `add_book(fields, by)` adds a book typed in by hand.
  - `update_book(id, version, changes, by)` applies a partial change if `version` is current, then adds one to it. A field that is not a book field is refused.
  - `move_books(ids, location_id=None, state=None, by)` changes location or state of several books in one transaction.
  - `book(id)`; `search_books(query="", state=None, location_id=None, tag=None, limit=50, offset=0)`. A query of three or more characters uses `books_fts`; a shorter one, which is common for Japanese titles, uses a `LIKE` match on the same columns. Results sort by `sort_key`, then `title`.
- **Export:** `export_rows()` gives every book as a flat dict with the location's name, in the column order of spec 2.1. `export_books()` adds sorted, distinct `capture_ids` from its observations and its chosen cover, in the same database snapshot.
- **Web reads:** `capture(id)` returns the stored receipt plus `open_observations`; `captures(ids=None)` lists these newest first; `jobs()` lists jobs in id order; `health()` gives the title-free worker summary; `observation(id)` returns one row with its record and capture; `candidate_observation(id)` returns it only for the latest completed import, otherwise None; `locations_with_counts()` lists locations with the number of books each holds. `validate_capture(...)` checks the same metadata as `add_capture` without writing, and returns the stored receipt when the id and hash already exist. Upload publication calls it before moving the file, then calls `add_capture`, which checks again in its write transaction.

## Worker (`home_library.worker`, `hl worker`)

One process that drains the job queue, one job at a time (the home uplink carries one photo at a time; pipeline.md, "What runs at once").

- It claims a job, then runs the pipeline for the capture as a child process in its own process group, with the data root's `work/` as work root. The location goes as the single argument `--location=<name>`, so a name that starts with `-` cannot be read as an option:
  - `shelf`: `hl --work-root <work> run <captures>/<id>.jpg --location=<name>`
  - `cover`: `hl --work-root <work> cover <captures>/<id>.jpg --location=<name>`
  - `barcode`: `hl --work-root <work> barcode <captures>/<id>.jpg --location=<name>`
- While the child runs, a thread calls `heartbeat` every 30 seconds. After 20 minutes the whole process group is killed and the job fails with a timeout. If `heartbeat` reports the job lost, the child is killed and nothing is imported. An error from `heartbeat` (a busy database) is logged and tried again at the next beat; only three errors in a row count as a lost lease.
- When the child exits 0, the worker reads `work/<id>/records.json` and calls `finish_job`. A non-zero exit, a missing or unreadable `records.json`, or a timeout calls `fail_job` with the last 2000 characters of the child's standard error.
- With nothing to do it waits 5 seconds and looks again. A database error (a locked or briefly unavailable `catalog.db`) while claiming, finishing or failing a job is logged by job id, never with titles, and the loop waits the same 5 seconds and goes on; a job whose result could not be recorded keeps its lease, and another attempt takes it over when the lease runs out. It stops cleanly on SIGTERM or SIGINT: a running child is killed and its job is given back with `release_job`, so a restart takes it at once and the stop costs no attempt. (A worker that is killed outright cannot do this; its job is taken over once its heartbeat is stale.)
- `hl worker --once` handles at most one job and exits; tests and a harness use it.
- The worker runs the child through an injectable runner, so tests use a fake `hl` the way `tests/test_reader.py` fakes `codex`.

## Cover and barcode photos (`hl cover`, `hl barcode`)

Both write the same `records.json` and `records.csv` as `hl run`, in the photo's work directory, so the worker treats every kind alike.

### `hl cover <photo> --location <name>`

- Stage 1 for a cover cuts no tiles: it writes the photo, EXIF orientation applied and scaled so that its longer side is at most 2000 pixels, as the single image `tiles/cover-r0.jpg`, and a `tiles.json` with `"kind": "cover"` and that one entry. A photo already that small is not enlarged.
- The two blind reads, the merge, the look-up, the pick and the records then run as for a shelf photo, with these differences:
  - The read prompt is `prompts/cover_read.txt`: one book, seen from the front. The answer has the same shape and the same nine fields as a shelf read, plus an optional tenth field, `author`, for the author's name as printed. The parser keeps `author` when it is given and sets it to the empty string otherwise, for every read.
  - The look-up passes an item's `author` to `find_candidates`, so the title-and-author step runs.
  - The record's `author` column is the catalogue's when a candidate was matched, and otherwise the author as read.
- Rerunning is safe in the same way as for `hl run`.

### `hl barcode <photo> --location <name>`

- Decodes the photo with `zxing-cpp` (EXIF orientation applied first). Of the codes it finds, the first EAN-13 that is a valid ISBN-13 is used: prefix 978 or 979 and a correct check digit. An ISBN-10 printed as text is not looked for; that would be OCR.
- The language comes from the registration group: `978-4` Japanese, `978-80` Czech, `978-0`, `978-1` and `979-8` English. For any other group every language's sources are tried, Japanese, then Czech, then English, until one returns a record.
- Only the ISBN step of the look-up runs. A candidate whose ISBN equals the decoded one is the match, the first in source order; no model is asked.
- It writes one record. `read_status` is `barcode`, `isbn` is the decoded ISBN, `title` is empty (nothing was read), and the catalogue fields come from the match. Without a match the record says so in `notes`. When no ISBN could be decoded the record's `read_status` is `no_barcode`, and `notes` says to type the number in.
- `barcode.json` in the work directory keeps what was decoded: every code found, its format and text, and which one was used.

## Access

The app listens on `127.0.0.1` by default. Another bind address requires an explicit `hl serve --host` argument. Tailscale Serve puts it on the tailnet with HTTPS and adds the header `Tailscale-User-Login` to each request (plan D9).

- A browser request is let in when its `Tailscale-User-Login` is one of the logins in `$HL_USERS` (comma-separated). That login is the person's name in the catalog (`uploaded_by`, `created_by`, `reviewed_by`).
- An agent sends `Authorization: Bearer <token>`. The token is let in when its sha256 equals the one in `<data-root>/agent-token`; its name in the catalog is `agent`. `hl token` makes a new token, prints it once and stores its hash, which also revokes the old one.
- Everything else gets 401, except `GET /health`.
- `$HL_DEV_USER` lets every request in as that login, for local development. `hl serve` refuses it unless it listens on `127.0.0.1`, and refuses to start at all when `HL_USERS` is set as well, because the development identity would let every request in whatever its login.
- **Cross-site requests.** A browser request with a method other than GET or HEAD must carry an `Origin` header whose host is the request's own `Host`, or `Sec-Fetch-Site: same-origin`. Otherwise it gets 403. Bearer-token requests are exempt.
- Photos and tiles are served only to requests that are let in. The authenticated name is available to handlers as `request.state.user`.

When access methods overlap, a valid bearer token names `agent`; otherwise the development identity takes precedence over an allowed Tailscale login. An invalid bearer token does not grant the cross-site exemption. Origin comparison uses the HTTP or HTTPS authority, including any explicit port, without regard to case; credentials in the Origin are refused. Development browser writes still need the same-origin proof.

`hl serve` trusts proxy headers only from `127.0.0.1`. Its HTTP access log is disabled because a search URL can contain a title.

## HTTP API

JSON in and out. Errors are `{"error": "<message>"}` with 400 (`Invalid`), 404, 409 (`Conflict`) or 413/415 for uploads. Malformed JSON, path and query values also return 400. An upload's missing location is a 400 metadata error with the store's message; a missing resource requested by URL returns 404. A file-system failure during upload returns 503 with a message inviting a retry.

| Method and path | Does |
|---|---|
| `POST /api/captures` | Multipart: `file`, `id`, `kind`, `location_id`, `state` (default `Active`), optional `group_id`. Returns 201 with the receipt, or 200 with the stored receipt for a repeated id. JPEG, PNG and WebP only (a JPEG that carries a second image, as Android Ultra HDR photos do, is accepted and kept as `.jpg`), found from the file's content, not its name or declared type (415 otherwise); at most 40 MB (413). The file is written to a temporary file, flushed to disk and moved into place before the capture is recorded. |
| `GET /api/captures` | Recent captures with their job status and how many open observations each has. `?ids=a,b` limits it to those captures. |
| `GET /api/captures/{id}` | One stored receipt with its job, open observation count and `image` metadata. |
| `GET /api/captures/{id}/photo` | The photo. |
| `GET /api/captures/{id}/tiles/{file}` | One tile image of the capture's work directory; `file` must be a tile name the manifest lists. |
| `GET /api/jobs` | The queue, with the worker's last heartbeat. `POST /api/jobs/{id}/retry`. |
| `GET /api/observations` | `?status=open` by default; `?capture_id=`. Each with its record and its capture. |
| `POST /api/observations/approve` | `{"observation_ids": [...], "fields": {...}}`, returns the new book. |
| `POST /api/observations/attach` | `{"observation_ids": [...], "book_id": n}`. |
| `POST /api/observations/dismiss` | `{"observation_ids": [...]}`. |
| `GET /api/observations/{id}/candidates` | The catalogue candidates the pipeline fetched for this observation's item, from `lookup/candidates.json`. |
| `GET /api/books` | `?q=&state=&location_id=&tag=&limit=&offset=`. |
| `POST /api/books` | Add a book by hand. |
| `GET /api/books/{id}`, `PATCH /api/books/{id}` | Read; change with `{"version": n, "changes": {...}}`. |
| `POST /api/books/move` | `{"book_ids": [...], "location_id": n, "state": "Stored"}`, either may be left out. |
| `GET /api/locations`, `POST /api/locations`, `PATCH /api/locations/{id}` | List, add, rename. |
| `GET /export.csv`, `GET /export.json` | Every book. CSV in UTF-8 with a byte-order mark and the formula escaping of `records.py`. JSON with each book's capture ids. |
| `GET /health` | `{"ok": true, "worker_seen": "<last heartbeat or null>", "queued": n, "failed": n}`. No titles. |

### Response and file details

- Listings are JSON arrays. Capture entries contain `capture`, `job`, `created: false`, `open_observations` and, when relevant, `duplicate_of`. The capture list has no implicit limit and is ordered newest first. An empty `ids=` selects none.
- Upload receipts and single-capture details include `image: {"width": n, "height": n, "format": "JPEG|PNG|WEBP", "orientation": n|null}`. Width and height describe the original pixels before EXIF rotation. Uploads keep the original bytes, including metadata. The original filename is stored only as text.
- Here 40 MB means 40,000,000 file bytes, excluding multipart fields and framing. Multipart bytes stream directly into `captures/.incoming/*.tmp`; the limit is checked before each file chunk is written. The temporary file is flushed and fsynced before `os.replace` publishes it. A Linux/WSL file lock in `.incoming/.lock` serialises publication, including simultaneous retries; a repeated id never replaces its stored file. Temporary files are removed after rejection or completion, and a failed store insert removes the newly published file.
- `captures/` (or `work/<id>/tiles/`) may itself be a symlink, for example to another disk: the containment checks resolve the directory as well as the file, so only a file whose real path leaves it is refused.
- Photo and tile responses carry their image media type and `Cache-Control: private`. A tile must have a plain basename listed in `tiles.json`, and resolve inside that capture's `tiles/` directory.
- Candidate matching uses the observation's zero-based `row`, rather than its title: the pipeline writes one record per merged item first, in item order. Unreadable, unparsed, incomplete and no-barcode rows have no candidates. Missing or unfinished look-up output yields an empty list. So do observations from older attempts, and observations whose capture is being retried: only the latest completed import can use the current candidate file. This keeps the pipeline records and stored observations unchanged.
- Creating a location or book, and approving observations, returns 201. Other catalogue writes return 200 with the store result. Dismissal returns the dismissed observations; attachment returns the existing book.
- Both exports use spec 2.1 field order and catalogue sort order. JSON adds `capture_ids`, including evidence and the chosen cover, or an empty list for a manually entered book without either. CSV uses the escaping in `records.py`, writes null cells as empty text and booleans as lowercase `true` and `false`, as `records.csv` does. Both responses carry `Cache-Control: private`.

`home_library.web.create_app(data_root, users, dev_user=None)` constructs the protected app. It also mounts the pages (below) and `/static`; the templates and static files are part of the package. A browser navigation (an `Accept` header with `text/html`, not an HTMX request) that ends in an error gets an HTML page with the same status; scripts, HTMX and `/api/` paths keep the JSON error.

## Pages

Server-rendered with Jinja2 (`web/templates/`, one module per area under `web/`); HTMX 2 vendored as `static/htmx.min.js` (no CDN, no build step); plain JavaScript only where the browser must act: `static/capture.js`, `static/review.js` and a few lines in `static/app.js`. The interface is in English; a title gets a `lang` attribute from the record's language where it is `ja`, `cs`, `en` or `zh`. Colours follow `prefers-color-scheme`; fonts are the system's. The access rules apply to every page, and HTMX posts are same-origin. A refused HTMX action answers 400, 404 or 409 with a short fragment that the page shows in place; a plain form post is redirected with 303 and an HTMX post with an `HX-Redirect` header.

- **Home** (`/`): links to each page and the number of open observations.
- **Capture** (`/capture`, the phones: a Pixel 8, 412 x 915 CSS px, and a Galaxy A55, 384 x 832). Location and default state are chosen once and remembered in the browser (`localStorage`). A mode switch: *Shelf*, or *One book* (a cover photo, then "Add barcode photo" or "Next book"; the two share a `group_id`). In One book mode a gallery choice of several photos makes each a cover of its own book, except that a pending barcode takes the first. Two ways in: the camera (`<input type=file accept="image/*" capture="environment">`) and the gallery (`accept="image/*" multiple`). Each chosen photo gets its id at once (`crypto.randomUUID()`), shows as a thumbnail, and uploads one at a time with a progress bar; a failed upload is retried up to 5 times, after 2, 4, 8, 16 and 32 seconds, while the page is open (a refused photo, such as a wrong format, is not retried). The status reads *on this phone*, *received*, *reading*, *needs attention* or *ready for review*, polled from `GET /api/captures?ids=` every 10 seconds until final; a finished job with nothing to review reads *needs attention*. A thumbnail lasts only until the server has the photo: then its object URL is released and the picture is dropped from memory, so a long session does not fill the phone's memory. Photos taken with the camera may not be saved to the phone's gallery, so the page says under *Take photo* to keep it open until each photo says *received*, and the browser warns before the page is closed or left while any photo is still waiting, sending or out of retries (a refused photo does not count). The received width and height are shown, with a warning, for a shelf photo only, when the long side is under 3000 pixels (the phase 0 capture test). A cover is shrunk to 2000 pixels for reading anyway and a barcode photo can be any size, so neither is warned about. A photo the server has received shows no thumbnail, as the phone has let go of the file.
- **Review** (`/review`, the iPad, a 9th generation 10.2 in model at 810 x 1080 CSS px portrait, and laptop). The inbox lists open observations grouped by capture, and by `group_id` for one-book captures, newest first, with location and kind. `/review/{id}` shows the tile named by the first word of the record's `where` (else a cover's single tile, else the whole photo; the full photo is a tap away), both readings, the pipeline's note on why it needs a look, the candidates (as `GET /api/observations/{id}/candidates` gives them) with "Use this record" (which fills the title, the authors joined with `"; "` as the records do, the sort key from the catalogue's reading of the title when it has one, and the publisher, year, ISBN, series, language and source), and the book form, filled by `store.default_fields` from this observation and the photos paired with it, the same rule `approve` uses, so the form is the same whichever photo of the book is opened (the pipeline's note is not copied into the book's notes). Photos of the same book, ticked by default, are approved or attached together. The form is filled from the observation and the ticked photos only: ticking or unticking one reloads the page (an HTMX swap of `#review`) with `?without=<ids>` listing the unticked ones, and an unticked photo contributes nothing to the form and stays open when the book is approved. Actions are HTMX posts that go on to the next open observation (else the one before, else the inbox): approve as a new book, attach to an existing book (a search box with live results), dismiss (this observation only), and a separate form to add a book by hand that leaves the observation open. Keys: `j` and `k` move, `Enter` approves and goes to the next (not while a text area has focus; `Ctrl+Enter` approves from anywhere), `e` edits, `x` dismisses, `Esc` leaves a field; a legend is shown. None of these keys act while an input method is composing text (so `Esc` cancels a Japanese conversion and `Enter` commits it, without leaving the field or approving).
- **Books** (`/books`). Live search (debounced) with state, location and tag filters, 100 results at a time with "Show more"; tick several books to move them or change their state (a location that is not one of the listed numbers answers 400 and changes nothing). `/books/new` adds a book by hand, and goes on to a `next` page when the form carries one, but only a plain path on this site: it starts with a single `/`, holds no backslash or control character and no host (anything else is ignored). `/books/{id}` edits one with its version in the form and only the fields that were changed are sent; a conflicting edit answers 409 with a page that shows the stored value beside the person's change for each field they changed, and a button that applies just those changes to the stored version.
- **Locations** (`/locations`). List with book counts, add, and rename in place.
- **Status** (`/status`). Counts of queued, running, done and failed jobs; when the worker last reported (heartbeats only advance while a job runs, so an idle worker looks old); failed jobs with their error and a retry button; the newest 20 photos with the received size, flagged when a shelf photo is under 3000 pixels. The panel refreshes itself.
- **Install.** `/manifest.webmanifest` (name "Home library", short name "Library", start URL `/capture`, `display: standalone`, icons of 192 and 512 pixels), `/icons/icon-{180,192,512}.png` drawn with Pillow when first asked for (the repository tracks no images), and `/sw.js`, a service worker that installs, claims clients and caches nothing. The base template registers it.

## Commands

| Command | Does |
|---|---|
| `hl serve [--data-root PATH] [--port 8765] [--host 127.0.0.1]` | The web app, with environment access settings and local proxy trust. |
| `hl worker [--once]` | The worker. |
| `hl cover`, `hl barcode` | The pipeline for one cover or barcode photo. |
| `hl catalog books [--q] [--state] [--location]` | List books as JSON lines. |
| `hl catalog show <id>` | One book as JSON. |
| `hl catalog edit <id> --version n field=value ...` | Change a book. |
| `hl catalog move <id>... [--location NAME] [--state S]` | Move or change state. |
| `hl catalog locations`, `hl catalog add-location NAME --kind box` | Locations. |
| `hl catalog export --csv|--json` | Every book to standard output. |
| `hl token` | A new agent token (see Access). |
| `hl backup <dest>` | A consistent copy of the data root: `catalog.db` through `VACUUM INTO`, then `captures/` and `work/` copied with `rsync -a`. |

All of them take `--data-root`, defaulting to `$HL_DATA` or `~/home-library/`.

`hl serve` reads comma-separated `HL_USERS` and optional `HL_DEV_USER`. Without `--host`, it uses `127.0.0.1`; if `UVICORN_HOST` names another address, startup is refused until `--host` is supplied explicitly. `HL_DEV_USER` is refused with any host other than the literal `127.0.0.1`, including `localhost` and `::1`. Ports must be between 1 and 65535.

## Running it

See [operations.md](operations.md): systemd user services for `hl serve` and `hl worker` in WSL on battlebox, Tailscale Serve, starting WSL at boot, the nightly backup to Battlebook, and restoring it.
