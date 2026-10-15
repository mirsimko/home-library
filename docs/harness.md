# Catalog access for Claude Code and Codex

Use `hl catalog` to read and change the catalog. From this checkout, prefix commands with `uv run`.
Set `HL_DATA` to the private data directory, or pass `--data-root PATH` before or after the command
(including after `catalog books`). The default is `~/home-library`. The directory must be outside
any git checkout. Keep photos, catalog output and tokens outside the repository too.

**Agents never write `catalog.db` directly.** Use the CLI or the authenticated HTTP API: both write
through `home_library.store`, which checks locations, book states and editing versions. Captures and
observations are evidence; only an approved book represents a physical copy.

## Commands

| Command | Result |
|---|---|
| `hl catalog books --q TEXT --state Active --location NAME` | Matching books as JSON lines; each filter is optional. All matching pages are included. |
| `hl catalog show ID` | One book as JSON, including its editing version and location id. |
| `hl catalog edit ID --version N 'author=Ada Birch' age_from=4 'notes='` | The updated book as JSON. Empty values clear optional fields; ages are integers. Read the current version before editing. |
| `hl catalog move ID... --location NAME --state Stored` | Updated books as JSON lines. Either location or state may be omitted; the batch succeeds together. |
| `hl catalog locations` | Locations as JSON lines, with their ids and names. |
| `hl catalog add-location NAME --kind box` | The new location as JSON; kind is `box` or `shelf`. |
| `hl catalog export --json` | Every book's flat export fields as a JSON list. |
| `hl catalog export --csv` | Formula-safe CSV in UTF-8 with a BOM. Redirect it to a private file. |

CLI book writes are attributed to `agent`. Errors print one line to standard error and exit 1.
A version conflict means read the book again and reconcile the requested change with the new version.
`location_id` edits take an integer; prefer `move --location NAME`. `needs_review` takes `true` or
`false`; an empty `cover_capture_id` clears the cover. Required title, state and location cannot be cleared.

## HTTP access

When the web app is running, an agent can use its HTTP API instead. Provision a token once:

```sh
export HL_TOKEN="$(hl token)"
```

`hl token` prints a new secret once and stores only its hash in `agent-token` with mode `0600`.
Running it again revokes the old token. Supply the secret to the agent's environment; the hash is
not a usable bearer token. Set `HL_URL` to the app's local address (`http://127.0.0.1:8765`) or its
Tailscale HTTPS address. For example:

```sh
curl --fail-with-body --get "$HL_URL/api/books" \
  -H "Authorization: Bearer $HL_TOKEN" --data-urlencode 'q=The Copper Comet'
curl --fail-with-body -X PATCH "$HL_URL/api/books/17" \
  -H "Authorization: Bearer $HL_TOKEN" -H 'Content-Type: application/json' \
  --data '{"version":1,"changes":{"notes":"Checked the cover"}}'
```

Read with `GET /api/books`, `GET /api/books/ID` and `GET /api/locations`. Add with
`POST /api/books`; edit with `PATCH /api/books/ID` and its `version` and `changes`; move with
`POST /api/books/move` and `{"book_ids":[11,12],"location_id":3,"state":"Stored"}`.
The authenticated identity is `agent`. A 409 means reconcile a version conflict; 400 and 404 explain
invalid input or a missing row. The full API and observation approval workflow are in [app.md](app.md#http-api).

## Example: is a book owned?

These examples use invented titles and ids. Search without a state filter so stored copies are included:

```sh
hl catalog books --q 'The Copper Comet'
hl catalog show 17
hl catalog locations
```

Suppose the search returns id 17, and `show` says `Stored` at location id 3. Match its author or ISBN
to the requested edition and use `locations` to resolve id 3 to its box name. Report that the family
owns that copy and where it is. `Active`, `Stored` and `Retired` copies are still at home; `Gone`
keeps the history of a copy that left. No result means no matching copy is recorded, not proof that
there is no unrecorded book in the house.

## Example: move a season's books to Stored

Suppose the user has selected the winter books and is moving them into a winter box:

```sh
hl catalog books --q Winter --state Active
hl catalog locations
```

Read the returned books and select the intended physical copies; here they are ids 11 and 12.
If `Winter Box` is absent, create it, then record both the location and the state:

```sh
hl catalog add-location 'Winter Box' --kind box
hl catalog move 11 12 --location 'Winter Box' --state Stored
hl catalog show 11
hl catalog show 12
```

Finish when both books say `Stored` and their location id names `Winter Box`. A catalog move records
the physical move; it does not establish that somebody has moved the books.
