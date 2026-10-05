from home_library.lookup import loc


def test_loc_by_isbn_returns_the_candidate_in_the_contract_shape(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("loc_isbn_9780123456786.xml"))

    candidates = loc.by_isbn("9780123456786", fetch)

    assert candidates == [
        {
            "id": "loc:2099001234",
            "source": "loc",
            "source_id": "2099001234",
            "url": "https://lccn.loc.gov/2099001234",
            "title": "The blue kite",
            "title_reading": "",
            "authors": ["Novak, Jana", "Ito, Ken (illustrator)"],
            "publisher": "Birch Books",
            "year": "2020",
            "isbn": "9780123456786",
            "series": "Kite stories",
            "language": "en",
            "audience": "juvenile",
            "age_note": "",
            "subjects": ["Kites -- Fiction", "Toy and movable books", "Picture books"],
            "summary": "A girl follows her blue kite over the roofs of the town.",
        }
    ]
    assert fetch.urls[0].startswith("https://lx2.loc.gov/sru/lcdb?")
    assert fetch.query()["query"] == "bath.isbn=9780123456786"
    assert fetch.query()["operation"] == "searchRetrieve"
    assert fetch.query()["recordSchema"] == "marcxml"


def test_loc_search_asks_for_title_and_author_in_cql(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("loc_isbn_9780123456786.xml"))

    candidates = loc.search("The Blue Kite", "Novak", fetch)

    assert fetch.query()["query"] == 'bath.title="The Blue Kite" and bath.author="Novak"'
    assert [c["id"] for c in candidates] == ["loc:2099001234"]


def test_loc_search_without_an_author_asks_for_the_title_alone(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("loc_isbn_9780123456786.xml"))

    loc.search("The Blue Kite", None, fetch)

    assert fetch.query()["query"] == 'bath.title="The Blue Kite"'


def test_loc_search_escapes_quotes_so_a_title_cannot_change_the_query(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("loc_isbn_9780123456786.xml"))

    loc.search('Say "Hi" or bath.author=x', None, fetch)

    assert fetch.query()["query"] == 'bath.title="Say \\"Hi\\" or bath.author=x"'
