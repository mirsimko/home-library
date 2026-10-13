"""Exports preserve catalogue text and spreadsheet-safe UTF-8 CSV."""
import csv
from contextlib import closing
from io import StringIO

from store_helpers import CAPTURE_ID, SECOND_ID, finish, record
from web_helpers import client as client

from home_library import store


def test_exports_keep_capture_provenance_and_escape_csv_formula_prefixes(client, tmp_path):
    with closing(store.open(tmp_path)) as db:
        cover = finish(db, [record("=ぐぽ")], kind="cover")
        barcode = finish(db, [record("", read_status="barcode")], SECOND_ID, kind="barcode")
        store.approve(db, [cover[0]["id"], barcode[0]["id"]], {"notes": "+Invented note"}, "parent")
        for index, prefix in enumerate(["-", "@", "\t", "\r"]):
            store.add_book(db, {"title": f"Paper Moon {index}", "location_id": 1, "notes": prefix + "note"}, "parent")
        expected = store.export_rows(db)
    response = client.get("/export.json")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["capture_ids"] == [CAPTURE_ID, SECOND_ID]
    assert all(row["capture_ids"] == [] for row in rows[1:])
    assert [{key: value for key, value in row.items() if key != "capture_ids"} for row in rows] == expected
    response = client.get("/export.csv")
    assert response.status_code == 200 and response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    reader = csv.DictReader(StringIO(response.content.decode("utf-8-sig"), newline=""))
    csv_rows = list(reader)
    assert reader.fieldnames == list(expected[0])
    assert csv_rows[0]["title"] == "'=ぐぽ" and csv_rows[0]["notes"] == "'+Invented note"
    assert [row["notes"] for row in csv_rows[1:]] == ["'-note", "'@note", "'\tnote", "'\rnote"]
    assert csv_rows[0]["age_from"] == "" and csv_rows[0]["needs_review"] == "false"
    assert csv_rows[0]["cover_photo"] == f"captures/{CAPTURE_ID}.jpg"


def test_an_empty_catalogue_still_exports_csv_column_names(client):
    assert client.get("/export.json").json() == []
    response = client.get("/export.csv")
    assert response.status_code == 200
    header = response.content.decode("utf-8-sig").strip()
    assert header.startswith("title,sort_key,author,") and header.endswith(",source,source_id,needs_review,notes")
