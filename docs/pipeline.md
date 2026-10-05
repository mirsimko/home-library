# Shelf photo pipeline: stages and file formats

This is the contract between the stages of the shelf-photo reading pipeline. Each stage is a module under `src/home_library/` with a small public interface, and each reads and writes plain UTF-8 files in a work directory. The design reasons are in [spec.md](spec.md) section 2.4 and 2.5 and in the [research notes](research/).

Status: built and tried on the four test photos on 2026-10-05. Cover photos, barcode photos and a catalog store are not part of it yet.

## Rules that hold everywhere

- **No private data in this repository.** Photos, tiles, model answers and book lists live in a work directory outside any git checkout. Tests use generated images and invented titles, or public catalogue records of well-known books.
- **No traditional OCR.** Only a vision LLM reads a photo.
- **One photo per model session**, started fresh, with about 5 MB of images. Few requests at once: the home uplink is about 10 Mbit/s.
- **A read never sees another read.** A reader gets the tiles and the prompt, nothing else.
- **Nothing is lost silently.** An entry that cannot be parsed, an answer that was cut off, a title only one read gave and a look-up that failed all reach the review output with a reason.

## Running it

The command is `hl`. From a checkout, run it as `uv run hl`.

```sh
uv run hl run ~/photos/shelf-1.jpg ~/photos/shelf-2.jpg --location "Box 3"
```

This cuts the tiles, reads each photo twice, merges the reads, looks the titles up, picks catalogue records and writes `records.csv` and `records.json` into each photo's work directory. It prints one line per photo and exits with 1 if any photo failed.

