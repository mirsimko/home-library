# Book metadata sources

> [!NOTE]
> **AI-generated research.** Written by a Claude Code subagent (Claude Sonnet 5.5, `claude-sonnet-5-5`) on 2026-10-05, from each source's own documentation and terms and from real `curl` and Z39.50 calls made the same day. Candidate URLs were found by three search-only Codex jobs (OpenAI `gpt-6-luna`, medium effort); every page and endpoint cited was then fetched and checked by the subagent. No second-opinion review. Lightly edited for publication the same day: links to private planning notes were replaced.

## Question

Given an ISBN, or a title and author read off a photo, which sources return reliable metadata and cover images for children's books in Japanese, Czech and English, and on what terms?

Conventions. All links carry their access date, 2026-10-05. **Observed** means I saw it in a real response. **Documented** means the source's own documentation or terms say so. **Unverified** means I could not check it. AI-generated synthesis and recommendations are marked as such. Test books: ぐりとぐら, だるまさんが, はらぺこあおむし (Japanese); Broučci, Krtek a zajíček, Pohádky o pejskovi a kočičce, Rumcajs (Czech); Where the Wild Things Are, The Very Hungry Caterpillar, Brown Bear, Brown Bear (English).

## Short answer

**One line.** Every language has a free, keyless source that resolves an ISBN to a solid catalog record (NDL Search for Japanese, the National Library of the Czech Republic over Z39.50 for Czech, Open Library plus Library of Congress for English), but cover images, target age and seasonal tags are thin everywhere, and only the Czech national catalogue carries a usable age band (a MARC audience code plus, in many records, an age note such as "Pro děti od 3 let").

### Recommended lookup order (AI-generated synthesis from the observations below)

**Japanese**
1. **NDL Search OpenSearch/SRU**, restricted to `dpid=iss-ndl-opac`, by ISBN, or by title plus author. It returns the title reading, author readings, publisher, year, price, genre 児童図書 and class codes; the SRU `dcndl` schema adds a one-line abstract and a coarse audience 児童. No key. It has no cover.
2. **openBD** by ISBN, as a supplement: a cheap, fast second record that sometimes has a cover, a description or a Cコード. It has no title search and covers some publishers badly (偕成社 is almost absent).
3. **Rakuten Books Book Search** (needs a free Rakuten developer app; I could not call it) as the title-search and cover fallback: it has a picture-book filter, kana readings and 200x200 covers.
4. **Open Library** by ISBN, only for the cover and a romanised title (it held the ぐりとぐら ISBN and a cover).
5. Magazines such as こどものとも: search NDL **by the story title**, not by the magazine code (see Gaps).

**Czech**
1. **NK ČR catalogue over Z39.50** (`aleph.nkp.cz:9991`, bases `NKC-UTF` and `SKCM-UTF`), by ISBN (10 or 13 digit) or by title plus author. CC0, no key. Records carry the illustrator, series, genre/form (for example `leporela`), Konspekt class, subject headings, a summary, an audience band in the MARC 008 field (preschool, primary and so on) and, in many recent records, an age note such as `Pro děti od 2 let`. Pre-ISBN books are in it (a 1930s *Broučci* edition came back).
2. **Knihovny.cz** would be the second source, but its pages and API answered my curl calls with a bot challenge (HTTP 418) and I did not work around it. Ask the operators, or use it by hand.
3. Covers: no free source I could use. Open Library had none for the Czech ISBNs I tried; obalkyknih.cz is only for registered libraries. Use the family's own cover photo. Google Books (needs a key) is untested for Czech.

**English**
1. **Open Library** by ISBN (`/api/books`) or `search.json`. Keyless; returns subjects (for example `Juvenile fiction`, `Dreams`) and a cover URL.
2. **Library of Congress SRU** (`lx2.loc.gov/sru/lcdb`, keyless) for MARC subject headings (`Caterpillars -- Fiction`), the juvenile flag and a summary. It has no cover.
3. **Google Books** only after getting an API key: keyless calls returned HTTP 429 with a quota of 0.

### What stays uncovered

- **Target age for Japanese books.** None of the free Japanese sources carries an age in years. NDL gives only the coarse audience 児童; openBD carries ONIX audience and Cコード values (not decoded here). EhonNavi, the one Japanese site that is rich in age and season, has no API and forbids reuse (see its section).
- **Season and theme tags** outside Czech. NDL gives class codes and a one-line abstract; LoC and Open Library give topical subjects, not seasons. Czech subject headings do carry seasons (for example `Vánoce`), but only for some books. Expect to derive season and age by the LLM from title plus abstract, and store them as the family's own tags.
- **Japanese covers.** NDL ended its cover service on 2026-03-31; openBD held a cover for roughly 1 in 20 random ISBNs and about 1 in 200 in my picture-book-publisher sample.
- **Czech covers**, as above.
- **Japanese monthly picture-book magazines** with only a 雑誌コード. No source I called looks a book up by magazine code. NDL does hold the individual stories by title; the registry at magcode.jpo.or.jp maps codes to magazine title and publisher only.
- **Misread titles.** None of the free sources is fuzzy. See the table column on title search; a wrong character gave zero results at NDL, NK ČR and Open Library.

