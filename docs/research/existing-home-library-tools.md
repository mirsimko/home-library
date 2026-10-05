# Existing home library tools

> [!NOTE]
> **AI-generated research.** Written by a Claude Code subagent (Claude Sonnet 5.5, `claude-sonnet-5-5`) on 2026-10-05. Candidate URLs were found by three search-only Codex jobs (OpenAI `gpt-6-luna`); the pages were then read with WebFetch, which returns small-model summaries of a page, and with `curl`. No second-opinion review. Lightly edited for publication the same day: links to private planning notes were replaced.

## Question

Which existing tools could carry all or part of this system, and what would still have to be built around each?

Three families were surveyed: off-the-shelf book catalog apps, self-hosted open-source library or inventory managers, and a plain Google spreadsheet or spreadsheet-like database. `gog` is a Google Workspace command-line client already installed on the family's machines, and the XPS13 is a Linux laptop that could serve as an always-on host.

**Conventions.** Every link in this note was fetched on 2026-10-05; the source list at the end repeats each with its access date and how it was read. "unverified" means I could not confirm it from a primary source. "(inference)" marks my own reasoning, as opposed to a source claim. Page text that reached me only as a WebFetch summary is marked "WebFetch" in the source list; anything that decides a result was re-read with `curl` or from the raw repository file where possible.

## Short answer

The shortlist is five options, in order of how directly an agent harness can read and write them today.