- **Needs:** [uv](https://docs.astral.sh/uv/); the `codex` command, logged in, for GPT-6.1 Sol; the `pi` command with access to Muse Spark 1.3 for the second read; and `yaz-client` (Ubuntu package `yaz`) for Czech look-ups. Without `yaz-client` Czech titles are simply not looked up.
- **Starting again is safe.** A read that is already stored is not repeated, and a look-up that was answered is not asked again. If a run fails half way, run the same command again. A stored read is reused only for the tiles it was made from, and a stored pick only for the readings and candidates it was made for; a pick step that failed is made again. `--force` starts a photo from nothing, and so does a changed photo file: every file made from the old photo is removed first.
- **One work directory per file name.** Two different photos with the same file name cannot both be kept: the later one replaces the earlier one's results, and two of them in one run are refused.
- **`--second-reader codex-exec`** makes the second read another Sol session in place of Muse Spark.
- **What runs at once.** The two reads of one photo run at the same time. Photos are read one after another. The look-ups and the pick of a photo run in the background while the next photo is read, because one NDL title search takes 10 to 15 seconds.
- **From an agent harness,** start a run of several photos as a background job: a photo takes about two minutes, and a harness may cap a single command at ten.
- Each stage is also a command of its own, for repeating one step: `hl tiles`, `hl read`, `hl merge`, `hl lookup`, `hl pick`, `hl export`. Each takes the photo and the same `--work-root`. `hl gather <read-id>` prints one read's answers for all photos in the shape the scoring tools of the 2026-10-05 tests take.

## Measured on 2026-10-05

One run of `hl run` over the four test photos (4080x3072), from nothing, on the home uplink of about 10 Mbit/s. The answer key of 46 titles is provisional; see the [shelf photo reading test](research/shelf-photo-reading-test.md).

| Measure | Result |
|---|---|
| Time for all four photos, every stage | 458 seconds, about 115 seconds per photo |
| Tile images per photo | 12, together 4.4 to 6.2 MB |
| GPT-6.1 Sol read | 77 to 145 seconds per photo; 43 of 46 key titles |
| Muse Spark 1.3 read | 56 to 85 seconds per photo; 44 of 46 key titles |
| Titles both reads gave alike (accepted) | 28, all of them in the key |
| Titles sent to review | 29: 22 partly read, 7 given by one read only |
| Reads that used a tool; answers with a parse error | 0; 0 |
| Catalogue picks for 32 titles with candidates | 16 matched, 8 ambiguous, 8 none |

"Alike" means equal match keys, as stage 4 defines them: case, spacing and punctuation are ignored, every letter and digit counts.

The run was made before the review of 2026-10-05 changed some rules: split pairs now compare whole words, an incomplete event stream fails a read, and what a read lost gets rows of its own. A second run after those changes is recorded below the table if its numbers differ.

What the run and the trials before it showed:

- **One attached call is faster than an agent session.** The same Sol read took 151 to 199 seconds when Codex opened the twelve images one by one inside a session.
- **Two reads at once cost nothing on this uplink.** Both reads of the densest photo together took 133 seconds, against about 190 in sequence.
- **NDL title searches are slow,** 10 to 15 seconds each when NDL has not answered the same search recently. Its ISBN look-up and the other sources answer in under two seconds.
- **Pi must run with standard input closed.** With an image attached and standard input left open it produced nothing for four minutes.
- **Models divide a spine differently.** One puts a series name into the title where the other puts it into the other text. In a trial run on one photo this made eight rows out of four books. The merge now pairs such readings as `split`, so the book is one review row. The run in the table had no such pair.
- **A model renumbers what it is given.** The first pick prompt labelled books with their item numbers; the model numbered its answers from the start, and its verdicts landed on the wrong books. The check on candidate ids kept every wrong match out, but most picks were lost. The prompt now numbers books from 1 and the answer must echo each title.

## Work directory

One directory per photo, named after the photo's file stem:

```text
<work-root>/<photo-stem>/
  tiles.json                  manifest written by the tile cutter
  tiles/                      tile images only, nothing else, ever
    r1c1-r0.jpg  r1c1-r180.jpg  ...
  reads/<read-id>/            one directory per read, for example a-sol, b-spark
    prompt.txt                the prompt as sent
    raw.txt                   the model's answer, untouched
    events.jsonl              the harness's event stream, where it gives one
    run.json                  backend, model, command, start time, seconds, return code
    read.json                 the parsed read
  merged.json
  lookup/
    candidates.json
    picks.raw.txt             the pick model's answer, untouched
    picks.json
    cache/                    raw catalogue responses, keyed by request
  records.json
  records.csv
```

The default work root is `~/home-library/work/`. Every stage refuses to write inside a git checkout, so a clone of this repository must not itself be `~/home-library`; pass `--work-root` in that case.

## Stage 1: tiles (`home_library.tiles`)

Cuts a photo into overlapping tiles at full resolution and saves each tile twice: as photographed (`-r0`) and turned by 180 degrees (`-r180`), so that print on upside-down books can be read upright.

- The photo's EXIF orientation is applied before cutting. Tiles are saved without metadata.
- The layout is computed from the image size and four numbers: tile width 1560, tile height 2000, minimum horizontal overlap 300, minimum vertical overlap 900. Along each axis the tile is no larger than the image, the tile count is the smallest that gives at least the minimum overlap between neighbours, and the tile starts are spread evenly from 0 to `size - tile` and rounded to whole pixels.
- For a 4080x3072 photo this gives columns at x = 0, 1260, 2520 and rows at y = 0, 1072: six tiles, twelve images. Any piece of text up to 928 pixels tall lies whole in at least one tile. The layout tested on 2026-10-05 overlapped by only 408 pixels and cut long spine titles in two.
- No tile side exceeds 2000 pixels with these numbers, because the harnesses shrink larger images. Pi and OpenCode do so above 2000 pixels. For Codex this was measured on 2026-10-05 with generated images of small digits: 7 to 9 pixel digits were read almost perfectly on 1560x1740 and 1560x2000 images, about half of the 7 pixel digits were lost on a 1360x3072 image, and all of them on a 4080x3072 image. Full-height strips are therefore not an option.
- For an image smaller than a tile, the layout records the reduced tile size.
- A tile size no larger than its minimum overlap is refused.
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

Two backends:

| Backend | Model | How it is called |
|---|---|---|
| `codex-exec` | GPT-6.1 Sol, low effort | One `codex exec` call with every tile attached by `--image`, the prompt on standard input, a read-only sandbox, no saved session and the user's Codex configuration ignored. |
| `pi` | Muse Spark 1.3 | One `pi -p` call with every tile attached, and with tools, sessions, context files, skills, prompt templates and extensions all switched off. |

- The reader runs in `tiles/` and first checks that the directory holds exactly the files the manifest lists. It refuses to run otherwise.
- **A read must use no tools.** Pi runs with tools switched off. Codex cannot switch them off, so the reader asks for its event stream (`--json`), keeps it as `events.jsonl`, and rejects the read unless the stream is complete and shows nothing but the model's reasoning and its answer. A line that is not a JSON object, a missing `turn.completed` event, or a `turn.failed` or `error` event rejects the read as well, because a tool call could hide behind any of them. A rejected read leaves no `read.json`.
- A read id is a plain name of letters, digits, dots, dashes and underscores. Anything else is refused, so a read can only be written inside the photo's work directory.
- A read that fails, times out, returns nothing or returns an answer with no `books` list is an error. `raw.txt` and `run.json` are still written, so the failure can be inspected. An empty `books` list is a valid read of an empty shelf.

`run.json`:

```json
{
  "read_id": "a-sol",
  "backend": "codex-exec",
  "model": "gpt-6.1-sol",
  "command": ["codex", "exec", "..."],
  "started": "2026-10-05T19:40:01+09:00",
  "seconds": 113.2,
  "returncode": 0,
  "tool_calls": [],
  "usage": {"input_tokens": 58000, "output_tokens": 3900}
}
```

`command` leaves the prompt out; it is in `prompt.txt`. `tool_calls` lists the type of every event that was not reasoning or an answer. `usage` is what the harness reported, or null.

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
- An empty place in the list, as two commas in a row leave, is an error too: an entry was lost there.
- `errors` lists each piece of the answer that could not be decoded: its position in the list counted from 1, its character offset in the raw text, the reason, and the raw text itself. Every element of the list counts towards the position, decodable or not. An entry the answer was cut off in is listed too.
- An answer with no `books` list gives one error with position 0 that holds the whole answer.
- `complete` is false when anything was lost: an entry in `errors`, a cut-off answer, or no `books` list at all.
- The reader adds `read_id` when it stores the read, sets `file` to the photo's name from the manifest, whatever name the model echoed, and adds `tiles_sha256`, the hash of the `tiles.json` it read from. The pipeline reuses a stored read only when that hash is the current one.

## Stage 4: merge (`home_library.merge`)

Compares two reads of the same photo that could not see each other.

- The **match key** of a title: the signs ™, ®, © and ℠ removed, then Unicode NFKC, then case folding, then every character that is not a letter or a digit removed. Diacritics, kana and digits stay significant.
- Two reads with the same read id are refused: one read agreeing with itself is not two reads.
- An entry is **eligible** when `readable` is `yes`, its match key is not empty and `inferred` is empty.
- Eligible entries with equal match keys are paired one to one across the two reads. Two copies in one read and one in the other give one pair and one left over. Each pair is **accepted**.
- Left-over entries that have a title are then paired one to one where their match keys are at least 0.9 similar (`difflib.SequenceMatcher` ratio), best pairs first. Such a pair goes to review as `near` when both entries are eligible, and as `partial` otherwise.
- Entries still left over are paired one to one where the two reads hold the same words but divide them differently between `title` and `other_text`, as happens when one model takes a series name for part of the title. Words are what white space separates. Two entries pair when every word of each entry's title equals, by match key, a word of the other entry's title or other text. They also pair when title and other text together have the same match key in both, which covers a number that one model wrote onto the title. Such a pair goes to review as `split` when both entries are eligible, and as `partial` otherwise.
- Every other entry with a title goes to review alone: `solo` when eligible, `partial` otherwise.
- Entries without a title are not compared. They are listed under `unreadable`. A title that is only white space counts as no title. A title of punctuation only has an empty match key: it is never paired and goes to review alone as `partial`.

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
  "incomplete": [],
  "parse_errors": [{"read_id": "a-sol", "position": 3, "offset": 812, "reason": "...", "raw": "..."}]
}
```

- `status` is `accepted` or `review`. `reason` is `agreed`, `near`, `split`, `solo` or `partial`.
- `title` and `language` come from the first read that has the entry.
- `exact` is true when the two titles are equal after Unicode NFC and trimming of outer white space only. It is false for an item with one reading.
- `items` keeps the order of the first read, followed by entries only the second read gave.
- `incomplete` lists the reads whose `complete` is false.
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

- Every free title search is exact on characters, so a title is searched in a short ladder: title with author when an author is known, then the title alone, then a shortened title. The ladder stops at the first step that returns something, and makes at most three requests per source for one book. A shelf photo gives no separate author and no ISBN, so today only the last two steps run; the author and ISBN steps are for cover and barcode photos.
- The language is matched without regard to case and surrounding white space. A language with no source is not looked up, and the record says so.
- Requests to one HTTP source are paced: NDL caps concurrent requests, and Open Library allows one request per second. The whole run makes its look-ups one after another.
- A source that fails or is not installed never stops the run. Its status is recorded, any failure ends that source's ladder for the book, and a source that could not be reached or was rate limited is not asked again for the rest of the photo: its later queries are recorded with the step `skipped`.
- The answer of each step, including "no match", is cached in `lookup/cache/`, so a repeated run makes no request. A failure is never cached.

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

Every field is present and none is null. Text fields are strings and may be empty; `authors` and `subjects` are lists of strings. `id` is `<source>:<source_id>` and is unique among one book's candidates.

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
- A query's `status` is `ok`, `no_match`, `unavailable` (not installed, not reachable or timed out), `rate_limited` or `error`.
- At most ten candidates are kept per source for one book.

## Stage 6: pick and records (`home_library.pick`, `home_library.records`)

The pick step gives a model the reading and its candidates as text and asks which candidate, if any, is the book. The prompt numbers the books from 1 and the model must echo each book's title. Code rejects an answer that echoes another title, and an answer that names a candidate that was not fetched for that book.

`picks.json`:

```json
{
  "file": "shelf-1.jpg",
  "picks": [
    {"item": 0, "verdict": "match", "candidate_id": "ndl:000009209109", "reason": "Same title and publisher."}
  ],
  "made_for": "<hash of the pick prompt>",
  "failed": false
}
```

- There is one pick for each book in `candidates.json` that has at least one candidate, in the same order.
- `verdict` is `match`, `ambiguous` or `none`. `candidate_id` is set only for `match` and is null otherwise.
- `made_for` is a hash of everything the model was shown, and `failed` says whether the model call failed. The pipeline uses a stored pick only when `made_for` fits the current readings and candidates, and makes a failed pick again on the next run.
- A `match` that names a candidate not fetched for that book becomes `none`, with the rejection as its reason. So does a missing or unusable answer for a book.
- A pick that fails as a whole (the model call fails, or its answer cannot be read) gives `none` for every book, with the failure as the reason. It never stops the run.
- Unlike a read, the pick is not checked for tool use: it sees only text the two reads already produced.
- When no book has a candidate, no model is called.

`records.json` and `records.csv` hold one row per entry of `merged.json` `items`, followed by the unreadable entries of the first read. The columns follow spec section 2.1 where this stage can fill them, then the provenance:

`title, sort_key, author, illustrator, publisher, year, language, isbn, series, age_from, age_to, tags, state, location, cover_photo, source, source_id, needs_review, notes, photo, read_status, other_reading, catalogue_title, other_text, where, read_ids, pick_verdict, candidate_count`

- `needs_review` is always true: no person has seen the record yet.
- `title` is the reading from the photo, never a catalogue title. `language` is the read's too.
- `other_reading` is the second reading's title where an item has two readings whose titles differ. Otherwise it is empty.
- The catalogue fields are filled only from a candidate picked as `match`: `catalogue_title`, `author` (the candidate's authors joined with `; `), `publisher`, `year`, `isbn`, `series`, `source`, `source_id`, and `sort_key` (the candidate's title reading). Without a match, or without a title reading, `sort_key` is the title.
- `age_from` and `age_to` come from a matched candidate's age note, and only where it states an age in years, as in `od 3 let`, `5-8 let`, `od 3 do 6 let` or `Ages 4-8`. A grade, a reading level or a year in the note is not taken for an age.
- `illustrator`, `tags`, `state` and `cover_photo` are empty in this version. `location` is filled only when it was given for the photo.
- `read_status` is `agreed`, `near`, `split`, `solo`, `partial`, `unreadable`, `unparsed` or `incomplete`.
- After the items and the unreadable entries come the rows for what a read lost. Each entry that could not be parsed is an `unparsed` row with its raw text in `other_text`. A read whose answer was cut off, and whose loss is not already listed entry by entry, is an `incomplete` row.
- `other_text` and `where` come from the item's first reading. `read_ids` joins the readings' read ids with `; `.
- `notes` says in plain words why the row needs a look: which read gave a solo title, that two reads divide the words differently, a guess the model put in `inferred`, a catalogue that could not be asked or does not cover the language, why no catalogue record was matched, an ambiguous match with its reason, a catalogue age or audience note.
- `records.json` is a list of objects with every column. `needs_review` is a boolean and `candidate_count` an integer there.
- `records.csv` is UTF-8 with a byte-order mark, so that a spreadsheet program opens Japanese and Czech text correctly. `needs_review` is written as `true`.
- In the CSV, a cell that starts with `=`, `+`, `-` or `@` is prefixed with a single quote, so a spreadsheet does not run it as a formula.
