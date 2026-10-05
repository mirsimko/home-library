# Home library: draft spec

Version 0, 2026-10-05. Nothing described here is built.

Part 1 holds the requirements, which are settled. Part 2 holds the design, where every point carries one of three marks:

- **Settled**: decided by the family.
- **Proposed**: a recommendation that still needs the family's confirmation or a test.
- **Open**: no recommendation yet.

Terms in bold capitals such as Active and Stored are defined in [CONTEXT.md](../CONTEXT.md).

## 1. Requirements

### 1.1 Problem

A family in a small apartment owns more children's books than its shelves hold: a few hundred picture books in Japanese, Czech and English, with about seven boxes that do not fit on the shelves. The children are of preschool age, so books rotate with the seasons and are outgrown year by year. Nobody knows exactly which books the family owns, or which box a given book is in.

### 1.2 Goal

A working system in which every children's book in the home is cataloged together with where it is. Most books enter the catalog from phone photos read by a vision-capable LLM. The rest are typed in by hand.

The system is done when the whole collection, shelves and boxes, is in the catalog with locations.

### 1.3 Users and devices

Two adults. They take photos with Android phones, and do typing and correction on an iPad with a keyboard or on a laptop.

### 1.4 Settled requirements

| # | Requirement |
|---|---|
| R1 | Photos are read by vision-capable LLMs. No traditional OCR engine is used anywhere. |
| R2 | The hand-off from the phone to the bigger screen is easy to use. The family calls this imperative. |
| R3 | An agent harness such as Claude Code or Codex can read and write the catalog, so it can do look-ups and help with planning, for example a seasonal rotation. |
| R4 | Every book has a state (Active, Stored or Retired) and a location. |
| R5 | Cover images are the family's own photos of the covers, because free sources rarely provide covers (see [book metadata sources](research/book-metadata-sources.md)). |
| R6 | Model work runs on subscriptions the family already has, as far as possible. A cheap or free API model is acceptable. |
| R7 | The simplest thing that reaches the goal wins. A plain spreadsheet is an acceptable end state. |

### 1.5 Nice to have

- Looking the catalog up away from home, for example to check in a bookshop whether a book is already owned.

### 1.6 Working assumptions

These are not yet confirmed by the family.

- Only children's books are cataloged.
- Reading an ISBN from a barcode does not count as OCR and is allowed.
- The interface is in English first.
- Seasonal rotation, retirement by age, the bookshop check and tracking books that leave must all be possible from the catalog's data. They need no dedicated features for the system to count as done.

### 1.7 Out of scope

- A reading log, favourites, or a catalog browser for the children.
- Adults' books.
- Deciding which books to keep.

## 2. Design

### 2.1 What the catalog records

**Settled:** a state and a location for every book (R4).

**Proposed:** one record per physical copy, with these fields.

| Field | Notes |
|---|---|
| Title | In its original script. |
| Sort key | The kana reading for Japanese, the plain title otherwise. No candidate store documents how it sorts Japanese or Czech (see [existing tools](research/existing-home-library-tools.md)). |
| Author, illustrator | |
| Publisher, year | |
| Language | Japanese, Czech or English; more than one for a bilingual book. |
| ISBN | Empty for a book without one. |
| Series | Also holds the magazine name and issue for monthly picture-book magazines. |
| Age range | A from-age, and optionally a to-age. |
| Season and theme tags | From a fixed list (2.2). |
| State | Active, Stored or Retired. |
| Location | A shelf or a box (2.3). |
| Cover photo | The family's own photo. |
| Source record | Which catalogue the metadata came from, and its record id. |
| Needs review | Set until a person has checked the record. |
| Notes | Free text. |

**Open:**

- Whether a book that has been sold or given away keeps a record, as a fourth state, or is deleted.
- Whether a keepsake mark protects a book from being Retired.
- Whether a cover photo is required for every book or only nice to have.
- How to treat borrowed and library books, which must not end up in the catalog.

### 2.2 Tags

**Proposed:** two short fixed lists, one of seasons and occasions, one of themes. A book can carry several of each. A starting point for the first list is the four seasons plus the occasions the family marks across the Japanese and Czech calendars, for example New Year, Setsubun, Easter, Tanabata, Halloween, St Nicholas Day and Christmas.

**Proposed:** the age range comes from the Czech national catalogue where its record states one. For other books the model proposes it and a person confirms it. No free source gives an age in years for Japanese or English books (see [book metadata sources](research/book-metadata-sources.md)).

**Open:** the actual lists. They are the family's to write.

### 2.3 Locations

**Proposed:** a location is one shelf of a bookcase, or one box, and nothing finer. Each has a short name written on a physical label, such as "Box 3". The catalog records where a book is now, and keeps no history of moves unless the store provides one for free.