1. **Google Sheets** (with `gog`) needs no adoption step. The local `gog` 0.19.0 already has `sheets get/update/append/batch-update` with `--json` and `--dry-run` ([local CLI help](#sources)). Verified pain points: `IMAGE()` rejects `drive.google.com` URLs ([Google](https://support.google.com/docs/answer/3093333)), multi-select dropdowns do not work on mobile ([Google](https://support.google.com/docs/answer/186103)), and API edits do not fire `onEdit` ([Apps Script](https://developers.google.com/apps-script/guides/triggers)).
2. **Grist** is the closest thing to a relational spreadsheet: Choice List, Reference and Attachment columns, a REST API, and SQLite files ([grist-core README](https://github.com/gristlabs/grist-core)). Hosted Free allows 5,000 records per document ([pricing](https://www.getgrist.com/pricing/)); the built-in MCP server is on hosted for every plan but on self-hosted only in the full edition ([Grist MCP doc](https://github.com/gristlabs/grist-help/blob/master/help/en/docs/mcp.md)).
3. **Homebox** is the only candidate whose data model already has nested shelf and box containers, with tags, custom fields, a Swagger-described REST API with API keys, and a third-party MCP server ([docs](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/user-guide/entity-types.mdx), [swagger.json](https://github.com/sysadminsmedia/homebox/blob/main/backend/app/api/static/docs/swagger.json), [homebox-mcp](https://github.com/dgahagan/homebox-mcp)). Its fields are inventory-shaped, not book-shaped.
4. **Baserow or NocoDB** (one slot): self-hosted Airtable-style databases, each with a REST API and MCP code in the repository. Both are comparable to Grist for this job, with more moving parts.
5. **Libib** is the one polished Android book app, but the harness cannot write to it: the documented REST API covers accounts, managers and patrons only, so the bridge is CSV upload and one-collection-at-a-time CSV export ([API docs](https://support.libib.com/rest-api/introduction.html), [export docs](https://support.libib.com/libib/website/settings.html)).

No vendor documents Czech or Japanese sorting for any candidate. Only Libib (UTF-8 CSV) and Homebox (Unicode- and accent-insensitive search) say anything about non-English text, so a test with real records is needed whichever is chosen. Dropped: BookBuddy (Apple platforms only), LibraryThing and TinyCat (no API for members' books), Booklog (closed, help pages unreachable), Jelu (reading tracker), Calibre and Calibre-Web (ebook domain), Koha (heavy stack), Airtable (hosted, 1,000-record and 1,000-API-call free caps), and young projects with under 20 stars.

## Comparison

Evidence and links for every cell are in the per-candidate notes below. "unv." = unverified. "JA/CZ/EN" is only what the vendor states about non-English text; none states Czech or Japanese sort order.

| Candidate | JA/CZ/EN text | Push in / read back | Location, state, season, age | Harness access | Android x2 + laptop | Cost, export, self-host |
|---|---|---|---|---|---|---|
| **Google Sheets** | unv. (cells are text; sort order unv.) | Sheets API append/update; CSV import and export | Any columns; dropdown validation; no multi-select on mobile | `gog` CLI today; no MCP needed | Android app, offline, 100 concurrent editors | Free; exports CSV/XLSX/PDF; not self-hosted |
| **Grist** | unv. | REST API with key; CSV import that can update existing records | Choice, Choice List, Reference, Attachment columns | REST; MCP hosted (all plans), self-hosted full edition only | Mobile web: unv.; two users fine | Core free (Apache-2.0); hosted Free 5,000 records/doc; ARM64, about 100 MB RAM |
| **Homebox** | Unicode and accent-insensitive search documented; CJK substring unv. | REST (Swagger, API keys); CSV import updates by `import_ref` | Nested location containers, tags, custom fields; no book fields | REST; third-party MCP (MIT) | Responsive web, QR scan; multi-user unv. | Free (AGPL-3.0); Go + SQLite, under 50 MB idle; amd64 and arm64 images |
| **Baserow** | unv. | REST (OpenAPI) | Fields, select types (unv. per type) | REST; MCP code in repo, edition gating unv. | unv. | MIT core; Free cloud 3,000 rows; arm64 image |
| **NocoDB** | unv. | REST data and meta APIs, API tokens | Fields, views | REST; MCP in docs and repo | unv. | Sustainable Use License; Community self-host free; arm64 binary and SQLite |
| **Libib** | CSV must be UTF-8 for non-Latin | CSV in and out; REST has no item endpoints | Collections, tags, 4 custom fields per type (Pro only) | CSV only | Android app and scanning on all plans; multi-user is Pro | Free 5,000 items, 1 user; Pro $9/mo or $99/yr; no self-host |
| **Airtable** | unv. | Web API | Fields | Official MCP, all plans | Android app, barcode field | Free: 1,000 records/base, 1,000 API calls/workspace/month; hosted only |
| **Jelu** | unv. | REST (Swagger UI), API tokens, CSV import and export | Tags and tag-based lists; no location field documented | REST | Mobile ISBN scan; PWA unv. | MIT; Docker amd64, arm64, armv7 |
| **Calibre / Calibre-Web** | language field on add; sort unv. | `calibredb` CLI with JSON output; Calibre-Web README lists an OPDS feed and metadata editing, no API | Custom columns | CLI, plain SQLite file | Browser or OPDS; editing on Android unv. | Free; local files |
| **Koillection** | unv. | REST (API Platform, JWT) | Custom fields and templates | REST | Responsive; no app | MIT; needs PostgreSQL, MariaDB or MySQL |
| **LibraryThing / TinyCat** | unv. | Import CSV template; export JSON/TSV/Excel/MARC; no members' books API | Tags, custom data | Export files only | Mobile web | Paid; TinyCat targets small circulating libraries |
| **Booklog** | unv. (Japanese service) | Help pages unreachable: unv. | Categories, tags | unv. | Android app, continuous barcode scan | Free with optional premium |
| **BookBuddy** | Japanese UI | CSV, PDF, HTML export | Categories, tags, custom fields | None found | Apple only | Free 50 books; $9.99 lifetime |
| **Koha** | UTF-8 (unv.) | REST takes MARC records | MARC fields | REST | Web | Free; heavy stack |

## Notes per candidate

### Google Sheets (deep)

**What it gives for free.**
- Direct harness access: the local `gog` 0.19.0 lists `get`, `update`, `append`, `batch-update`, `table`, `validation`, `export` and more under `gog sheets`, with `--json`, `--dry-run`, `--readonly` and `--wrap-untrusted` flags ([`gog sheets --help`, local](#sources)). Underneath is the Sheets API, whose `values.append` finds a table in the given range and appends after it; scopes are `spreadsheets`, `drive` or `drive.file` ([API reference](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append)).
- Quotas: 300 read or write requests per minute per project and 60 per minute per user per project; a 2 MB payload is recommended ([limits](https://developers.google.com/workspace/sheets/api/limits)). A few hundred books fit in a handful of `batch-update` calls. Size limit is 20 million cells ([Google](https://support.google.com/drive/answer/37603)).
- Two people: up to 100 people can edit at once, with Viewer, Commenter and Editor roles ([Google](https://support.google.com/a/users/answer/13309904)). Version history shows who edited what and can restore versions; up to 15 named versions per spreadsheet; edit history does not record added or deleted rows ([Google](https://support.google.com/docs/answer/190843)).
- Phone: the Android app creates, views and edits Sheets and imports and exports CSV ([Google](https://support.google.com/docs/answer/6000292?co=GENIE.Platform%3DAndroid)); files can be made available offline ([Google](https://support.google.com/docs/answer/6388102?co=GENIE.Platform%3DAndroid)). Sync and conflict behaviour while offline is not documented on that page (unverified).
- Dropdowns from a range or a list are native data validation ([Google](https://support.google.com/docs/answer/186103)).
- Apps Script: web apps via `doGet` or `doPost`, running as the owner or as the user ([Apps Script](https://developers.google.com/apps-script/guides/web)). Quotas differ by account type: consumer accounts get 90 min per day of trigger runtime and 20,000 URL fetches per day, Workspace accounts 6 h and 100,000; execution is capped at 6 minutes either way ([quotas](https://developers.google.com/apps-script/guides/services/quotas)).
- AppSheet: a Free/Prototype plan with up to 10 test users; barcode scanning is listed only under Core ($10 per user per month) and above, offline and webhooks under paid plans, and Core allows 10 databases of 2,500 rows ([pricing](https://about.appsheet.com/pricing/)). Scanning works only in the mobile app, not the browser, and covers EAN-13 among other formats ([AppSheet](https://support.google.com/appsheet/answer/10106618)). Whether a family may keep running a Prototype app long-term is unverified. AppSheet's Sheets guide warns that `onEdit` triggers do not fire for edits made through AppSheet ([AppSheet](https://support.google.com/appsheet/answer/10106594)).

**Where it hurts.**
- Cover images: `IMAGE(url)` cannot use `drive.google.com` URLs and the cell does not resize to the image ([Google](https://support.google.com/docs/answer/3093333)). So the family's own cover photos cannot be shown by pointing at Drive. Covers from a metadata source's URL would work. Whether the API can write Sheets' uploaded in-cell images is unverified.
- Multi-select: a dropdown cannot select several options on mobile ([Google](https://support.google.com/docs/answer/186103)), which matters for season or theme tags on a phone (inference).
- History: `onEdit` is not run by API requests or script executions ([Apps Script](https://developers.google.com/apps-script/guides/triggers)). A trigger that logs location changes would therefore miss everything the pipeline or `gog` writes. A location history needs explicit rows in a separate tab written by whoever moves the book (inference). Sheets has no native relations, so Books, Locations and Moves tabs are linked by lookup formulas or by the agent (inference).
- No key-based upsert in the Sheets API as documented; append adds rows after a table ([API reference](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append)). The pipeline must read, match on an ID, then update (inference).
- Barcode scanning and in-cell image insertion are not described on the Android help page I read ([Google](https://support.google.com/docs/answer/6000292?co=GENIE.Platform%3DAndroid)); unverified whether the app has them.
- Japanese or Czech sort and search behaviour is unverified.

### Grist (deep)

- Model: a relational spreadsheet; Python formulas; each document is SQLite, readable by any SQLite tool ([README](https://github.com/gristlabs/grist-core)). Column types include Choice, Choice List, Reference, Reference List and Attachment, with image thumbnails in cells ([Grist](https://support.getgrist.com/col-types/)). A Reference to a Locations table and a Moves table gives location history without formulas (inference).
- Import: CSV import can update existing records using merge fields ([imports](https://github.com/gristlabs/grist-help/blob/master/help/en/docs/imports.md)). Forms feed a table directly, with file attachments, hidden fields and URL pre-population ([README](https://github.com/gristlabs/grist-core)).
- API: a REST API authenticated by a per-user API key ("same permissions as that user"); the docs recommend a scoped connected app for AI agents ([REST doc](https://github.com/gristlabs/grist-help/blob/master/help/en/docs/rest-api.md)). Webhooks are configurable ([README](https://github.com/gristlabs/grist-core)).
- MCP: on hosted Grist the MCP server is on for all plans; on self-hosted it is part of the full edition, enabled with `GRIST_MCP_ENABLED=true`, and clients can pass an API key ([Grist MCP doc](https://github.com/gristlabs/grist-help/blob/master/help/en/docs/mcp.md)). The full edition is free for individuals and small organisations under US$1 million total annual funding via an activation key ([README](https://github.com/gristlabs/grist-core)). `grist-core` can use community MCP servers over the REST API ([README](https://github.com/gristlabs/grist-core)).
- Cost: hosted Free is $0 with unlimited documents, 5,000 records per document, 10 team members and 2 guests per document; Pro is $10 per user per month ([pricing](https://www.getgrist.com/pricing/)). `grist-core` is Apache-2.0 ([README](https://github.com/gristlabs/grist-core)).
- Self-host: ARM64 is packaged; a sample document ran in about 100 MB RAM without sandboxing and 200 MB with it ([self-managed doc](https://github.com/gristlabs/grist-help/blob/master/help/en/docs/self-managed.md)). The Docker image has amd64 and arm64 builds ([Docker Hub](https://hub.docker.com/v2/repositories/gristlabs/grist/tags/latest)).
- Unverified: Android and mobile-browser usability (the column-types page and forms page say nothing about it), and Japanese or Czech search and sort.

### Homebox (deep)

- Fit: "inventory and organization system built for the Home User"; Go, SQLite, idle memory under 50 MB; categories, locations, tags, custom fields, photo upload, responsive design ([README](https://github.com/sysadminsmedia/homebox)). Docker images are built for linux/amd64 and linux/arm64 ([publish workflow](https://github.com/sysadminsmedia/homebox/blob/main/.github/workflows/docker-publish.yaml)). AGPL-3.0, 7,446 GitHub stars, last push 2026-10-04 ([GitHub API](https://api.github.com/repos/sysadminsmedia/homebox)).
- Location model: entity types let you define container types such as Room, Shelf and Drawer, and locations carry photos, tags, custom fields, notes and asset IDs ([entity types](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/user-guide/entity-types.mdx)). This matches "shelf or box" directly (inference).
- Import and update: CSV import takes `HB.location` with nested paths, `HB.label`, and `HB.field.<name>` custom fields; a repeated `HB.import_ref` updates the existing item instead of duplicating it. Attachments are not imported, and item-to-item relations are not supported ([CSV doc](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/advanced/import-csv.mdx)). The standard columns are inventory-shaped (serial number, manufacturer, purchase price), with no author or language column, so book metadata would live in custom fields (inference).
- API: the repository's Swagger file lists `/v1/entities` (GET, POST), `/v1/entities/{id}` (GET, PUT, DELETE, PATCH), `/v1/entities/import`, `/v1/entities/export`, `/v1/entities/tree`, `/v1/tags`, and `/v1/users/self/api-keys` ([swagger.json on main](https://github.com/sysadminsmedia/homebox/blob/main/backend/app/api/static/docs/swagger.json)). It is the file on `main`; the version we would run may differ. API keys need `HBOX_AUTH_API_KEY_PEPPER` on the server ([configure doc](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/quick-start/configure/index.mdx)).
- MCP: `homebox-mcp` is a third-party MIT server over the REST API, requiring Homebox 0.26 or later and an API key from Profile, API Keys; it covers questions, intake, attachments and QR labels ([homebox-mcp README](https://github.com/dgahagan/homebox-mcp)).
- Text handling: database search covers names, descriptions, notes, tag names and custom field values, is case-insensitive "across the full Unicode range" and accent-insensitive; Meilisearch is optional ([search doc](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/quick-start/configure/search.mdx)). Whether Japanese substring search works is unverified; so is Czech sort order.
- Scanning: a built-in QR reader and generator for labels ([tips](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/user-guide/tips-tricks.mdx)). A barcode lookup endpoint exists, but its configured sources are BarcodeSpider and the Open Food Facts family ([configure doc](https://github.com/sysadminsmedia/homebox/blob/main/docs/src/content/docs/en/quick-start/configure/index.mdx)); fit for ISBN lookup is unverified.
- Not found: any location history or move log (unverified), and Android PWA install (unverified).

### Baserow and NocoDB (deep, one slot)

- **Baserow.** Open-core; non-premium features under MIT; REST API with an OpenAPI schema; Docker quick start ([README](https://github.com/baserow/baserow)). The repository holds MCP code in `backend/src/baserow/api/mcp` and `contrib/database/mcp` ([repo tree](https://github.com/baserow/baserow/tree/develop/backend/src/baserow/contrib/database/mcp)); whether it is premium-gated is unverified. Cloud Free is 3,000 rows per workspace; Premium is $10 per user per month ([pricing](https://baserow.io/pricing)). The image is built for amd64 and arm64 ([Docker Hub](https://hub.docker.com/v2/repositories/baserow/baserow/tags/latest)). Resource use on a Pi is unverified (the docs mention reducing internal processes to cut memory, [install doc](https://github.com/baserow/baserow/blob/develop/docs/installation/install-with-docker.md)).
- **NocoDB.** Licensed under the Sustainable Use License, not an OSI open-source licence ([README](https://github.com/nocodb/nocodb)). Docker with SQLite, a Linux arm64 binary, grid, gallery, form, kanban and calendar views, REST APIs ([README](https://github.com/nocodb/nocodb)). Data and meta REST APIs with API tokens, and an MCP server described in the docs ([docs](https://nocodb.com/docs/apis-and-mcp)); MCP code is in `packages/nocodb/src/mcp` ([repo tree](https://github.com/nocodb/nocodb/tree/develop/packages/nocodb/src/mcp)). Self-hosted Community is free with unlimited records and seats; Cloud Free is 1,000 records and 1,000 API calls a month ([pricing](https://nocodb.com/pricing)).
- Unverified for both: Android usability, CJK and Czech search and sort, and edition gating for MCP.
- Judgment (inference): for this job they overlap with Grist, which has the stronger Reference and SQLite-file story and a documented hosted-free MCP route.

### Libib (deep)

- Plans: Basic is free for up to 5,000 items and 100 collections, one user; Pro is $9 per month or $99 per year; additional managers cost $2 per month or $24 per year each; the REST API is Pro and above; Android app, barcode scanning and CSV import and export are on every plan ([pricing](https://www.libib.com/pricing)). Cover or spine scanning is not a factor here; barcode scanning is built in.
- Custom fields: Pro only, up to 4 per media type ([settings doc](https://support.libib.com/libib/website/settings.html)). Tags and a 5,000-character notes field exist in CSV import; the import page lists no custom-field columns ([import doc](https://support.libib.com/libib/website/add-items.html)).
- CSV: UTF-8 is "mandatory" for non-Latin characters or diacritics; items need a valid ISBN, UPC or EAN unless a Pro user turns on Force Import Mode, which allows title-only ([import doc](https://support.libib.com/libib/website/add-items.html)). Many children's picture books lack usable ISBNs, so that matters (inference).
- Export: one collection per CSV file ([settings doc](https://support.libib.com/libib/website/settings.html)).
- API: `x-api-key` and `x-api-user` headers, one request per 2 seconds, Pro only; the documented section lists Introduction, Accounts, Managers and Patrons, with no item pages ([API intro](https://support.libib.com/rest-api/introduction.html), [accounts](https://support.libib.com/rest-api/accounts.html)). Item read or write endpoints may exist undocumented (unverified).
- Fit (inference): shelves or boxes would map to collections or tags. The harness could read only via manual CSV exports and write only via manual CSV uploads, so "an outside script can push records in and read them back" is not met in practice. Whether re-importing updates existing items is unverified.

### Dropped, with reasons

- **Airtable.** Free: 1,000 records per base, 1 GB attachments, 1,000 API calls per workspace per month, 5 editors, 2 weeks of history ([plans](https://support.airtable.com/articles/2277136852-airtable-plans-overview)). It has an official MCP server on all plans ([Airtable](https://support.airtable.com/articles/9897799762-using-the-airtable-mcp-server)) and a barcode field scanned from the iOS or Android app ([Airtable](https://support.airtable.com/articles/3817194919-using-the-barcode-field-in-airtable)). It is hosted-only and the 1,000-call cap is tight for an agent loop (inference), so Grist or Baserow cover the same ground.
- **Jelu.** A self-hosted "personal Goodreads" for tracking reading, MIT, with API, ISBN camera scanning, tags and CSV import and export ([README](https://github.com/bayang/jelu)). It has a Swagger UI and API tokens ([API doc](https://bayang.github.io/jelu-web/usage/api/)); custom lists are tag intersections ([docs](https://bayang.github.io/jelu-web/usage/custom-lists/)). No location or custom-field documentation was found in the docs index ([docs](https://bayang.github.io/jelu-web/)). The Docker image has amd64, arm64 and armv7 builds ([Docker Hub](https://hub.docker.com/v2/repositories/wabayang/jelu/tags/latest)). Reading life is out of scope for this project.
- **Calibre and Calibre-Web.** `calibredb` can add an empty book with languages and identifiers, define custom columns, set custom values, search, and output JSON, and can target a running Content server ([calibredb manual](https://manual.calibre-ebook.com/generated/en/calibredb.html)). That is the best CLI story of any candidate, but Calibre-Web is described as a front end for "browsing, reading, and downloading eBooks" over a Calibre database, with custom columns and metadata editing ([README](https://github.com/janeczku/calibre-web)). Wrong domain for physical picture books, and Android editing is unverified.
- **Koha.** Needs MariaDB or MySQL, Zebra or Elasticsearch, memcached and Plack, RabbitMQ and Apache; Raspberry Pi is not addressed in the manual ([install doc](https://koha-community.org/manual/24.05/en/html/installation.html)). Its REST API creates records from MARC ([API](https://api.koha-community.org/)). Far too heavy.
- **Koillection.** MIT, PHP and Symfony, custom fields and templates, REST via API Platform with JWT auth ([repo](https://github.com/benjaminjonard/koillection), [API doc](https://github.com/benjaminjonard/koillection/wiki/API)); 1,327 GitHub stars ([GitHub API](https://api.github.com/repos/benjaminjonard/koillection)). A credible near-miss for Homebox, but needs a PostgreSQL or MySQL-family database, and I did not look for an MCP server (unverified).
- **LibraryThing and TinyCat.** "LibraryThing does not currently offer an API for members' books"; export is Excel, tab-delimited, JSON or MARC, import takes a CSV template ([developer hub](https://web.archive.org/web/2025/https://www.librarything.com/developer), [import/export](https://web.archive.org/web/2025/https://www.librarything.com/import_export.php), both read from the Wayback Machine because librarything.com returned Cloudflare blocks). TinyCat is a small-library circulation system with 30-day trials ([TinyCat](https://web.archive.org/web/2025/https://www.librarycat.org/about/)); price unverified.
- **BookBuddy.** The App Store listing names iPhone, iPad, Mac, Apple Vision and Watch, free to 50 books, $9.99 lifetime, with CSV, PDF and HTML export and custom fields ([App Store](https://apps.apple.com/us/app/bookbuddy-book-tracker/id395150347)). No Android.
- **Booklog (ブクログ).** The Android app supports continuous barcode scanning, categories and tags, and original items for ZINEs and self-published books; premium adds folders ([Play Store](https://play.google.com/store/apps/details?id=jp.booklog.android&hl=ja)). Its help pages on import, export and API sit behind Cloudflare and returned HTTP 403 to both WebFetch and `curl`, so import, export and API are unverified. A Codex search snippet claimed CSV import is on the PC web version only; I did not confirm that.
- **Young projects.** Shelf (15 stars), Librarium API (12), Runary (1), TPT Library (0) and ShelfOS (0) are too new to rely on ([GitHub API](https://api.github.com/repos/dgahagan/shelf), [librarium-api](https://api.github.com/repos/fireball1725/librarium-api), [runary](https://api.github.com/repos/outerstellar-hq/runary), [tpt-library](https://api.github.com/repos/tpt-solutions/tpt-library), [ShelfOS](https://api.github.com/repos/matheine/ShelfOS)). I did not read their READMEs, so their feature claims are unverified.
- **Not examined.** BookWyrm, Kavita, BookLore, HomeBranch and BookNook were surfaced by Codex as ebook or social-reading tools and not examined.

## What we would still have to build

Common to every option (inference): the photo-to-record step; a stable ID and de-duplication rule; and a sort-key or reading column, because no source shows any candidate sorting Japanese by reading or Czech by its own alphabet. Test two or three real records in each shortlisted tool before the decision.

**Google Sheets**
- A schema in tabs (Books, Locations, Moves) with dropdown validation, and a convention for season and age that works without mobile multi-select (for example one column per season, or a single-value column).
- A writer that reads, matches on ID and updates, since there is no upsert; batch writes to stay under 60 requests a minute per user.
- A Moves tab written explicitly by the pipeline or the harness, not by `onEdit`.
- Cover handling: store URLs from a metadata source for `IMAGE()`, or skip covers.
- A correction screen is the sheet itself; check how wide rows feel on an Android phone.

**Grist**
- Tables for Books, Locations and Moves with Reference columns, and Choice List columns for season and age.
- A small writer over the REST API (or the community or hosted MCP), and an API key or connected app for the harness.
- A hosting decision: hosted Free (5,000 records per document) or self-hosted on the XPS13 or a Pi; if self-hosted, the full edition's free activation key for MCP.
- A phone test, since mobile use is undocumented.

**Homebox**
- A mapping from book metadata to Homebox fields: title to name, author, language, publisher and age range into custom fields via `HB.field.*` or the API.
- Shelf and box entity types as containers, and a script that creates containers first and then items, with `HB.import_ref` or the API for idempotent updates.
- A location history table or log outside Homebox, since none is documented.
- A search test with Japanese and Czech titles, and a check that the version we deploy matches the Swagger file and `homebox-mcp`'s 0.26 requirement.
- Hosting on the XPS13 or a Pi, plus a tunnel or VPN if the catalog should be reachable away from the apartment (inference).

**Baserow or NocoDB**
- The same table design as Grist, hosting, and an API token; plus a test of mobile use, language handling, and whether the MCP server is available in the edition we run.

**Libib**
- A CSV exporter in the exact import column set, a manual upload step in the web UI, and a CSV re-export step for read-back.
- A plan for books with no ISBN (Pro Force Import) and for location (collections or tags); Pro is needed for custom fields and multiple users.
- A decision on whether CSV-only access satisfies the "harness in the loop" requirement.

## Not resolved here

- Czech and Japanese search and sort in every tool.
- Android mobile usability for Grist, Baserow, NocoDB and Homebox (all unverified).
- Libib item API, Booklog import, export and API, LibraryThing pricing, TinyCat pricing.
- Whether AppSheet's free Prototype plan may be used long-term for a household app.
- This note picks no winner; that is a later decision (see the [draft spec](../spec.md)).

## Sources

All accessed 2026-10-05. Method: **WebFetch** = page summarised by WebFetch's small model; **curl** = raw text read directly; **raw** = raw file from the project repository; **Wayback** = Internet Archive copy of a page that returned Cloudflare 403; **local** = command run on this machine.

- Local CLI: `gog sheets --help`, `gog schema sheets append --json` (gog 0.19.0, Homebrew) — local.
- Google Sheets API limits: https://developers.google.com/workspace/sheets/api/limits — WebFetch
- Sheets API `values.append`: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append — WebFetch
- IMAGE function: https://support.google.com/docs/answer/3093333 — WebFetch and curl
- Sheets Android app: https://support.google.com/docs/answer/6000292?co=GENIE.Platform%3DAndroid — WebFetch
- Offline editing on Android: https://support.google.com/docs/answer/6388102?co=GENIE.Platform%3DAndroid — WebFetch
- Dropdown lists: https://support.google.com/docs/answer/186103 — WebFetch
- Version history: https://support.google.com/docs/answer/190843 — WebFetch
- Collaboration: https://support.google.com/a/users/answer/13309904 — WebFetch
- File and cell limits: https://support.google.com/drive/answer/37603 — WebFetch
- Apps Script quotas: https://developers.google.com/apps-script/guides/services/quotas — WebFetch
- Apps Script web apps: https://developers.google.com/apps-script/guides/web — WebFetch
- Apps Script triggers: https://developers.google.com/apps-script/guides/triggers — WebFetch
- AppSheet pricing: https://about.appsheet.com/pricing/ — WebFetch
- AppSheet barcode: https://support.google.com/appsheet/answer/10106618 — WebFetch
- AppSheet and Google Sheets: https://support.google.com/appsheet/answer/10106594 — WebFetch
- grist-core README: https://github.com/gristlabs/grist-core (raw README) — raw
- Grist REST doc: https://github.com/gristlabs/grist-help/blob/master/help/en/docs/rest-api.md — raw
- Grist MCP doc: https://github.com/gristlabs/grist-help/blob/master/help/en/docs/mcp.md — raw
- Grist self-managed doc: https://github.com/gristlabs/grist-help/blob/master/help/en/docs/self-managed.md — raw
- Grist imports doc: https://github.com/gristlabs/grist-help/blob/master/help/en/docs/imports.md — raw (grep only)
- Grist column types: https://support.getgrist.com/col-types/ — WebFetch
- Grist pricing: https://www.getgrist.com/pricing/ — WebFetch
- Docker Hub tag metadata: https://hub.docker.com/v2/repositories/gristlabs/grist/tags/latest, https://hub.docker.com/v2/repositories/baserow/baserow/tags/latest, https://hub.docker.com/v2/repositories/wabayang/jelu/tags/latest — curl
- Homebox README: https://github.com/sysadminsmedia/homebox — raw
- Homebox docs (entity types, CSV import, search, configure, tips and tricks): https://github.com/sysadminsmedia/homebox/tree/main/docs/src/content/docs/en — raw
- Homebox Swagger: https://github.com/sysadminsmedia/homebox/blob/main/backend/app/api/static/docs/swagger.json — raw, parsed
- Homebox image workflow: https://github.com/sysadminsmedia/homebox/blob/main/.github/workflows/docker-publish.yaml — raw
- homebox-mcp: https://github.com/dgahagan/homebox-mcp — raw
- GitHub repository metadata (licence, stars, last push): https://api.github.com/repos/sysadminsmedia/homebox, https://api.github.com/repos/benjaminjonard/koillection, https://api.github.com/repos/bayang/jelu, https://api.github.com/repos/dgahagan/shelf, https://api.github.com/repos/fireball1725/librarium-api, https://api.github.com/repos/outerstellar-hq/runary, https://api.github.com/repos/tpt-solutions/tpt-library, https://api.github.com/repos/matheine/ShelfOS — curl (the unauthenticated rate limit stopped the other repositories)
- Baserow README and pricing: https://github.com/baserow/baserow, https://baserow.io/pricing — raw and WebFetch; MCP code location from the repository tree, https://github.com/baserow/baserow/tree/develop/backend/src/baserow/contrib/database/mcp — curl on the GitHub tree API; Docker install doc: https://github.com/baserow/baserow/blob/develop/docs/installation/install-with-docker.md — raw (grep only)
- NocoDB README, docs, pricing: https://github.com/nocodb/nocodb, https://nocodb.com/docs/apis-and-mcp, https://nocodb.com/pricing — raw and WebFetch; MCP code location: https://github.com/nocodb/nocodb/tree/develop/packages/nocodb/src/mcp — curl on the GitHub tree API; Docker Hub: https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/latest — curl
- Libib pricing: https://www.libib.com/pricing — WebFetch
- Libib REST API: https://support.libib.com/rest-api/introduction.html, https://support.libib.com/rest-api/accounts.html — curl (sidebar and endpoints)
- Libib import: https://support.libib.com/libib/website/add-items.html — WebFetch
- Libib settings and export: https://support.libib.com/libib/website/settings.html — WebFetch
- Airtable plans, MCP, barcode: https://support.airtable.com/articles/2277136852-airtable-plans-overview, https://support.airtable.com/articles/9897799762-using-the-airtable-mcp-server, https://support.airtable.com/articles/3817194919-using-the-barcode-field-in-airtable — WebFetch
- Jelu: https://github.com/bayang/jelu (README), https://bayang.github.io/jelu-web/, https://bayang.github.io/jelu-web/usage/api/, https://bayang.github.io/jelu-web/usage/custom-lists/ — raw and WebFetch
- Calibre: https://manual.calibre-ebook.com/generated/en/calibredb.html — curl; Calibre-Web README: https://github.com/janeczku/calibre-web — raw
- Koha: https://koha-community.org/manual/24.05/en/html/installation.html, https://api.koha-community.org/ — WebFetch
- Koillection: https://github.com/benjaminjonard/koillection (WebFetch), https://github.com/benjaminjonard/koillection/wiki/API — raw
- LibraryThing and TinyCat: https://web.archive.org/web/2025/https://www.librarything.com/developer, https://web.archive.org/web/2025/https://www.librarything.com/import_export.php, https://web.archive.org/web/2025/https://www.librarycat.org/about/ — Wayback via curl (the live sites returned Cloudflare blocks)
- BookBuddy: https://apps.apple.com/us/app/bookbuddy-book-tracker/id395150347 — WebFetch
- Booklog Android listing: https://play.google.com/store/apps/details?id=jp.booklog.android&hl=ja — curl; Booklog help pages (https://booklog.zendesk.com/hc/ja, https://booklog.jp/help) — HTTP 403, not read
- Codex discovery: three search-only jobs on `gpt-6-luna` returned candidate URLs only; none of its claims are cited here except where marked as unconfirmed.
