from home_library.lookup import nkcr


def test_nkcr_by_isbn_returns_the_candidate_in_the_contract_shape(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_isbn_9788024297217.txt").decode("utf-8"))

    candidates = nkcr.by_isbn("9788024297217", run)

    assert candidates == [
        {
            "id": "nkcr:nkc20233578648",
            "source": "nkcr",
            "source_id": "nkc20233578648",
            "url": "",
            "title": "Krtek a zajíček",
            "title_reading": "",
            "authors": ["Miler, Zdeněk, 1921-2011 (author, illustrator)"],
            "publisher": "Euromedia Group, a.s.",
            "year": "2024",
            "isbn": "9788024297217",
            "series": "Pikola",
            "language": "cs",
            "audience": "preschool",
            "age_note": "Pro děti od 2 let",
            "subjects": [
                "české příběhy", "leporela", "publikace pro děti",
                "Czech stories", "folding picture-books", "children's literature",
            ],
            "summary": "Příběh o Krtkovi, který tentokrát pomůže ztracenému zajíčkovi najít maminku.",
        }
    ]


def test_nkcr_by_isbn_sends_an_isbn_search_to_the_catalogue_database(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_empty.txt").decode("utf-8"))

    nkcr.by_isbn("9788024297217", run)

    assert run.lines() == [
        "open aleph.nkp.cz:9991/NKC-UTF",
        "format usmarc",
        'find @attr 1=7 "9788024297217"',
        "show 1+10",
        "quit",
    ]