**Open:** the naming scheme and the labels.

### 2.4 Capture

**Settled:** vision-capable LLMs do the reading (R1), and the cover image is the family's own photo (R5).

**Proposed:** three ways for a book to enter the catalog.

1. **Cover photo**, the main one. A photo of the front cover gives the cover image and usually the clearest title and author. It also works for thin books that have no text on the spine.
2. **Barcode photo.** Where the back cover carries an ISBN barcode, a second photo gives an exact identifier.
3. **Shelf photo.** One photo of a row of spines records quickly which books are at a location, and can later check a shelf against the catalog.

**Proposed:** an agent harness runs the vision model over new photos (R3, R6). For each book it sees, it writes the title, the author, the language and how sure it is.

**Open:**

- The mix of the three. It stays a proposal until it has been tested on the family's own photos (section 3).
- Which model. The family named GPT-6 Luna, and Space Bunny, which it reports as free over API on 2026-10-05. Whether each accepts images is not yet checked.

### 2.5 Matching a photo to a catalogue record

Research on 2026-10-05 found that an ISBN resolves to a solid record in all three languages from free sources that need no key. It also found that every free title search is exact on characters, so one misread character returns nothing. Details are in [book metadata sources](research/book-metadata-sources.md).

**Proposed:**

- **With an ISBN**, look it up by language:
  - Japanese: NDL Search, then openBD.
  - Czech: the National Library of the Czech Republic.
  - English: Open Library, then the Library of Congress.
- **Without an ISBN**, search by author or by a shortened title, collect the candidates, and let the model pick the best one or say that none fits.
- **With no match**, keep what the model read from the photo and mark the record for review.

### 2.6 The store

**Open.** This is the main undecided point. The research shortlist is Google Sheets, Grist, Homebox, and Baserow or NocoDB (see [existing tools](research/existing-home-library-tools.md)). Libib is ruled out by R3: its documented API has no endpoints for books.

How the requirements bear on the choice:

- **R3 (harness access)** is met by Google Sheets through a command-line client the family already uses, and by the others through their REST APIs.
- **R5 (own cover photos)** counts against Google Sheets. Its `IMAGE` function cannot show images stored in Google Drive, so the family's photos would have to be hosted somewhere else to appear in the sheet. Grist shows uploaded images as thumbnails in the table.
- **R2 (easy hand-off)** cannot be judged yet. How Grist, Homebox, Baserow and NocoDB behave on a phone or an iPad is unverified.
- **R7 (simplicity)** favours Google Sheets or hosted Grist, because neither needs a server at home.

**Proposed:** decide between Google Sheets and Grist by a hands-on test (section 3). Grist is the provisional front-runner, because it shows cover photos in the table and links books to locations properly. Google Sheets wins if Grist proves awkward on the phone or the iPad. Homebox is the third option if handling locations turns out to matter more than expected.

### 2.7 From the phone to the bigger screen

**Settled:** this path has to be easy (R2).

**Proposed:**

1. On the phone, photos go into a shared cloud folder with one sub-folder per location. The folder name tells the system where the books are.
2. A harness job picks up new photos, reads them (2.4), matches them (2.5) and writes records marked as needing review, each with its photo.
3. On the iPad or laptop, a review view shows each new record beside its photo. The person fixes the fields and clears the mark.
4. A book the model could not read is typed in on the same screen.

No step involves moving files by hand.

**Open:**

- Which cloud folder.
- Whether the job runs on a schedule or on request.
- Whether the review view is the store's own interface or a small page built for it.

### 2.8 Harness jobs

**Proposed:** this repository holds instructions that work in Claude Code and in Codex for four jobs.

- Cataloging new photos.
- Looking a book up.
- Proposing a seasonal rotation: which Stored books to bring out and which Active books to put away.
- Listing candidates for retirement by age.

## 3. What has to happen before the design is final

1. **Sample photos.** The family photographs a few shelves, an open box, a stack of thin books, some covers and some barcodes, and times one whole shelf taken cover by cover.
2. **Photo test.** Two or three vision models read those photos. The result fixes the capture mix and the model (2.4), and shows how much correction to expect.
3. **Catalog decisions.** The family settles the open points in 2.1 to 2.3.
4. **Store test.** About twenty real records go into Google Sheets and into Grist, and are used on a phone, the iPad and the laptop. The test covers cover display, ease of correction, Japanese and Czech sorting and search, and reading and writing by a harness.
5. **Store decision**, then a rough version of the flow in 2.7 tried on one real shelf.

After that come the build and the cataloging of the whole collection.

## 4. Research

- [Existing home library tools](research/existing-home-library-tools.md)
- [Book metadata sources](research/book-metadata-sources.md)
