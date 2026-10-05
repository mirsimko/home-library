# Lookup fixtures

Small files that the look-up tests feed to the parsers. Tests never touch the network.

| File | Origin |
|---|---|
| `ndl_*.xml` | Real NDL Search OpenSearch responses recorded on 2026-10-05 for public books (だるまさんが), trimmed to the fields the parser reads. NDL's own bibliographies are CC BY. |
| `openlibrary_*.json` | Real Open Library responses recorded on 2026-10-05 (Where the Wild Things Are), trimmed. |
| `nkcr_*.txt` | Real `yaz-client` output from the NK CR catalogue (CC0) recorded on 2026-10-05, trimmed to the MARC lines the parser reads. `nkcr_isbn_broucci.txt` is reconstructed by hand from the record shown in docs/research/book-metadata-sources.md, because only the trimmed record was kept there. |
| `openbd_*.json` | **Hand-made**, not a recording. openBD's terms forbid passing its data on, so only the documented response shape is imitated, with an invented book and an invented ISBN. |
| `loc_*.xml` | **Hand-made**, not a recording. The reuse terms of Library of Congress catalogue records are unverified, so only the documented MARCXML shape is imitated, with an invented book and an invented ISBN. |
