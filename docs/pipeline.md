# Shelf photo pipeline: stages and file formats

This is the contract between the stages of the shelf-photo reading pipeline. Each stage is a module under `src/home_library/` with a small public interface, and each reads and writes plain UTF-8 files in a work directory. The design reasons are in [spec.md](spec.md) section 2.4 and 2.5 and in the [research notes](research/).

Status: being built. This file is updated as the stages land.

## Rules that hold everywhere

- **No private data in this repository.** Photos, tiles, model answers and book lists live in a work directory outside any git checkout. Tests use generated images and invented titles, or public catalogue records of well-known books.
- **No traditional OCR.** Only a vision LLM reads a photo.
- **One photo per model session**, started fresh, with about 5 MB of images. Few requests at once: the home uplink is about 10 Mbit/s.
- **A read never sees another read.** A reader gets the tiles and the prompt, nothing else.
- **Nothing is lost silently.** An entry that cannot be parsed, a title only one read gave and a look-up that failed all reach the review output with a reason.

## Work directory

One directory per photo, named after the photo's file stem:

```text
<work-root>/<photo-stem>/
  tiles.json                  manifest written by the tile cutter
  tiles/                      tile images only, nothing else, ever
    r1c1-r0.jpg  r1c1-r180.jpg  ...
  reads/<read-id>/            one directory per read, for example a-sol, b-spark
    raw.txt                   the model's answer, untouched
    run.json                  backend, model, command, start time, seconds, return code
    read.json                 the parsed read
  merged.json
  lookup/
    candidates.json
    picks.json
    cache/                    raw catalogue responses, keyed by request
  records.json
  records.csv
```

The default work root is `~/home-library/work/`.

## Stage 1: tiles (`home_library.tiles`)

Cuts a photo into overlapping tiles at full resolution and saves each tile twice: as photographed (`-r0`) and turned by 180 degrees (`-r180`), so that print on upside-down books can be read upright.

- The photo's EXIF orientation is applied before cutting. Tiles are saved without metadata.
- The layout is computed from the image size and four numbers: tile width 1560, tile height 2000, minimum horizontal overlap 300, minimum vertical overlap 900. Along each axis the tile is no larger than the image, the tile count is the smallest that gives at least the minimum overlap between neighbours, and the tile starts are spread evenly from 0 to `size - tile` and rounded to whole pixels.
- For a 4080x3072 photo this gives columns at x = 0, 1260, 2520 and rows at y = 0, 1072: six tiles, twelve images. Any piece of text up to 928 pixels tall lies whole in at least one tile. The layout tested on 2026-10-05 overlapped by only 408 pixels and cut long spine titles in two.
- No tile side exceeds 2000 pixels, because some harnesses shrink larger images.
- Tiles are JPEG, quality 88 by default.
- File names are `r<row>c<col>-r<rotation>.jpg`, rows and columns counted from 1, top to bottom and left to right.

`tiles.json`:

```json
{
  "photo": "shelf-1.jpg",
  "sha256": "<hash of the photo file>",
  "width": 4080,
  "height": 3072,
  "layout": {"tile_width": 1560, "tile_height": 2000, "columns": [0, 1260, 2520], "rows": [0, 1072]},
  "quality": 88,
  "tiles": [
    {"file": "r1c1-r0.jpg", "row": 1, "column": 1, "rotation": 0, "box": [0, 0, 1560, 2000], "bytes": 412345}
  ],
  "total_bytes": 4812345
}
```

`box` is `[left, top, right, bottom]` in the upright photo's pixels, for both rotations of a tile.

## Stage 2: read (`home_library.reader`)

Runs one model session over the tiles of one photo and stores the answer. The prompt names every tile file and tells the model not to stop and ask questions.

A read entry has nine fields. The scoring tools of the 2026-10-05 tests depend on these names, so they do not change:

