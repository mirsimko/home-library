from home_library.lookup import ndl


def test_ndl_by_isbn_returns_the_candidate_in_the_contract_shape(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("ndl_isbn_9784893094315.xml"))

    candidates = ndl.by_isbn("9784893094315", fetch)

    assert candidates[0] == {
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
        "summary": "",
    }
