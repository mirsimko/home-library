# Shelf photo reading test

> [!NOTE]
> **AI-generated research.** Run and written on 2026-10-05 by a Claude Code session on Claude Opus 5.5 (`claude-opus-5-5`), which also read the photos as one of the five models tested. The other reads were made by subagents: Claude Sonnet 5.5 and a second Claude Opus 5.5 run directly, GPT-6.1 Sol and GPT-6 Luna through Codex, and Space Bunny through OpenCode. The answer key is provisional and no person has checked it against the shelves. No second-opinion review.

## Question

How well do vision-capable LLMs read book titles from ordinary phone photos of the family's shelves, and what does that mean for how books get into the catalog?

This is a first pass on shelf photos only. Cover photos and barcode photos are not tested yet.

## Short answer

- **Shelf photos work for books with clear print on the spine.** Claude Opus 5.5, Claude Sonnet 5.5 and GPT-6.1 Sol each found all 31 clearly printed titles, in Japanese, Czech and English, including vertical Japanese text and Czech diacritics.
- **Cutting each photo into full-resolution tiles helps with small print.** It raised those three models from 5–9 to 9–11 of the 11 small-print titles.
- **Small print on upside-down spines defeats every model**, tiles or not. Those titles became legible only in full-resolution crops turned the right way up.
- **GPT-6 Luna and Space Bunny are not reliable enough to read unattended.** Each missed a quarter to a third of the clearly printed titles and gave wrong titles while marking them fully readable.
- **Many books have no text on the spine at all.** No method reads those from a shelf photo; they need a cover photo.

## Method

**Material.** Four photos of real shelves taken with an Android phone, each 4080x3072. They show thick and thin books in three languages, some shelved upside down, some lying flat, some facing out. The photos are private and are not in this repository.

**Two passes.** Every model got the same written instructions and the same images.

1. **Whole photos.** One image per photo.
2. **Tiles.** Each photo cut into six overlapping tiles of 1560x1740 at full resolution, two rows by three columns, 24 tiles in all.

**Rules given to every model.** Read with its own vision; no OCR software, no cropping or enhancing, no web look-ups. List every physical book, including unreadable ones. Do not complete a title from memory: put only the legible part in the title field and any guess in a separate field. For each entry, say whether it was fully readable, partly readable or unreadable. The tile pass added one rule: put only the title in the title field, and the publisher, imprint or series elsewhere.

**Answer key.** 46 titles, each accepted because several models agreed on it or because it was legible in a zoomed, full-resolution crop read by Claude Opus 5.5. The key is sorted into three classes:

| Class | Meaning | Titles |
|---|---|---|
| A | Large, clear print on a spine or cover | 31 |
| B | Small print, upright or sideways | 11 |
| C | Small print on an upside-down spine, legible only after rotating a full-resolution crop | 4 |

**Scoring.** A key title counts as found when its distinguishing words all appear in one entry's title and accompanying text. The script also counts entries that a model marked fully readable but that match nothing in the key.

## Results

Titles found, out of 46:

| Model | Whole photos | Tiles |
|---|---|---|
| Claude Opus 5.5 | 40 | 43 |
| Claude Sonnet 5.5 | 38 | 41 |
| GPT-6.1 Sol (low effort) | 36 | 40 |
| GPT-6 Luna (medium effort) | 26 | 20 |
| Space Bunny | 23 | 21 |

By class, whole photos then tiles:

| Model | A (31) | B (11) | C (4) |
|---|---|---|---|
| Claude Opus 5.5 | 31, 31 | 9, 11 | 0, 1 |
| Claude Sonnet 5.5 | 31, 31 | 7, 10 | 0, 0 |
| GPT-6.1 Sol | 31, 31 | 5, 9 | 0, 0 |
| GPT-6 Luna | 24, 18 | 2, 2 | 0, 0 |
| Space Bunny | 21, 18 | 2, 3 | 0, 0 |

Entries marked fully readable that match no key title, whole photos then tiles:

| Model | Count | What they were |
|---|---|---|
| Claude Opus 5.5 | 0, 0 | |
| Claude Sonnet 5.5 | 1, 1 | A correctly read series name on a book cut off by the frame. |
| GPT-6.1 Sol | 1, 2 | An imprint taken for a title; two titles on thin spines that the zoomed crops contradict. |
| GPT-6 Luna | 4, 7 | Mostly wrong titles, plus an author and a publisher entered as titles. One of the seven may be a correct short title. |
| Space Bunny | 6, 9 | Wrong titles; in the tile pass, the same garbled series string repeated six times. |

## What the results show

**The three stronger models are dependable on clear print.** They agreed on every class A title in both passes, and Opus and Sonnet gave no wrong title as certain.

**The instruction not to complete titles from memory matters, and the stronger models follow it.** They put partial readings and guesses where the prompt told them to. The weaker models wrote plausible titles that were not on the shelf. Three examples, each marked fully readable:

- *Paleček* read as "PALETTE" (Space Bunny)
- せいかつの図鑑 read as せかいの図鑑 (Luna)
- *Fascinující zvířata* read as "Fascinující příroda" (Luna)

A wrong title that looks valid is the most expensive mistake for a catalog, because nothing flags it for correction.

**Even a strong model invents when the text is too hard.** On a faintly embossed spine and on small upside-down spines, Sol offered titles that the zoomed crops contradict, where Opus and Sonnet reported that they could not read them.

**Spines carry more than the title.** In the whole-photo pass Opus, Sonnet and Sol each listed an imprint as a separate book. The extra rule in the tile pass removed that mistake.

**Resolution is the limit for small print, and orientation for upside-down print.** A 4080-pixel photo is reduced before most models see it; tiles avoid that. Tiles did not help with upside-down spines. In crops turned upright, text as small as a monthly picture-book magazine's issue line was legible.

**Tiles made the weaker models worse.** Luna and Space Bunny both found fewer class A titles from tiles than from whole photos.

## Time and cost

Everything ran on existing subscriptions or a free model, with no paid API calls.

| Model | Whole photos (4 images) | Tiles (24 images) | Notes |
|---|---|---|---|
| Claude Opus 5.5 | not timed | about 13 min, 192k tokens | The whole-photo read was done by the main session. |
| Claude Sonnet 5.5 | about 3 min, 76k tokens | about 8 min, 186k tokens | Token counts are for the whole subagent run. |
| GPT-6.1 Sol | about 2.5 min | about 4 min | Codex reported no token usage. |
| GPT-6 Luna | about 2 min | about 3.5 min | Codex reported no token usage. |
| Space Bunny | 5.5 min, 61k tokens | four parallel runs of 1 to 6 min | OpenCode reported cost 0. One tile run hit its output limit and was repeated. |

## Limits of this test

- **Small sample.** Four photos and 46 key titles.
- **Provisional key.** It rests on model agreement and on one model's zoomed reading. The four class C titles rest on that zoomed reading alone. A person has to confirm it.
- **Not independent for one row.** The session that read the whole photos as Claude Opus 5.5 also built the key.
- **Unequal image sizes in the whole-photo pass.** The Claude models and Space Bunny saw the photos reduced to 2000x1506. Codex reported that Sol and Luna opened the photos in full, which was not checked independently. In the tile pass every model saw the tiles at full size; for Space Bunny that was confirmed byte for byte.
- **Books without spine text are not counted.** The models grouped them as runs with estimated sizes, and the estimates include neighbouring shelves at the photo edges, so no share is given here.

## Consequences for the design

1. Read shelf photos as full-resolution tiles, not as whole photos.
2. Give the model each tile in both orientations, or detect upside-down spines and rotate them. This is untested.
3. Keep the rule against completing titles from memory, and the separate fields for partial readings and guesses.
4. Tell the model that a spine carries a publisher, imprint or series as well as a title.
5. Use Claude Sonnet 5.5 or GPT-6.1 Sol as the reader. Opus reads slightly more at a higher cost. Luna and Space Bunny are ruled out for unattended reading on this evidence.
6. Shelf photos cannot be the only way in. Thin books without spine text need a cover photo.

## Still to test

- Cover photos and barcode photos.
- Tiles in both orientations.
- A box of books photographed from above.
- The key confirmed by a person, then the scores recomputed.
