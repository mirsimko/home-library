from home_library.lookup import openlibrary


def test_open_library_by_isbn_returns_the_candidate_in_the_contract_shape(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("openlibrary_isbn_9780060254926.json"))

    candidates = openlibrary.by_isbn("9780060254926", fetch)

    assert candidates == [
        {
            "id": "openlibrary:OL46918311M",
            "source": "openlibrary",
            "source_id": "OL46918311M",
            "url": "http://openlibrary.org/books/OL46918311M/Where_The_Wild_Things_Are_by_Maurice_Sendak_(Special_Edition_1_Jan_1967)_Hardcover",
            "title": "Where The Wild Things Are by Maurice Sendak (Special Edition, 1 Jan 1967) Hardcover",
            "title_reading": "",
            "authors": ["Maurice Sendak"],
            "publisher": "Bodley Head",
            "year": "1967",
            "isbn": "9780060254926",
            "series": "",
            "language": "",
            "audience": "",
            "age_note": "",
            "subjects": [
                "Caldecott Medal", "Dreams", "Fantasy", "Fantasy fiction", "Fiction",
                "Imagination", "Juvenile fiction", "Miniature books", "Monsters", "Specimens",
            ],
            "summary": "",
        }
    ]
    assert fetch.urls[0].startswith("https://openlibrary.org/api/books?")
    assert fetch.query()["bibkeys"] == "ISBN:9780060254926"
    assert fetch.query()["jscmd"] == "data"
    assert fetch.query()["format"] == "json"
