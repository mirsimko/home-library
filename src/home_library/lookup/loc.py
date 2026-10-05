"""Library of Congress catalogue over SRU, answered as MARCXML."""
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from home_library.lookup.errors import SourceError
from home_library.lookup.marc import candidate_from_marc

BASE = "https://lx2.loc.gov/sru/lcdb"
MARC = "{http://www.loc.gov/MARC21/slim}"
SRU = "{http://www.loc.gov/zing/srw/}"


def _record(element):
    control = {c.get("tag"): (c.text or "") for c in element.findall(MARC + "controlfield")}
    fields = []
    for field in element.findall(MARC + "datafield"):
        subfields = [(s.get("code"), s.text or "") for s in field.findall(MARC + "subfield")]
        fields.append((field.get("tag"), field.get("ind1"), field.get("ind2"), subfields))
    return {"control": control, "fields": fields}


def _candidate(element):
    record = _record(element)
    lccn = ""
    for tag, _, _, subfields in record["fields"]:
        if tag == "010" and subfields:
            lccn = subfields[0][1].strip()
            break
    return candidate_from_marc("loc", record, url="https://lccn.loc.gov/" + lccn if lccn else "")


def _query(cql, fetch):
    params = {
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": cql,
        "maximumRecords": 10,
        "recordSchema": "marcxml",
    }
    root = ET.fromstring(fetch(BASE + "?" + urlencode(params)))
    if root.tag != SRU + "searchRetrieveResponse":
        raise SourceError("loc: the answer is not an SRU response")
    if any(node.tag.endswith("}diagnostic") for node in root.iter()):
        raise SourceError("loc: the SRU response carries a diagnostic")
    return [_candidate(r) for r in root.iter(MARC + "record")]


def by_isbn(isbn, fetch):
    return _query("bath.isbn=" + isbn, fetch)


def _quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def search(title, author, fetch):
    cql = "bath.title=" + _quote(title)
    if author:
        cql += " and bath.author=" + _quote(author)
    return _query(cql, fetch)