| Field | Values |
|---|---|
| `n` | Running number within the photo. |
| `where` | Tile name and position, so a person can find the book. |
| `visible` | `spine`, `front cover`, `back cover` or `edge`. |
| `title` | The title as printed, in its original script, or empty. Only what is legible. |
| `other_text` | Everything else legible: author, publisher, series, issue. |
| `language` | `ja`, `cs`, `en`, `zh` or `unknown`. |
| `readable` | `yes`, `partial` or `no`. |
| `confidence` | `high`, `medium` or `low`. |
| `inferred` | A guess where text was not legible, or empty. |

The model answers with `{"file": "<photo>", "books": [<entries>]}`.

## Stage 3: parse (`home_library.parse`)

Turns a raw answer into a read, entry by entry, so that one malformed entry does not lose a photo. It never repairs or rewrites what the model wrote.

`read.json`:

```json
{
  "file": "shelf-1.jpg",
  "books": [
    {"n": 1, "where": "r1c1-r0.jpg, left", "visible": "spine", "title": "Zelený drak", "other_text": "",
     "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}
  ],
  "errors": [
    {"position": 3, "offset": 812, "reason": "Expecting ',' delimiter", "raw": "{\"n\": 3, ..."}
  ],
  "complete": true
}
```

- `books` holds every entry that decoded as a JSON object, in the model's order. All nine fields are present. `n` is an integer; the others are strings. A missing field is the empty string, and a missing or unusable `n` is the entry's position counted from 1.
- `readable` is always `yes`, `partial` or `no`. Any other value becomes `partial`, so the entry goes to review.
- `errors` lists each piece of the answer that could not be decoded: its position in the list counted from 1, its character offset in the raw text, the reason, and the raw text itself.
- `complete` is false when anything was lost: an entry in `errors`, a cut-off answer, or no `books` list at all.
- The reader adds `read_id` when it stores the read.

## Stage 4: merge (`home_library.merge`)

Compares two reads of the same photo that could not see each other.

- The **match key** of a title: Unicode NFKC, then case folding, then every character that is not a letter or a digit removed. Diacritics, kana and digits stay significant.
- An entry is **eligible** when `readable` is `yes`, its match key is not empty and `inferred` is empty.
- Eligible entries with equal match keys are paired one to one across the two reads. Two copies in one read and one in the other give one pair and one left over. Each pair is **accepted**.
- Left-over entries that have a title are then paired one to one where their match keys are at least 0.9 similar (`difflib.SequenceMatcher` ratio), best pairs first. Such a pair goes to review as `near` when both entries are eligible, and as `partial` otherwise.
- Every other entry with a title goes to review alone: `solo` when eligible, `partial` otherwise.
- Entries without a title are not compared. They are listed under `unreadable`.

`merged.json`:

```json
{
  "file": "shelf-1.jpg",
  "reads": ["a-sol", "b-spark"],
  "items": [
    {"status": "accepted", "reason": "agreed", "title": "Zelený drak", "language": "cs", "exact": true,
     "readings": [{"read_id": "a-sol", "n": 1, "...": "the nine fields"}, {"read_id": "b-spark", "n": 4, "...": "the nine fields"}]},
    {"status": "review", "reason": "solo", "title": "The Blue Kite", "language": "en", "exact": false,
     "readings": [{"read_id": "b-spark", "n": 7, "...": "the nine fields"}]}
  ],
  "unreadable": [{"read_id": "a-sol", "n": 9, "...": "the nine fields"}],
  "parse_errors": [{"read_id": "a-sol", "position": 3, "offset": 812, "reason": "...", "raw": "..."}]
}
```

- `status` is `accepted` or `review`. `reason` is `agreed`, `near`, `solo` or `partial`.
- `title` and `language` come from the first read that has the entry.
- `exact` is true when the two titles are equal after Unicode NFC and trimming of outer white space only. It is false for an item with one reading.
- `items` keeps the order of the first read, followed by entries only the second read gave.
- An accepted title is an agreed reading. It does not clear human review of the record.