## Sources against the criteria

Legend: Y = yes (observed), (d) = documented only, n = no, ? = unverified.

| Source | Key / cost / limits | ISBN lookup | Title + author search, forgiveness | Cover | Target age | Subjects / season | Series, reading | Reuse terms |
|---|---|---|---|---|---|---|---|---|
| **NDL Search API** (JP) | No key, free. Non-commercial use needs no application; credit required; concurrent-request cap (I hit one 429) | Y, good; filter `dpid=iss-ndl-opac` to avoid dozens of duplicate holdings records | Y. Kana and katakana variants match through readings; one wrong character or wrong kanji gave 0 hits | n (thumbnail API ended 2026-03-31; `/thumbnail/` returned 403) | Only coarse `audience` 児童 (SRU `dcndl`) | NDC and NDLC class codes, genre 児童図書, abstract text; no keyword headings seen | Y: title reading, creator readings, `seriesTitle` | Own bibliographies CC BY (credit); other providers differ per provider list |
| **openBD** (JP) | No key, free | Y, up to 1,000 ISBNs per GET | n, no title search | Sparse: 52 of 1,000 random ISBNs; 2 of 400 in the picture-book-publisher sample | Audience code present in about 6.5% of the picture-book sample; meaning not decoded | Cコード-style `Subject` entries in about 4 to 9%; no seasons | `series` and `title` collation key (reading) in some | Free to use to introduce books; no modification; no passing on; keep up to date |
| **Rakuten Books API** (JP) | Key: Rakuten ID, registered app, `applicationId` plus `accessKey` (d) | Y (d), `isbn` / `isbnjan` | Y (d), `title`, `author`, `publisherName`, `size=7` = picture book; fuzziness unverified | 64, 128 and 200 px only (d) | n, no age field in the output list (d) | `itemCaption` text; Rakuten genre ids (d) | `titleKana`, `authorKana`, `seriesName` (d) | Credit required; app must link Rakuten sites; quotas set per app (d) |
| **EhonNavi** (JP) | No API | n | n | n | On site, not via any API | Site has a season facet (observed in the page navigation) | n | Private use only; images may not be saved |
| **NK ČR catalogue via Z39.50** (CZ) | No key, free | Y, ISBN-10 and 13 | Y. Diacritics ignored except č š ř ž; no fuzzy matching; right truncation gave 0 in my try | n | **Y**: 008 audience band (a preschool, b primary, c pre-adolescent) in all 20 records of a recent sample, plus field 521 age note (for example `Pro děti od 2 let`) in 12 of those 20; none in the 1930s records except the 008 band | **Y**: 650 topical (`Vánoce`), 655 genre/form (`leporela`, `české pohádky`), 072 Konspekt | Y: 490 series, illustrator in 700 `$4 ill`, 520 summary | CC0 for NKC, SKC, CNB; credit to NK ČR requested |
| **Knihovny.cz** (CZ) | Unknown; scripts met a bot challenge | ? | ? | ? | ? | ? | ? | robots.txt: Crawl-delay 30, `/Search/Results` disallowed; software GPL-2.0 (the data licence is unverified) |
| **obalkyknih.cz** (CZ) | Registration of a library catalogue URL and IPs required | n for individuals (HTTP 404 "Unknown referer") | n | Y for registered libraries; 170x240 px (d) | n | annotations, contents scans (d) | n | Covers may not be stored permanently; backlink required (d) |
| **Databazeknih.cz** (CZ) | No API documented | n | n | Site only | not checked | not checked | n | Covers belong to publishers; no commercial use; not scraped |
| **Open Library** (EN, some JP) | No key; 1 req/s, 3 req/s with a User-Agent plus email (d) | Y, English and the Japanese ISBN; empty for my Czech ISBN | Y, but strict: a misspelled title and author gave 0; Japanese-script title gave 0 | Y, S/M/L jpeg for English and Japanese; none for Czech | n | Y: subjects such as `Juvenile fiction`, `Dreams`; folksonomy-like, no seasons | Partly | No new rights asserted by Open Library; do not use as a backend for high-traffic commercial services (d) |
| **Library of Congress SRU** (EN) | No key | Y | Y, word-based CQL; no fuzziness tested | n | 008 audience `j` (juvenile); no age in years seen | Y: 650 headings (`Caterpillars -- Fiction`), 520 summary | partial | Reuse licence not verified |
| **Google Books API** (EN) | Key required (d); keyless call returned 429 | ? | ? (d: complete words and same-stem words, not substrings) | `imageLinks` (d) | `maturityRating` only (d) | `categories` (d) | n | Google APIs terms; not read in depth |

## Notes per source

### NDL Search API (National Diet Library, Japan)

