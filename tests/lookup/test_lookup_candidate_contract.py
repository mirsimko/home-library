"""Every source gives candidates that keep the contract of docs/pipeline.md, however sparse or null the record is."""
import json

from home_library.lookup import loc, ndl, nkcr, openbd, openlibrary
from home_library.lookup.candidate import FIELD_ORDER, LIST_FIELDS, new_candidate


def assert_contract(candidate):
    assert set(candidate) == {"id", "source", "source_id", *FIELD_ORDER}
    for name, value in candidate.items():
        if name in LIST_FIELDS:
            assert isinstance(value, list) and all(isinstance(member, str) for member in value), name
        else:
            assert isinstance(value, str), name
            assert value != "None", name


def test_a_candidate_has_empty_text_and_empty_lists_for_null_values():
    candidate = new_candidate(
        "openlibrary", "OL1W", title=None, year=None, authors=None, subjects=None, summary=None
    )

    assert candidate["title"] == ""
    assert candidate["year"] == ""
    assert candidate["summary"] == ""
    assert candidate["authors"] == []
    assert candidate["subjects"] == []
    assert_contract(candidate)


def test_a_candidate_drops_null_and_non_string_members_of_its_lists_and_keeps_the_rest():
    candidate = new_candidate(
        "openlibrary", "OL1W", authors=["Anna Kovář", None, 7, "The Blue Kite"], subjects=[None, "Draci"]
    )

    assert candidate["authors"] == ["Anna Kovář", "The Blue Kite"]
    assert candidate["subjects"] == ["Draci"]


def test_a_number_given_for_a_text_field_becomes_its_text():
    assert new_candidate("openlibrary", "OL1W", year=1963)["year"] == "1963"


def test_open_library_search_with_null_values_gives_empty_fields(fake_fetch):
    body = json.dumps(
        {"docs": [{"key": "/works/OL9W", "title": None, "author_name": None, "first_publish_year": None, "subject": None}]}
    ).encode("utf-8")

    [candidate] = openlibrary.search("Zelený drak", None, fake_fetch(body))

    assert candidate["id"] == "openlibrary:OL9W"
    assert candidate["authors"] == []
    assert candidate["year"] == ""
    assert candidate["subjects"] == []
    assert candidate["title"] == ""
    assert_contract(candidate)


def test_open_library_search_with_nothing_but_a_title_gives_empty_fields(fake_fetch):
    body = json.dumps({"docs": [{"title": "The Blue Kite"}]}).encode("utf-8")

    [candidate] = openlibrary.search("The Blue Kite", None, fake_fetch(body))

    assert candidate["title"] == "The Blue Kite"
    assert_contract(candidate)


def test_open_library_by_isbn_with_null_values_gives_empty_fields(fake_fetch):
    body = json.dumps(
        {
            "ISBN:9780123456786": {
                "key": None, "url": None, "title": None, "authors": None, "publishers": None,
                "publish_date": None, "subjects": None,
            }
        }
    ).encode("utf-8")

    [candidate] = openlibrary.by_isbn("9780123456786", fake_fetch(body))

    assert candidate["authors"] == []
    assert candidate["publisher"] == ""
    assert candidate["year"] == ""
    assert candidate["subjects"] == []
    assert candidate["isbn"] == "9780123456786"
    assert_contract(candidate)


def test_open_library_by_isbn_drops_null_names_and_publishers(fake_fetch):
    body = json.dumps(
        {
            "ISBN:9780123456786": {
                "key": "/books/OL5M", "title": "The Blue Kite",
                "authors": [{"name": None}, {"name": "Anna Kovář"}, {}],
                "publishers": [{"name": None}],
                "subjects": [{"name": None}, {"name": "Kites"}],
            }
        }
    ).encode("utf-8")

    [candidate] = openlibrary.by_isbn("9780123456786", fake_fetch(body))

    assert candidate["authors"] == ["Anna Kovář"]
    assert candidate["publisher"] == ""
    assert candidate["subjects"] == ["Kites"]
    assert_contract(candidate)


def test_openbd_with_null_values_gives_empty_fields(fake_fetch):
    body = json.dumps(
        [{"summary": {"isbn": "9784001111118", "title": None, "author": None, "publisher": None,
                      "pubdate": None, "series": None}, "onix": None}]
    ).encode("utf-8")

    [candidate] = openbd.by_isbn("9784001111118", fake_fetch(body))

    assert candidate["authors"] == []
    assert candidate["year"] == ""
    assert candidate["summary"] == ""
    assert_contract(candidate)


def test_openbd_with_an_empty_summary_gives_empty_fields(fake_fetch):
    [candidate] = openbd.by_isbn("9784001111118", fake_fetch(b'[{"summary": {}, "onix": {}}]'))

    assert candidate["source_id"] == ""
    assert candidate["year"] == ""
    assert_contract(candidate)


def test_ndl_with_a_bare_item_gives_empty_fields(fake_fetch):
    body = b'<rss version="2.0"><channel><item><title/></item></channel></rss>'

    [candidate] = ndl.search("あかいふうせん", None, fake_fetch(body))

    assert candidate["authors"] == []
    assert candidate["subjects"] == []
    assert_contract(candidate)


def test_loc_with_a_bare_record_gives_empty_fields(fake_fetch):
    body = (
        b'<zs:searchRetrieveResponse xmlns:zs="http://www.loc.gov/zing/srw/"><zs:records><zs:record>'
        b'<zs:recordData><record xmlns="http://www.loc.gov/MARC21/slim">'
        b'<datafield tag="245" ind1="1" ind2="0"/><datafield tag="100" ind1="1"/>'
        b'<datafield tag="010"/><datafield tag="520"><subfield code="a"/></datafield>'
        b"</record></zs:recordData></zs:record></zs:records></zs:searchRetrieveResponse>"
    )

    [candidate] = loc.search("The Blue Kite", None, fake_fetch(body))

    assert candidate["title"] == ""
    assert candidate["authors"] == []
    assert_contract(candidate)


def test_nkcr_with_a_bare_record_gives_empty_fields(fake_yaz):
    output = (
        "Search was a success.\nNumber of hits: 1, setno 1\n"
        "[NKC-UTF]Record type: USmarc\n"
        "245 10 $a\n100 1  \n650  7 \n"
    )

    [candidate] = nkcr.search("Zelený drak", None, fake_yaz(output))

    assert candidate["title"] == ""
    assert candidate["authors"] == []
    assert candidate["subjects"] == []
    assert_contract(candidate)