## Stage 5: look-up (`home_library.lookup`)

Fetches candidate catalogue records for a title, from the sources tested in [book-metadata-sources.md](research/book-metadata-sources.md). A separate pick step then chooses among them.

| Source | Key | Used for |
|---|---|---|
| NDL Search (`ndl`) | none | Japanese: by ISBN, or by title and creator, always with `dpid=iss-ndl-opac` |
| openBD (`openbd`) | none | Japanese: by ISBN only |
| NK ČR over Z39.50 (`nkcr`) | none | Czech: by ISBN, or by title and author, through the `yaz-client` program |
| Open Library (`openlibrary`) | none | English: by ISBN, or by title and author |
| Library of Congress SRU (`loc`) | none | English: by ISBN, or by title and author |

- Every free title search is exact on characters, so a title is searched in a short ladder: title with author when an author is known, then the title alone, then a shortened title. The ladder stops at the first step that returns something, and makes at most three requests per source for one book.
- Requests to one source run one at a time and are paced: NDL caps concurrent requests, and Open Library allows one request per second.
- A source that fails or is not installed never stops the run. Its status is recorded.
- Raw responses are cached in `lookup/cache/`, so a repeated run makes no request.

A candidate:

```json
{
  "id": "ndl:000009209109",
  "source": "ndl",
  "source_id": "000009209109",
  "url": "https://ndlsearch.ndl.go.jp/books/R100000002-I000009209109",
  "title": "だるまさんが",
  "title_reading": "ダルマサン ガ",
  "authors": ["加岳井, 広, 1955-2009"],
  "publisher": "ブロンズ新社",
  "year": "2008",
  "isbn": "9784893094315",
  "series": "",
  "language": "ja",
  "audience": "",
  "age_note": "",
  "subjects": ["児童図書"],
  "summary": ""
}
```

Every field is present. Text fields are strings and may be empty; `authors` and `subjects` are lists of strings. `id` is `<source>:<source_id>` and is unique within a file.

`candidates.json`:

```json
{
  "file": "shelf-1.jpg",
  "books": [
    {
      "item": 0,
      "title": "だるまさんが",
      "language": "ja",
      "queries": [
        {"source": "ndl", "step": "title", "status": "ok", "count": 6}
      ],
      "candidates": []
    }
  ]
}
```

- `item` is the index of the entry in `merged.json` `items`.
- A query's `status` is `ok`, `no_match`, `unavailable`, `rate_limited` or `error`.
- At most ten candidates are kept per source for one book.

## Stage 6: pick and records (`home_library.pick`, `home_library.records`)

The pick step gives a model the reading and its candidates as text and asks which candidate, if any, is the book. Code rejects an answer that names a candidate that was not fetched.

`picks.json`:

```json
{
  "file": "shelf-1.jpg",
  "picks": [
    {"item": 0, "verdict": "match", "candidate_id": "ndl:000009209109", "reason": "Same title and publisher."}
  ]
}
```

`verdict` is `match`, `ambiguous` or `none`. `candidate_id` is set only for `match`.

`records.json` and `records.csv` hold one row per entry of `merged.json` `items`, followed by the unreadable entries of the first read. The columns follow spec section 2.1 where this stage can fill them, then the provenance:

`title, sort_key, author, illustrator, publisher, year, language, isbn, series, age_from, age_to, tags, state, location, cover_photo, source, source_id, needs_review, notes, photo, read_status, read_title, other_text, where, read_ids, pick_verdict, candidate_count`

- `needs_review` is always true: no person has seen the record yet.
- `title` is the reading from the photo, never a catalogue title. Catalogue fields are filled only from a candidate picked as `match`.
- `read_status` is `agreed`, `near`, `solo`, `partial` or `unreadable`.
- `state` is empty. `location` is filled only when it was given for the photo.
- In the CSV, a cell that starts with `=`, `+`, `-` or `@` is prefixed with a single quote, so a spreadsheet does not run it as a formula.
