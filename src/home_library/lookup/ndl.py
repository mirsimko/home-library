"""NDL Search (National Diet Library, Japan) through its OpenSearch API."""
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from home_library.lookup.errors import SourceError

BASE = "https://ndlsearch.ndl.go.jp/api/opensearch"
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
XSI_TYPE = "{%s}type" % NS["xsi"]


def _text(item, path):
    node = item.find(path, NS)
    return (node.text or "").strip() if node is not None else ""


def _identifier(item, kind):
    for node in item.findall("dc:identifier", NS):
        if node.get(XSI_TYPE) == "dcndl:" + kind:
            return (node.text or "").strip()
    return ""


def _candidate(item):
    source_id = _identifier(item, "NDLBibID")
    return {
        "id": "ndl:" + source_id,
        "source": "ndl",
        "source_id": source_id,
        "url": _text(item, "link"),
        "title": _text(item, "dc:title"),
        "title_reading": _text(item, "dcndl:titleTranscription"),
        "authors": [(n.text or "").strip() for n in item.findall("dc:creator", NS)],
        "publisher": _text(item, "dc:publisher"),
        "year": _text(item, "dc:date"),
        "isbn": _identifier(item, "ISBN").replace("-", ""),
        "series": _text(item, "dcndl:seriesTitle"),
        "language": "ja",
        "audience": "",
        "age_note": "",
        "subjects": [(n.text or "").strip() for n in item.findall("dcndl:genre", NS)],
        "summary": "",
    }


def _parse(body):
    root = ET.fromstring(body)
    if root.tag != "rss":
        raise SourceError("ndl: the answer is not an OpenSearch feed")
    return [_candidate(item) for item in root.iter("item")]


def by_isbn(isbn, fetch):
    return _parse(fetch(BASE + "?" + urlencode({"isbn": isbn, "dpid": "iss-ndl-opac", "cnt": 10})))


def search(title, author, fetch):
    params = {"title": title}
    if author:
        params["creator"] = author
    params.update({"dpid": "iss-ndl-opac", "cnt": 10})
    return _parse(fetch(BASE + "?" + urlencode(params)))
