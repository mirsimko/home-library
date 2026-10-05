import subprocess

import pytest

from home_library.lookup import nkcr
from home_library.lookup.errors import SourceError, Unavailable


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


def test_nkcr_search_sends_title_and_author_and_returns_every_record(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_search_krtek_miler.txt").decode("utf-8"))

    candidates = nkcr.search("Krtek a zajíček", "Miler", run)

    assert run.lines()[2] == 'find @and @attr 1=4 "Krtek a zajíček" @attr 1=1003 "Miler"'
    assert [c["id"] for c in candidates] == [
        "nkcr:nkc20233578648", "nkcr:nkc20162777681", "nkcr:zpk20142614070",
    ]
    assert candidates[1]["age_note"] == "Pro děti od dvou let"
    assert candidates[1]["publisher"] == "Knižní klub"
    assert candidates[1]["audience"] == "preschool"
    assert candidates[1]["year"] == "2016"


def test_nkcr_search_without_an_author_searches_the_title_alone(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_empty.txt").decode("utf-8"))

    nkcr.search("Krtek a zajíček", None, run)

    assert run.lines()[2] == 'find @attr 1=4 "Krtek a zajíček"'


def test_nkcr_quotes_the_title_so_it_cannot_inject_a_yaz_command(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_empty.txt").decode("utf-8"))

    nkcr.search('Say "Hi"\nopen evil.example:210/x', 'Back\\slash', run)

    assert len(run.lines()) == 5
    assert run.lines()[2] == (
        'find @and @attr 1=4 "Say \\"Hi\\" open evil.example:210/x" @attr 1=1003 "Back\\\\slash"'
    )
    assert run.lines()[0] == "open aleph.nkp.cz:9991/NKC-UTF"


def test_nkcr_raises_when_the_server_refuses_the_search(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_search_failed.txt").decode("utf-8"))

    with pytest.raises(SourceError):
        nkcr.by_isbn("9788024297217", run)


def test_nkcr_raises_when_yaz_client_printed_nothing_useful(fake_yaz):
    with pytest.raises(SourceError):
        nkcr.search("Krtek a zajíček", None, fake_yaz("Z> Connecting...Unable to connect\n"))


def test_nkcr_reads_illustrator_primary_audience_year_in_brackets_and_subject_subdivisions(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_isbn_broucci.txt").decode("utf-8"))

    [candidate] = nkcr.by_isbn("9788076392939", run)

    assert candidate["title"] == "Broučci"
    assert candidate["authors"] == ["Karafiát, Jan, 1846-1929", "Švejdová, Vlasta, 1946- (illustrator)"]
    assert candidate["publisher"] == "Bookmedia s.r.o."
    assert candidate["year"] == "2025"
    assert candidate["isbn"] == "9788076392939"
    assert candidate["audience"] == "primary"
    assert candidate["language"] == "cs"
    assert candidate["age_note"] == ""
    assert candidate["subjects"] == [
        "podzim", "světlušky -- pohádky", "české pohádky", "publikace pro děti",
    ]


def test_nkcr_reads_a_translation_without_taking_added_entries_for_authors(fake_yaz, fixture_bytes):
    run = fake_yaz(fixture_bytes("nkcr_search_krtek_miler.txt").decode("utf-8"))

    chinese = nkcr.search("Krtek a zajíček", "Miler", run)[2]

    assert chinese["language"] == "zh"
    assert chinese["title"] == "Yan shu de gu shi : jing dian ban"
    assert chinese["authors"] == ["Miler, Zdeněk, 1921-2011 (author, illustrator)"]
    assert chinese["isbn"] == "9787544825870"
    assert chinese["year"] == ""
    assert chinese["publisher"] == ""


class FakeSubprocess:
    """Replaces subprocess.run, the boundary to the yaz-client program."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(args, 0, stdout=self.result, stderr="")


def test_run_yaz_client_feeds_the_commands_to_yaz_client_and_returns_its_output(monkeypatch):
    fake = FakeSubprocess(result="Z> Connecting...OK.\n")
    monkeypatch.setattr(subprocess, "run", fake)

    output = nkcr.run_yaz_client("open x\nquit\n")

    assert output == "Z> Connecting...OK.\n"
    args, kwargs = fake.calls[0]
    assert args == ["yaz-client"]
    assert kwargs["input"] == "open x\nquit\n"
    assert kwargs["timeout"] > 0


def test_run_yaz_client_reports_a_missing_program_as_unavailable(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeSubprocess(error=FileNotFoundError("yaz-client")))

    with pytest.raises(Unavailable):
        nkcr.run_yaz_client("quit\n")


def test_run_yaz_client_reports_a_timeout_as_a_source_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeSubprocess(error=subprocess.TimeoutExpired("yaz-client", 60)))

    with pytest.raises(SourceError):
        nkcr.run_yaz_client("quit\n")


def test_a_search_with_hits_whose_records_cannot_be_retrieved_is_a_source_error(fake_yaz):
    output = (
        "Z> Sent searchRequest.\nReceived SearchResponse.\nSearch was a success.\n"
        "Number of hits: 1, setno 1\nrecords returned: 0\nZ> Sent presentRequest (1+10).\n"
        "Target closed connection\n"
    )

    with pytest.raises(SourceError):
        nkcr.by_isbn("9788024297217", fake_yaz(output))
