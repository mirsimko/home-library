# Home library

A catalog for a family's children's books, in Japanese, Czech and English, that knows where every book is: on which shelf or in which box.

Most books are meant to enter the catalog from phone photos read by a vision-capable LLM. An agent harness such as Claude Code or Codex does the reading and the look-ups, and later helps plan seasonal rotations.

## Status

Early. As of 2026-10-05 the requirements are settled and the design is a draft with open decisions. One part is built: a pipeline that reads shelf photos and writes review-ready records to plain files. There is no catalog store yet, and cover and barcode photos are not handled.

## Running the shelf-photo pipeline

```sh
uv run hl run ~/photos/shelf-1.jpg --location "Box 3"
```

This reads the photo twice with two different models, accepts the titles both give alike (ignoring case, spacing and punctuation), looks them up in free library catalogues and writes `records.csv` under `~/home-library/work/`. What it needs and how each stage works is in [docs/pipeline.md](docs/pipeline.md). Tests run with `uv run pytest`, and the lint check with `uv run ruff check .`.

## Contents

- [docs/spec.md](docs/spec.md): the draft spec. It holds the settled requirements, the proposed design, and what has to happen before the design is final.
- [docs/pipeline.md](docs/pipeline.md): the shelf-photo pipeline. How to run it, its stages and file formats, and what was measured.
- [CONTEXT.md](CONTEXT.md): the project's vocabulary.
- `src/home_library/` and `tests/`: the pipeline's code and its tests.
- [docs/research/existing-home-library-tools.md](docs/research/existing-home-library-tools.md): which existing tools could hold the catalog, and what would still have to be built around each.
- [docs/research/book-metadata-sources.md](docs/research/book-metadata-sources.md): which free sources return metadata for children's books in the three languages, tested with real calls.
- [docs/research/shelf-photo-reading-test.md](docs/research/shelf-photo-reading-test.md): how well five vision models read titles from real shelf photos, as whole photos and as tiles.

## How these documents were made

They were drafted with AI assistance (Claude Code) from planning conversations with the family. The code was written by AI agents test-first and reviewed by other models; its history shows each failing test before the change that made it pass. The research notes state their own provenance, and mark what was observed, what is only documented, and what is unverified.

## Licence

None chosen yet.
