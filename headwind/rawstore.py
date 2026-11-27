"""Raw copies that stay the same file while a source's data does not change.

Some sources put values in every reply that change on each request although the data they serve does not:
trade.gov's Consolidated Screening List stamps its hourly import times, HDX counts downloads and page views, Census
returns the same rows in a different order, and several pages carry a script nonce, a challenge token or a server
clock. Stored as fetched, each such reply is a new raw file (and a new copy in the archive) on every run.

For those sources `split` returns the reply with the changing values taken out (Census: its rows in a fixed order)
and a recipe that puts them back. The fetch's line in index.jsonl keeps the recipe (`rebuild`) and the stored file's
name (`stored`), so the reply as fetched is `rebuild(stored bytes, recipe)`, byte for byte, and its sha256 is the
line's `sha256`. Nothing is dropped: the values taken out are in the recipe. A split is used only when the rebuild
gives the fetched bytes back exactly; otherwise the reply is stored as fetched.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

MAX_SPANS = 5000        # more matches than this means a rule matched data, not a stamp: store as fetched


class Rule:
    """A pattern whose groups are the changing values; `before` limits it to the text before that marker."""

    def __init__(self, pattern: bytes, before: bytes | None = None):
        self.rx = re.compile(pattern)
        self.before = before

    def spans(self, body: bytes) -> list[tuple[int, int]]:
        end = len(body)
        if self.before is not None:
            i = body.find(self.before)
            end = i if i >= 0 else end
        out = []
        for m in self.rx.finditer(body, 0, end):
            for g in range(1, (self.rx.groups or 0) + 1):
                if m.start(g) >= 0 and m.end(g) > m.start(g):
                    out.append((m.start(g), m.end(g)))
        return out


# Challenge scripts and mail obfuscation that page hosts add to every reply, with a new value each time.
PAGE_NOISE = [
    Rule(rb"__CF\$cv\$params=\{r:'([0-9a-f]+)',t:'([^']*)'\}"),         # Cloudflare challenge parameters
    Rule(rb"/cdn-cgi/challenge-platform/scripts/jsd/main\.js\?ray=([0-9a-f]+)"),
    Rule(rb"/cdn-cgi/l/email-protection#([0-9a-f]+)"),                  # Cloudflare mail link, new key per reply
    Rule(rb"/_Incapsula_Resource\?[^\"'\s<>]*?&cb=(\d+)"),               # Imperva script, new cache-buster
]

RULES: dict[str, list[Rule]] = {
    # trade.gov CSL: the search time and each source list's last import (hourly); the lists themselves are kept.
    "trade-gov-csl": [Rule(rb'"search_performed_at"\s*:\s*"([^"]*)"'), Rule(rb'"last_imported"\s*:\s*"([^"]*)"')],
    # HDX package search: download and page-view counters of each dataset.
    "hdx-wfp-index": [Rule(rb'"total_res_downloads"\s*:\s*(\d+)'), Rule(rb'"pageviews_last_14_days"\s*:\s*(\d+)')],
    "ecb-calendar": [Rule(rb"ECB\.clientTimeError\s*=\s*(\d+)")],      # the server's clock, for a script
    "worldbank-pinksheet-page": [Rule(rb"docs(?:inline|data)_([0-9a-f]{32})")],   # a widget id made per reply
    # supremecourt.gov RSS: the channel's own date (the time of the request), not the opinions' dates.
    "supremecourt-gov": [Rule(rb"<(?:pubDate|lastBuildDate)>([^<]*)</", before=b"<item>")],
    # supremecourt.uk sitemap: the listing and form pages (the entries with no priority) carry the time of the
    # request as lastmod; the other pages' lastmod is their own date and stays in the stored copy.
    "supremecourt-uk": [Rule(rb"<lastmod>([^<]*)</lastmod>\s*<changefreq>hourly</changefreq>\s*</url>")],
}

ROW_SOURCES = {"census-trade"}     # a JSON table, one row a line, rows in no fixed order


def gzip_bytes(data: bytes) -> bytes:
    """gzip with no time in the header, so the same bytes always compress to the same file."""
    return gzip.compress(data, 6, mtime=0)


# --- spans --------------------------------------------------------------------------------------------------------

def _split_spans(body: bytes, rules: list[Rule]) -> tuple[bytes, dict] | None:
    spans = sorted(s for r in rules for s in r.spans(body))
    if not spans or len(spans) > MAX_SPANS:
        return None
    parts, at, pos, cut = [], [], 0, 0
    for a, b in spans:
        if a < pos:              # overlapping matches: keep the first
            continue
        try:
            value = body[a:b].decode("utf-8")
        except UnicodeDecodeError:
            return None
        parts.append(body[pos:a])
        cut += a - pos
        at.append([cut, value])
        pos = b
    parts.append(body[pos:])
    return b"".join(parts), {"kind": "spans", "at": at}


def _rebuild_spans(stored: bytes, recipe: dict) -> bytes:
    parts, pos = [], 0
    for off, value in recipe["at"]:
        parts.append(stored[pos:off])
        parts.append(value.encode("utf-8"))
        pos = off
    parts.append(stored[pos:])
    return b"".join(parts)


# --- rows ---------------------------------------------------------------------------------------------------------

def _table(body: bytes):
    """(header line, rows, tail) of a reply laid out as Census sends it:
    '[[header],' then one '[row],' a line and a last '[row]]'. None for any other layout."""
    tail = b""
    if body.endswith(b"\n"):
        body, tail = body[:-1], b"\n"
    lines = body.split(b"\n")
    if len(lines) < 3 or not lines[0].startswith(b"[[") or not lines[0].endswith(b","):
        return None
    data = lines[1:]
    if not all(line.endswith(b",") for line in data[:-1]) or not data[-1].endswith(b"]]"):
        return None
    return lines[0], [line[:-1] for line in data], tail


def _join_table(header: bytes, rows: list[bytes], tail: bytes) -> bytes:
    return header + b"\n" + b",\n".join(rows) + b"]" + tail


def _split_rows(body: bytes) -> tuple[bytes, dict] | None:
    t = _table(body)
    if t is None:
        return None
    header, rows, tail = t
    try:
        cols = json.loads(header[1:-1])
        ti = cols.index("time") if "time" in cols else None
        keys = [((json.loads(r)[ti] if ti is not None else ""), r) for r in rows]
    except (ValueError, IndexError, TypeError):
        return None
    order = sorted(range(len(rows)), key=lambda i: keys[i])
    place = [0] * len(rows)
    for k, i in enumerate(order):
        place[i] = k
    runs = []
    for p in place:          # the reply's rows as runs [start, length] of the stored order
        if runs and runs[-1][0] + runs[-1][1] == p:
            runs[-1][1] += 1
        else:
            runs.append([p, 1])
    return _join_table(header, [rows[i] for i in order], tail), {"kind": "rows", "runs": runs}


def _rebuild_rows(stored: bytes, recipe: dict) -> bytes:
    t = _table(stored)
    if t is None:
        raise ValueError("stored table is not in the expected layout")
    header, rows, tail = t
    out = []
    for start, n in recipe["runs"]:
        out.extend(rows[start:start + n])
    if len(out) != len(rows):
        raise ValueError("recipe does not cover the stored rows")
    return _join_table(header, out, tail)


# --- entry points -------------------------------------------------------------------------------------------------

def rebuild(stored: bytes, recipe: dict) -> bytes:
    """The reply as fetched, from the stored bytes and the recipe in its index.jsonl line."""
    kind = recipe.get("kind")
    if kind == "spans":
        return _rebuild_spans(stored, recipe)
    if kind == "rows":
        return _rebuild_rows(stored, recipe)
    raise ValueError(f"unknown recipe kind {kind!r}")


def split(source_id: str, ext: str, body: bytes) -> tuple[bytes, dict | None]:
    """(bytes to store, recipe) for a reply; (body, None) when it is stored as fetched."""
    if source_id in ROW_SOURCES:
        got = _split_rows(body)
    else:
        rules = RULES.get(source_id, []) + (PAGE_NOISE if ext == "html" else [])
        got = _split_spans(body, rules) if rules else None
    if got is None:
        return body, None
    stored, recipe = got
    if stored == body:
        return body, None
    try:
        ok = rebuild(stored, recipe) == body
    except (ValueError, KeyError, TypeError):
        ok = False
    return (stored, recipe) if ok else (body, None)


def read_fetched(raw_dir: Path, rec: dict) -> bytes:
    """The reply of one index.jsonl line, as fetched, from the raw folder; checked against the line's sha256."""
    raw_dir = Path(raw_dir)
    if rec.get("stored"):
        p = raw_dir / rec["stored"]
    else:
        hits = sorted((raw_dir / rec["source_id"]).glob(f"{rec['sha256'][:12]}.*"))
        if not hits:
            raise FileNotFoundError(f"no raw copy of {rec['source_id']} {rec['sha256'][:12]}")
        p = hits[0]
    data = p.read_bytes()
    if p.name.endswith(".gz"):
        data = gzip.decompress(data)
    if rec.get("rebuild"):
        data = rebuild(data, rec["rebuild"])
    if hashlib.sha256(data).hexdigest() != rec["sha256"]:
        raise ValueError(f"raw copy of {rec['source_id']} does not match its sha256")
    return data
