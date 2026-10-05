"""National Library of the Czech Republic (NK CR) over Z39.50, through the yaz-client program.

The `run` argument of by_isbn and search is a callable run(commands: str) -> str that feeds a command
script to yaz-client and returns what it printed.
"""
import re

from home_library.lookup.errors import SourceError
from home_library.lookup.marc import candidate_from_marc

DATABASE = "aleph.nkp.cz:9991/NKC-UTF"
MAX_RECORDS = 10


def _quote(text):
    """A yaz query string: one line, in double quotes, with quote and backslash escaped."""
    text = " ".join(text.split())
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _script(query):
    return "\n".join(
        ["open " + DATABASE, "format usmarc", "find " + query, "show 1+%d" % MAX_RECORDS, "quit"]
    ) + "\n"


def _parse_field(line):
    tag = line[:3]
    if tag < "010":
        return tag, line[4:], None
    ind1, ind2 = (line[4:6] + "  ")[:2]
    subfields = [
        (m.group(1), m.group(2))
        for m in re.finditer(r"\$([0-9a-z]) (.*?)(?= \$[0-9a-z] |\s*$)", line[7:])
    ]
    return tag, (ind1, ind2), subfields


def _parse(output):
    if "Search was a success" not in output:
        raise SourceError("yaz-client: the search did not succeed")
    records = []
    record = None
    for line in output.splitlines():
        if "Record type:" in line:
            record = {"control": {}, "fields": []}
            records.append(record)
            continue
        if record is None or not re.match(r"\d{3} ", line):
            continue
        tag, indicators, subfields = _parse_field(line)
        if subfields is None:
            record["control"][tag] = indicators
        else:
            record["fields"].append((tag, indicators[0], indicators[1], subfields))
    return records


def by_isbn(isbn, run):
    output = run(_script('@attr 1=7 ' + _quote(isbn)))
    return [candidate_from_marc("nkcr", record) for record in _parse(output)]


def search(title, author, run):
    query = "@attr 1=4 " + _quote(title)
    if author:
        query = "@and %s @attr 1=1003 %s" % (query, _quote(author))
    output = run(_script(query))
    return [candidate_from_marc("nkcr", record) for record in _parse(output)]