- **Documentation.** Search APIs are SRU, OpenSearch and OpenURL; harvesting is OAI-PMH. Base URLs `https://ndlsearch.ndl.go.jp/api/opensearch`, `/api/sru`, `/api/openurl`, `/api/oaipmh` ([API specification overview, 2026-10-05](https://ndlsearch.ndl.go.jp/help/api/specifications)).
- **Terms.** Non-commercial use that earns no revenue needs no application; commercial use needs an application unless the data provider has pre-approved it; credit to NDL Search is required; heavy continuous access may be blocked, and the concurrent request count is capped ([API usage page, 2026-10-05](https://ndlsearch.ndl.go.jp/help/api)). NDL's own bibliographies (`iss-ndl-opac` and related ids) are listed as CC BY ([provider list, 2026-10-05](https://ndlsearch.ndl.go.jp/help/api/provider)).
- **Covers are gone.** NDL announced that its cover API ends on 2026-03-31 after the JPRO terms changed ([notice, 2026-10-05](https://ndlsearch.ndl.go.jp/news/20251217)). Observed: `https://ndlsearch.ndl.go.jp/thumbnail/9784834000825.jpg` returned HTTP 403.

**ISBN lookup, exact request** (observed):

```
GET https://ndlsearch.ndl.go.jp/api/opensearch?isbn=9784893094315&dpid=iss-ndl-opac&cnt=2
```

Trimmed result (だるまさんが, Bronze Shinsha) ([response, 2026-10-05](https://ndlsearch.ndl.go.jp/api/opensearch?isbn=9784893094315&dpid=iss-ndl-opac&cnt=2)):

```
dc:title                だるまさんが
dcndl:titleTranscription ダルマサン ガ
dc:creator              加岳井, 広, 1955-2009   (reading カガクイ, ヒロシ)
dc:publisher            ブロンズ新社      dc:date 2008      dcndl:price 850円
dc:identifier ISBN      978-4-89309-431-5     NDLBibID 000009209109   JPNO 21350311
dcndl:genre             児童図書          dc:subject NDLC Y17 / NDC9 726.6
```

Without `dpid`, the same ISBN query for ぐりとぐら (9784834000825) returned 27 records and 66 KB; the first three were Sapie (braille library) records, repository `R100000038`. With `dpid=iss-ndl-opac` it returned 2 NDL records (observed).

**SRU with the `dcndl` schema adds an abstract and an audience** (observed):

```
GET https://ndlsearch.ndl.go.jp/api/sru?operation=searchRetrieve&query=isbn="9784893094315" AND dpid=iss-ndl-opac&maximumRecords=1&recordSchema=dcndl
→ dcterms:abstract  ページをめくるとかわいいだるまさんが勢揃い!…シリーズ第一弾(日本児童図書出版協会)
→ dcterms:audience  児童
→ dcndl:genre       児童図書   dcndl:price 850円
```

**Title plus author, and forgiveness** (observed):

| Request (`dpid=iss-ndl-opac`) | Result |
|---|---|
| `title=だるまさんが&creator=かがくいひろし` | 6 hits; the creator in kana matched the kanji authority 加岳井, 広 through its reading |
| `title=はらぺこあおむし&creator=エリック・カール` | 24 hits including 1976 and 1988 偕成社 editions; ranking is not by closeness (an exhibition catalogue came first) |
| `title=グリとグラ&creator=なかがわりえこ` (katakana title, kana author) | 93 hits; the first three were `ぐりとぐら` (an accessible-format edition), `ぐりとぐら絵はがきの本` and `ぐりとぐらかるた`, so katakana for hiragana is tolerated; I did not locate the main 福音館 edition among the three shown |
| `title=ぐりとぐろ&creator=中川李枝子` (one wrong kana) | 0 hits |
| `title=ぐりとぐら&creator=中川李技子` (one wrong kanji) | 0 hits |

Practical reading (AI-generated): the search is exact on characters but lenient on script, so retry with the author dropped, with the title in kana, and with the title shortened, then let the LLM choose between candidates.

**Operational note** (observed): my first request timed out at 30 s with nothing received; the next returned HTTP 429 `同時アクセス数の上限に達した` after 0.15 s; the third, after a 25 s pause, took 3.7 s. Serialise requests and retry with a pause.

**Fields**: title, reading, creators with readings, publisher, year, price, ISBN, genre, NDC and NDLC codes, `seriesTitle` with reading, links to library catalogue pages (observed in the items above). No age in years and no keyword subject headings in the picture-book records I saw.

### openBD (hanmoto.com and Calil)

- **Documentation.** `https://api.openbd.jp/v1/get?isbn=…` (comma-separated, up to 1,000 by GET and 10,000 by POST) and `/v1/coverage`; JSON ([API slides, 2026-10-05](https://openbd.jp/pdf/api20170123.pdf)). There is no search endpoint in the specification.
- **Terms.** Free; data may be used only to promote or introduce books; data may not be altered; individual records and covers must be removed on request; the right of use may not be passed on; cached data should follow updates ([openBD terms, 2026-10-05](https://openbd.jp/terms/)). The service is provided without warranty and may stop without notice (same page).

**ISBN lookup, exact request** (observed):

```
GET https://api.openbd.jp/v1/get?isbn=9784834000825
```

Trimmed result ([response, 2026-10-05](https://api.openbd.jp/v1/get?isbn=9784834000825)):

```
"summary": {"isbn":"9784834000825","title":"ぐりとぐら","volume":"","series":"",
            "publisher":"福音館書店","pubdate":"196701","cover":"","author":"中川,李枝子 大村,百合子"}
onix.TitleDetail  collationkey "グリ ト グラ"      onix.Contributor  collationkey "ナカガワ, リエコ"
onix.CollateralDetail  {}     (no description, no cover)
```

Observed coverage:

- `/v1/coverage` listed 1,940,259 ISBNs ([coverage, 2026-10-05](https://api.openbd.jp/v1/coverage)).
- Random sample of 1,000 covered ISBNs fetched by POST: 52 had a cover URL, 148 had text content, 87 had `Subject`, 135 had `Audience`.
- Sample of 400 ISBNs with the prefixes 978-4-834, 978-4-494, 978-4-893 (picture-book publishers, though the prefixes also include non-children's imprints): 2 covers, 24 with text, 15 `Subject`, 26 `Audience`. In a second, separate 500-record sample from the same prefixes, 47 records had an `Audience` entry, almost all `AudienceCodeType 22, AudienceCodeValue 00`; I did not decode it, and nothing in these records was an age in years.
- `Subject` entries use scheme `78` with a four-digit code (for example `8793`) (observed). This looks like the Japanese Cコード, whose first digit marks children's books, but the openBD material I fetched does not say so. **Unverified.** If correct, it identifies a children's picture book, not an age.
- ISBN count by prefix: 978-4-834 has 6,186 ISBNs, 978-4-033 only 159 ([coverage, 2026-10-05](https://api.openbd.jp/v1/coverage)). The 偕成社 ISBNs I tried (9784033290102, 9784033213804, both taken from NDL records) returned `null`. 偕成社 uses the 978-4-03 prefix in NDL records ([NDL result, 2026-10-05](https://ndlsearch.ndl.go.jp/api/opensearch?title=%E3%81%AF%E3%82%89%E3%81%BA%E3%81%93%E3%81%82%E3%81%8A%E3%82%80%E3%81%97&creator=%E3%82%A8%E3%83%AA%E3%83%83%E3%82%AF%E3%83%BB%E3%82%AB%E3%83%BC%E3%83%AB&dpid=iss-ndl-opac&cnt=5)), so はらぺこあおむし is not in openBD by these ISBNs.

### Rakuten Books API (not called: key required)

- **Access.** Needs a Rakuten account; register an app (name, URL, type, allowed websites, purpose of use, expected QPS); App ID and access key are issued per app, up to 5 apps per developer ([Usage guide, 2026-10-05](https://webservice.rakuten.co.jp/guide)). Requests need both `applicationId` and `accessKey` ([Book Search docs, 2026-10-05](https://webservice.rakuten.co.jp/documentation/books-book-search)). I created no account.
- **Endpoints.** `…/BooksBook/Search/20170404` (title, author, publisher, size, ISBN, genre), `…/BooksTotal/Search/20170404` (keyword or `isbnjan`), and a magazine search `…/BooksMagazine/Search/20170404` ([Book Search](https://webservice.rakuten.co.jp/documentation/books-book-search), [Total Search](https://webservice.rakuten.co.jp/documentation/books-total-search), [Magazine Search](https://webservice.rakuten.co.jp/documentation/books-magazine-search), all 2026-10-05).
- **Fields (documented).** `title`, `titleKana`, `subTitle`, `seriesName`, `author`, `authorKana`, `publisherName`, `size` (value 7 = picture book), `isbn`, `itemCaption`, `salesDate`, `itemPrice`, and images at 64, 128 and 200 px only. No age field ([Book Search output list, 2026-10-05](https://webservice.rakuten.co.jp/documentation/books-book-search)). The `size=7` picture-book filter is a useful narrowing; the Rakuten genre tree might include age bands, but **unverified** without a key.
- **Terms (documented).** Credit required; the app must link Rakuten sites in the parts that use the data; usage limits may be set per app; terms are subject to change ([Terms of service, 2026-10-05](https://webservice.rakuten.co.jp/guide/rule)). I did not find a stated per-second limit; the docs warn that repeated identical requests may be throttled ([Book Search, 2026-10-05](https://webservice.rakuten.co.jp/documentation/books-book-search)).
- **Fit.** A Rakuten key is the one documented source that offers a title and author search with kana readings and a picture-book filter in the Japanese market, but it adds an account, a mandatory branding link, and 200 px covers. AI-generated judgement: worth it only if NDL title search proves too strict in practice.

### EhonNavi (絵本ナビ), not called

- **No API** is published on the operator page I fetched; the Codex search found none either ([operator page, 2026-10-05](https://www.ehonnavi.net/home04.asp)).
- **Terms.** Information, images and the site structure belong to the company or its providers; members may not copy, publish or use anything obtained through the site beyond private personal use without approval; saving or redistributing cover and inside-page images by screenshot or download is expressly refused ([terms, 2026-10-05](https://www.ehonnavi.net/home04.asp)). Its robots.txt sets `Crawl-delay: 10` and blocks several paths ([robots.txt, 2026-10-05](https://www.ehonnavi.net/robots.txt)). Given the terms I did not fetch book pages.
- **Why it matters.** The home page navigation offers facets for 季節 (season), family, feelings and gifts (observed on the page above), so this is where Japanese seasonal and age curation lives. I did not check whether per-book pages state a target age, which is **unverified**. It remains a manual, by-hand reference for the family, not a data source.

### National Library of the Czech Republic over Z39.50

- **Documentation and terms.** The Aleph Z39.50 server is `aleph.nkp.cz` port `9991`, no login, UTF-8, USMARC, UNIMARC or Dublin Core XML. Bases include `NKC-UTF` (catalogue), `SKCM-UTF` (union catalogue, monographs), `CNB-UTF` (national bibliography), `AUT-UTF` (authorities). Use attribute 7 is ISBN, 4 title, 1003 author, 21 subject heading ([Z39.50 server page, 2026-10-05](http://aleph.nkp.cz/web/Z39_NK_cze.htm)). NKC, SKC, CNB and the authority file are CC0; crediting NK ČR is requested but not required. OAI-PMH `GetRecord` is not supported, so Z39.50 is the single-record route, and weekly full dumps are the bulk route ([Open data page, 2026-10-05](https://www.nkp.cz/o-knihovne/odborne-cinnosti/otevrena-data)).
- **How I called it.** `yaz-client` 5.31.1 from the Ubuntu `yaz` package, unpacked locally without root. Plain `curl` cannot speak Z39.50. The Aleph X-Server at `aleph.nkp.cz/X` answered HTTP 403 "access from this IP not allowed", and `aleph.nkp.cz/robots.txt` disallows crawling (both observed), so there is no HTTP search route I could use.

**ISBN lookup, exact session** (observed):

```
open aleph.nkp.cz:9991/NKC-UTF
find @attr 1=7 9788076392939
show 1+1
```

Trimmed result ([Z39.50 server, 2026-10-05](http://aleph.nkp.cz/web/Z39_NK_cze.htm)):

```
008  250318t20252025xr a   b      000 j cze        (position 22 = b, primary-school audience; position 33 = j, short stories)
020  $a 978-80-7639-293-9 $q (vázáno)
072  7 $a 821-93 $x Literatura pro děti a mládež (beletrie) $2 Konspekt
100 1 $a Karafiát, Jan, $d 1846-1929 $4 aut
245 10 $a Broučci / $c Jan Karafiát ; ilustrace Vlasta Švejdová
264  1 $a Ostrava : $b Bookmedia s.r.o., $c [2025]
655  7 $a české pohádky     655 7 $a publikace pro děti
700 1  $a Švejdová, Vlasta, $d 1946- $4 ill
```

**Title plus author with an age note** (observed):

```
find @and @attr 1=4 "Krtek a zajíček" @attr 1=1003 "Miler"      → 8 hits
008  240805s2024    xr a   a      000 j cze        (position 22 = a, preschool audience)
020  $a 978-80-242-9721-7        245 10 $a Krtek a zajíček / $c Zdeněk Miler
264  1 $a V Praze : $b Euromedia Group, a.s., $c 2024      300 $a 12 nečíslovaných stran : $b barevné ilustrace
490  1  $a Pikola                500 $a Kartonové listy
520  2  $a Příběh o Krtkovi, který tentokrát pomůže ztracenému zajíčkovi najít maminku.
521  8  $a Pro děti od 2 let
655  7 $a leporela     655 7 $a publikace pro děti     100 1 $a Miler, Zdeněk, 1921-2011 $4 aut $4 ill
```

**Forgiveness** (observed on `NKC-UTF`):

| Query | Hits |
|---|---|
| `Krtek a zajíček` + `Miler` | 8 |
| `Krtek a zajiček` (í without accent) + `Miler` | 8 (same record), because diacritics other than č š ř ž are ignored |
| `Brouci` or `Broucci` + `Karafiat` | 0 (č is significant; the right word is `Broučci`) |
| `Krtek a zajíček` + `Miller` (wrong author) | 0 |
| Right truncation with `@attr 5=1` and `Krtek a zaj` | 0 (truncation did not work in the form I tried) |
| `Povídání o pejskovi a kočičce` + `Čapek` | 108 hits; translations (Korean, Slovak) come before the Czech edition, so results need filtering by language (008 positions 35 to 37) |

**Age, season and subjects, sample** (observed): 32 hits for "Vánoce" plus "děti" published 2024; I pulled 20. In MARC 21 the 008 byte at position 22 is the target audience, with `a` preschool, `b` primary, `c` pre-adolescent, `g` general ([MARC 21 008 for books, 2026-10-05](https://www.loc.gov/marc/bibliographic/bd008b.html)). All 20 records had it: 8 `a`, 9 `b`, 1 `c`, 2 `g`. Of the 20, 12 also had an age note in field 521 (for example `Pro děti od 3 let`, `Pro děti 5-8 let`, `Pro čtenáře od 12 let`; six of the seven notes for ages 3 to 5 sat on `a` records, and the notes for ages 6 to 12 sat on `b` or `c` records), 10 had a 520 summary, 10 had a topical 650 heading (`Vánoce`, `vánoční zvyky`, `advent`) and all 20 had a 655 genre/form. The sample was drawn on a Christmas query, so it overstates how common 650 headings are across all books, and it is only 20 recent records. The 1930s Broučci edition had the 008 band (`b`) but no 521, no 650 and no ISBN, only 655, 072 and a digitised-copy link in 856.

**Older books without an ISBN** (observed): `@and @attr 1=4 "Broučci" @attr 1=1003 "Karafiát"` returned 163 hits including two 1930s editions with no ISBN (`020 $q (Vázáno)` only), publisher, an estimated date and the illustrator. The ISBN-10 `80-11-01711-X` for a 2000 Rumcajs school edition found one record (`NKC-UTF` and `SKCM-UTF`). `SKCM-UTF` returned a similar hit list for the Čapek query.

**Cover**: none; the only link in these records was a digitisation URL (856) on old books.

### Knihovny.cz (not usable by script)

- **Observed.** `GET https://www.knihovny.cz/api/v1/search?lookfor=…`, `/api`, `/Content/api` and `/api/v1/record?id=x` all returned HTTP 418 with a page titled "Ověřujeme, že nejste AI" (a proof-of-work challenge by the `go-away` filter) ([probe, 2026-10-05](https://www.knihovny.cz/api/v1/search?lookfor=test)). I did not try to solve it. A WebFetch of `/Content/api` timed out (HTTP 504).
- **Terms (documented).** `robots.txt` sets `Crawl-delay: 30` and disallows `/Search/Results` and a few AJAX and record-export paths ([robots.txt, 2026-10-05](https://www.knihovny.cz/robots.txt)). The portal is open-source VuFind software under GPL-2.0 ([repository, 2026-10-05](https://github.com/moravianlibrary/Knihovny.cz)). I did not find a data licence or API terms. **Unverified**: whether a documented public API exists. Most of its records come from the same national and union catalogues that Z39.50 already serves under CC0, so little is lost.

### obalkyknih.cz (Czech covers, annotations, contents)

- **Observed.** `GET https://cache.obalkyknih.cz/api/books?isbn=9788024297217` returned HTTP 404 with `Unknown referer. You need to sign up at http://www.obalkyknih.cz and provide your catalog URL`. `GET …/api/cover?isbn=9788024297217&type=medium&keywords=krtek` returned HTTP 404 ([probe, 2026-10-05](https://cache.obalkyknih.cz/api/books?isbn=9788024297217)).
- **Documented access.** The 2016 API manual (marked possibly out of date) says the metadata API needs the IP address of a registered library or library system, and covers need a registered catalogue URL (referer); fields include `cover_medium_url` (170x240), annotations, reviews and OCR'd contents; a backlink to obalkyknih.cz is mandatory ([API 3.1 manual, 2026-10-05](https://www.obalkyknih.cz/doc/Dokumentace_API_OKCZ_3.1.pdf)). Registration asks for a library SIGLA and a description of use (same manual).
- **Terms.** The project relies on the Czech copyright exception for libraries and non-profit educational institutions; free registration is a condition for libraries and similar institutions; covers may not be stored permanently on library servers because of agreements with publishers ([About and terms, 2026-10-05](https://www.obalkyknih.cz/about)). A family collection is not such an institution. Treat it as not available.

### Databazeknih.cz (not called as a source)

- No API is documented in the terms I read. The terms say annotations are mostly the publishers' official texts and covers are the publishers' property, and users may not use the portal for commercial purposes outside the book bazaar section ([terms, 2026-10-05](https://www.databazeknih.cz/podminky-uziti)). `robots.txt` blocks only `/user/`, `/admin/` and `/superadmin/` ([robots.txt, 2026-10-05](https://www.databazeknih.cz/robots.txt)).
- I made one fetch of the site's ISBN search page (`/search?q=9788024297217`, redirected to `/vyhledavani/knihy?q=…`); the returned HTML did not contain the book, so that check was inconclusive and I did not pursue it. I did not scrape. Whether book pages show age or tags: **unverified**.

### Open Library (English, plus partial Japanese)

- **Documentation and limits.** Open Library asks for a descriptive `User-Agent` with an email; default 1 request per second, 3 per second when identified; no HTML scraping; use `search.json` for batches; not for high-traffic commercial backends ([API usage guidelines, 2026-10-05](https://openlibrary.org/developers/api)). It asserts no new rights over its database; contributions may still carry existing rights ([licensing, 2026-10-05](https://openlibrary.org/developers/licensing)). I used a generic User-Agent without an email and one request per 1.2 s.

**ISBN lookup, exact request** (observed):

```
GET https://openlibrary.org/api/books?bibkeys=ISBN:9780060254926&format=json&jscmd=data
```

Trimmed result ([response, 2026-10-05](https://openlibrary.org/api/books?bibkeys=ISBN:9780060254926&format=json&jscmd=data)):

```
title   Where The Wild Things Are by Maurice Sendak (Special Edition, 1 Jan 1967) Hardcover
authors Maurice Sendak     publishers Bodley Head    publish_date 1967
subjects Caldecott Medal, Dreams, Fantasy, Fiction, Imagination, Juvenile fiction, Monsters …
cover   https://covers.openlibrary.org/b/id/14827178-L.jpg   (also -S and -M)
```

Other observations: The Very Hungry Caterpillar (9780399226908) came back with subjects `Children's fiction`, `Caterpillars, fiction`, `Toy and movable books` but no cover; the Japanese ISBN of ぐりとぐら (9784834000825) came back as `Guri and Gura` by `Nakagawa Rieko`, publisher `Fukuinkan-shoten`, subjects `Cake, Mice, Eggs, Fiction` and a cover; the Czech ISBN 9788024297217 returned empty. Cover URL check: `https://covers.openlibrary.org/b/isbn/9784834000825-M.jpg?default=false` and the Wild Things ISBN returned HTTP 200 `image/jpeg`; the Czech ISBN returned 404.

**Title plus author and forgiveness** (observed):

| `search.json` parameters | Result |
|---|---|
| `title=Where the Wild Things Are&author=Sendak` | 5 hits; first is the right work, with a cover id and subjects |
| `title=Where the Wild Thing Are&author=Sendack` (two typos) | 0 |
| `title=Brown Bear, Brown Bear, What Do You See?&author=Bill Martin` | 6 hits; right work first |
| `title=ぐりとぐら` | 0 (records are romanised) |
| `title=Krtek a zajíček&author=Miler` | 0 |
| `title=Broučci&author=Karafiát` | 4 hits, Czech editions, no cover and no subjects |

No target age field exists in the records returned.

### Library of Congress SRU (English)

- **Documentation.** The LoC lists SRU servers for its catalogue and authority files ([SRU page, 2026-10-05](https://www.loc.gov/apis/additional-apis/search-retrieve-via-url/)). I called `https://lx2.loc.gov/sru/lcdb` with CQL (`bath.isbn`, `bath.title`, `bath.author`) and `recordSchema=marcxml`, no key. Rate limits and a reuse licence for catalogue records: **unverified**; I did not find them on the page I read.

**ISBN lookup, exact request** (observed):

```
GET https://lx2.loc.gov/sru/lcdb?version=1.1&operation=searchRetrieve&query=bath.isbn%3D9780060254926&maximumRecords=1&recordSchema=marcxml
```

Trimmed result ([response, 2026-10-05](https://lx2.loc.gov/sru/lcdb?version=1.1&operation=searchRetrieve&query=bath.isbn%3D9780060254926&maximumRecords=1&recordSchema=marcxml)):

```
2 records.  008  161208s2013    nyu           000 0 eng d
020 $a 9780060254926     100 $a Sendak, Maurice.
245 $a Where the wild things are / $c story and pictures by Maurice Sendak.   250 $a 50th anniversary ed.
260 $a New York : $b HarperCollins, $c 2013.     650 $a Monsters $v Fiction.     655 $a Fiction. $2 lcgft
```

The query `bath.title="very hungry caterpillar" and bath.author=carle` returned 96 records; one 1979 record has a `520` summary ("Follows the progress of a hungry little caterpillar…") and headings `Caterpillars -- Fiction` and `Toy and movable books`; the 1979 Caterpillar record and a 1988 Wild Things record (from the title query) carry audience code `j` (juvenile) in 008 position 22, while the 2013 Wild Things anniversary edition (from the ISBN lookup) leaves it blank ([MARC 21 008 codes, 2026-10-05](https://www.loc.gov/marc/bibliographic/bd008b.html)). No age in years and no cover appeared in the records I printed (print restricted to selected fields).

### Google Books API (key required)

- **Observed.** A keyless `GET https://www.googleapis.com/books/v1/volumes?q=isbn:9780060254926` returned HTTP 429 with `Quota exceeded for quota metric 'Queries' and limit 'Queries per day'` and `quota_limit_value: "0"` ([probe, 2026-10-05](https://www.googleapis.com/books/v1/volumes?q=isbn:9780060254926)); ten further keyless calls (ISBN and title, three languages) failed the same way, so I have **no observed Google Books data**.
- **Documented.** Public-data requests must carry an API key or OAuth token; a key comes from the Cloud Console credentials page as "Create credentials > API key"; search matches complete words and same-stem words, not substrings; exact phrases in quotes ([Using the API, 2026-10-05](https://developers.google.com/books/docs/v1/using)). From general knowledge (not checked here): `volumeInfo` has `categories`, `maturityRating` and `imageLinks`. **Unverified** for Japanese and Czech picture books and for terms on reusing covers.

### Magazines without an ISBN, and other gaps

- **Japanese monthly picture-book magazines.** In NDL, the magazine title is a serial-level record (`こどものとも`, publisher 福音館書店, category 雑誌, genre 児童雑誌, class `ZY1`, `NDLBibID 000000029662`), and the individual stories appear as separate records. A query for the magazine name with `dpid=iss-ndl-opac` returned only the serial-level record repeated; without `dpid`, `title=こどものとも年少版&from=2025` returned story-level article records (for example `あさのどうぶつえん`, series `こどものとも年少版 ; 575号`) from NDL articles and from NII ([observed 1](https://ndlsearch.ndl.go.jp/api/opensearch?title=%E3%81%93%E3%81%A9%E3%82%82%E3%81%AE%E3%81%A8%E3%82%82%E5%B9%B4%E5%B0%91%E7%89%88&from=2025&dpid=iss-ndl-opac&cnt=4), [observed 2](https://ndlsearch.ndl.go.jp/api/opensearch?title=%E3%81%93%E3%81%A9%E3%82%82%E3%81%AE%E3%81%A8%E3%82%82%E5%B9%B4%E5%B0%91%E7%89%88&from=2025&cnt=4), 2026-10-05). A 1998 issue appeared as `あー あった（こどものとも年少版１９９８年１１月号）`. AI-generated conclusion: look these up by **story title** as the LLM reads it from the cover, add the magazine name and the issue only to narrow it, and accept that the magazine code is not searchable.
- **雑誌コード.** The JPO magazine-code registry is a web search system (`magcode.jpo.or.jp`) whose rows hold code, type, status, title, publisher and price ([registry page, 2026-10-05](https://magcode.jpo.or.jp/code/magcode-manage/decision)). I did not find an API and did not test a code lookup. Rakuten has a magazine search by title and publisher (documented, not called).
- **Czech books without an ISBN** are in the national and union catalogues (see the Z39.50 section); coverage of really old or obscure picture books beyond what I sampled is **unverified**.
- **Not tested.** Wikidata and Wikipedia SPARQL; CiNii Books; ISBNdb (paid); Amazon Product Advertising API (needs an associate account); Calil (library holdings, not metadata); Czech retailers and publishers (no public APIs found by the Codex search); NDL Ngram (OCR full text, not catalogue data).

## Observations that shape the design (AI-generated synthesis)

- A title read from a photo is rarely an exact string. All free searches were exact on characters, so use a candidate-then-rank step: retrieve with the author alone or a shortened title, let the LLM compare titles and years, and accept or ask a person. This is the same flow for Japanese, Czech and English.
- ISBN barcodes are the reliable path: NDL, openBD, Z39.50 and Open Library all answered ISBN lookups, including old 10-digit ISBNs.
- Season and age are the weakest fields. A practical split: take the Czech audience band, age note and subject headings from the NK ČR record when present; for Japanese and English books, derive age and season from the abstract (NDL SRU abstract, LoC 520, Rakuten `itemCaption`) and the cover photo by LLM, and store them as the family's own tags, as the project's open questions already anticipate.
- Cover images: the family's own photos are the dependable image; the free cover sources (Open Library for English and a few Japanese titles, openBD for a few percent) are a bonus whose reuse terms are restrictive.

## Sources

- [NDL Search, API usage](https://ndlsearch.ndl.go.jp/help/api), [API specification overview](https://ndlsearch.ndl.go.jp/help/api/specifications), [provider list](https://ndlsearch.ndl.go.jp/help/api/provider), [cover API end notice](https://ndlsearch.ndl.go.jp/news/20251217), all 2026-10-05.
- [openBD terms](https://openbd.jp/terms/), [openBD API slides](https://openbd.jp/pdf/api20170123.pdf), [openBD coverage list](https://api.openbd.jp/v1/coverage), all 2026-10-05.
- [Rakuten Books Book Search](https://webservice.rakuten.co.jp/documentation/books-book-search), [Total Search](https://webservice.rakuten.co.jp/documentation/books-total-search), [Magazine Search](https://webservice.rakuten.co.jp/documentation/books-magazine-search), [usage guide](https://webservice.rakuten.co.jp/guide), [terms of service](https://webservice.rakuten.co.jp/guide/rule), all 2026-10-05.
- [EhonNavi operator page and terms](https://www.ehonnavi.net/home04.asp), [EhonNavi robots.txt](https://www.ehonnavi.net/robots.txt), both 2026-10-05.
- [JPO magazine code registry](https://magcode.jpo.or.jp/code/magcode-manage/decision), 2026-10-05.
- [NK ČR open data](https://www.nkp.cz/o-knihovne/odborne-cinnosti/otevrena-data), [NK ČR Z39.50 server](http://aleph.nkp.cz/web/Z39_NK_cze.htm), both 2026-10-05.
- [Knihovny.cz robots.txt](https://www.knihovny.cz/robots.txt), [Knihovny.cz repository](https://github.com/moravianlibrary/Knihovny.cz), both 2026-10-05.
- [obalkyknih.cz API 3.1 manual](https://www.obalkyknih.cz/doc/Dokumentace_API_OKCZ_3.1.pdf), [obalkyknih.cz about and terms](https://www.obalkyknih.cz/about), [obalkyknih.cz for developers](https://w.obalkyknih.cz/for_developers), all 2026-10-05.
- [Databazeknih.cz terms](https://www.databazeknih.cz/podminky-uziti), [Databazeknih.cz robots.txt](https://www.databazeknih.cz/robots.txt), both 2026-10-05.
- [Open Library API guidelines](https://openlibrary.org/developers/api), [Open Library licensing](https://openlibrary.org/developers/licensing), both 2026-10-05.
- [Library of Congress SRU](https://www.loc.gov/apis/additional-apis/search-retrieve-via-url/), [MARC 21 008 for books](https://www.loc.gov/marc/bibliographic/bd008b.html), both 2026-10-05.
- [Google Books API, using the API](https://developers.google.com/books/docs/v1/using), 2026-10-05.
- Discovery of candidate URLs: three read-only Codex jobs (`gpt-6-luna`, medium effort), 2026-10-05. Every URL above was fetched and read by the Claude subagent; the Codex output itself is not cited as evidence.
