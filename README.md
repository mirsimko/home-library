# Home library

A catalog for a family's children's books, in Japanese, Czech and English, that knows where every book is: on which shelf or in which box.

Most books are meant to enter the catalog from phone photos read by a vision-capable LLM. An agent harness such as Claude Code or Codex does the reading and the look-ups, and later helps plan seasonal rotations.

## Status

Early. As of 2026-10-13 the requirements are settled and the design is a draft with open decisions. Built so far:

- A pipeline that reads shelf, cover and barcode photos and writes review-ready records to plain files.
- A small web app on top of it: the phones (a Pixel 8 and a Galaxy A55) send photos, a worker runs the pipeline on each, and the iPad (9th generation, 10.2 in, 810 x 1080 CSS px) or a laptop reviews the results into a SQLite catalog. It is not yet tried on the real phones and iPad; the checks it rests on are listed in [app-spikes.md](docs/research/app-spikes.md).

## Running the shelf-photo pipeline

```sh
uv run hl run ~/photos/shelf-1.jpg --location "Box 3"
```

This reads the photo twice with two different models, accepts the titles both give alike (ignoring case, spacing and punctuation), looks them up in free library catalogues and writes `records.csv` under `~/home-library/work/`. What it needs and how each stage works is in [docs/pipeline.md](docs/pipeline.md). Tests run with `uv run pytest`, and the lint check with `uv run ruff check .`.

## Contents

- [docs/spec.md](docs/spec.md): the draft spec. It holds the settled requirements, the proposed design, and what has to happen before the design is final.
- [docs/pipeline.md](docs/pipeline.md): the shelf-photo pipeline. How to run it, its stages and file formats, and what was measured.
- [docs/app.md](docs/app.md): the capture and review app. Its store, worker, access rules, HTTP API, pages and commands.
- [docs/operations.md](docs/operations.md): how the app runs at home, is backed up and restored.
- [docs/harness.md](docs/harness.md): how Claude Code or Codex read and write the catalog.
- [docs/plans/](docs/plans/): the implementation plan of the app.
- [CONTEXT.md](CONTEXT.md): the project's vocabulary.
- `src/home_library/` and `tests/`: the code of the pipeline and the app, and their tests. `deploy/systemd/`: the services that run the app.
- [docs/research/existing-home-library-tools.md](docs/research/existing-home-library-tools.md): which existing tools could hold the catalog, and what would still have to be built around each.
- [docs/research/book-metadata-sources.md](docs/research/book-metadata-sources.md): which free sources return metadata for children's books in the three languages, tested with real calls.
- [docs/research/shelf-photo-reading-test.md](docs/research/shelf-photo-reading-test.md): how well five vision models read titles from real shelf photos, as whole photos and as tiles.
- [docs/research/app-framework.md](docs/research/app-framework.md): which way to build the app for two Android phones (a Pixel 8 and a Galaxy A55) and an iPad (9th generation, 10.2 in) without a Mac.
- [docs/research/app-spikes.md](docs/research/app-spikes.md): the checks the app rests on, and what was found on the home machine.

## How these documents were made

They were drafted with AI assistance (Claude Code) from planning conversations with the family. The code was written by AI agents test-first and reviewed by other models; its history shows each failing test before the change that made it pass. The research notes state their own provenance, and mark what was observed, what is only documented, and what is unverified.

## Licence

None chosen yet.
