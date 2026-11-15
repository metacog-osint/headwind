"""Export-control, sanctions and trade rules from the US Federal Register (keyless API).

Reads the rules and proposed rules that the Bureau of Industry and Security (BIS), the Office of
Foreign Assets Control (OFAC) and the Office of the US Trade Representative (USTR) published in the
last LOOKBACK_DAYS, and USTR's notices (Section 301 actions, exclusions and their extensions), which
is how USTR publishes most of what it does. Each record keeps the document's own title, action line,
effective date, the dates its DATES paragraph names, and its RINs and docket numbers. A named date in
the future (the day a stay ends, a comment period closes) becomes a calendar entry for Verdict.

The same agencies' documents of the last REGISTER_DAYS give the register of scheduled dates
(`scheduled()`): every date a document set, kept with the document's RINs, dockets and, for USTR, the
investigation its title names. A filing on public inspection (inspection.py) is matched against it.

Headwind reports what was published. It does not say what a rule means or whether a stay will be
extended.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doctrine" / "kit" / "python"))
from tic_doctrine import geo  # noqa: E402

AGENCIES = {"industry-and-security-bureau": "BIS", "foreign-assets-control-office": "OFAC",
            "trade-representative-office-of-united-states": "USTR"}
USTR = "trade-representative-office-of-united-states"
LOOKBACK_DAYS = 60
# Long enough to hold the date a one-year stay or a year of exclusions was set to end, with room to spare.
REGISTER_DAYS = 800
REGISTER_KEEP_DAYS = 45      # a scheduled date stays in the register this long after it has passed
PER_PAGE = 200
REGISTER_PER_PAGE = 1000
FIELDS = ["document_number", "title", "type", "publication_date", "effective_on", "comments_close_on", "html_url",
          "agencies", "action", "abstract", "dates", "regulation_id_numbers", "docket_ids"]
REGISTER_FIELDS = ["document_number", "title", "type", "publication_date", "effective_on", "comments_close_on",
                   "html_url", "agencies", "dates", "regulation_id_numbers", "docket_ids"]
FR_API = "https://www.federalregister.gov/api/v1/documents.json"
# USTR notices that are about the office itself, not trade: left out of the lane.
ADMIN_TITLE = re.compile(r"Performance Review Board|Privacy Act|Information Collection|Sunshine Act|"
                         r"Advisory Committee|Federal Advisory|Meetings?\b", re.I)
_DOCKET_TOKEN = re.compile(r"\b(?:[A-Z]{2,}-\d{4}-\d{3,5}|\d{6}-\d{4}(?:-\d{2})?)\b")
_RIN = re.compile(r"\b(\d{4}-[A-Z]{2}\d{2})\b")

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
     "December"], 1)}
_DATE_RE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})\b")
_ADJECTIVES = {"Iranian": "IR", "Iran-Related": "IR", "Russian": "RU", "Cuban": "CU", "Venezuelan": "VE",
               "Syrian": "SY", "Chinese": "CN", "North Korea": "KP", "Belarus": "BY", "Burmese": "MM",
               "Democratic Republic of the Congo": "CD"}


def _url(agencies, types, since: str, per_page: int, fields) -> str:
    q = [f"conditions%5Bagencies%5D%5B%5D={a}" for a in agencies]
    q += [f"conditions%5Btype%5D%5B%5D={t}" for t in types]
    q += [f"conditions%5Bpublication_date%5D%5Bgte%5D={since}", f"per_page={per_page}", "order=newest"]
    q += [f"fields%5B%5D={f}" for f in fields]
    return FR_API + "?" + "&".join(q)


def fr_url(today: date) -> str:
    """Rules and proposed rules of BIS, OFAC and USTR in the last LOOKBACK_DAYS."""
    return _url(AGENCIES, ("RULE", "PRORULE"), (today - timedelta(days=LOOKBACK_DAYS)).isoformat(), PER_PAGE, FIELDS)


def ustr_url(today: date) -> str:
    """USTR's notices in the last LOOKBACK_DAYS."""
    return _url([USTR], ("NOTICE",), (today - timedelta(days=LOOKBACK_DAYS)).isoformat(), PER_PAGE, FIELDS)


def register_urls(today: date) -> dict[str, str]:
    """The register's two reads: every agency's rules, and USTR's notices, over REGISTER_DAYS (no abstracts)."""
    since = (today - timedelta(days=REGISTER_DAYS)).isoformat()
    return {"rules": _url(AGENCIES, ("RULE", "PRORULE"), since, REGISTER_PER_PAGE, REGISTER_FIELDS),
            "ustr": _url([USTR], ("NOTICE",), since, REGISTER_PER_PAGE, REGISTER_FIELDS)}


def docket_tokens(values) -> list[str]:
    """Docket numbers as tokens (USTR-2026-0364, 261027-0002), from the API's docket strings or a filing's text."""
    out = set()
    for v in values or []:
        out.update(_DOCKET_TOKEN.findall(v or ""))
    return sorted(out)


def subject(title: str | None) -> str | None:
    """The investigation a USTR title names: the words after its first colon, before any "; ...", without case,
    punctuation or the small words USTR is not consistent about ("Targeting of the Maritime" and "Targeting the
    Maritime"). None when the title has no colon or the subject is too short to tell investigations apart."""
    if not title or ":" not in title:
        return None
    s = title.split(":", 1)[1].split(";", 1)[0].lower()
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in {"of", "the", "and", "s", "for", "a", "an", "to"}]
    return " ".join(words) if len(words) >= 4 else None


def named_dates(text: str | None, after: str) -> list[str]:
    """ISO dates written out in a DATES paragraph that fall after `after` (the publication date)."""
    out = set()
    for month, day, year in _DATE_RE.findall(text or ""):
        try:
            d = date(int(year), _MONTHS[month], int(day)).isoformat()
        except ValueError:
            continue
        if d > after:
            out.add(d)
    return sorted(out)


def countries_in(title: str) -> list[str]:
    """Countries a title names outright. A rule that names none stays unplaced."""
    out = {cc for word, cc in _ADJECTIVES.items() if re.search(rf"\b{re.escape(word)}\b", title)}
    for c in geo._countries():                      # the kit's own list of names
        name = c.get("name") or ""
        if len(name) >= 4 and c["cc"] != "US" and re.search(rf"\b{re.escape(name)}\b", title):
            out.add(c["cc"])
    return sorted(out)


def agency_of(agencies) -> str | None:
    return next((AGENCIES[a.get("slug")] for a in agencies or [] if a.get("slug") in AGENCIES), None)


def parse_fr(body: bytes | str) -> list[dict]:
    doc = json.loads(body)
    out = []
    for r in doc.get("results") or []:
        agency = agency_of(r.get("agencies"))
        if not agency or not r.get("document_number") or not r.get("publication_date"):
            continue
        title = " ".join((r.get("title") or "").split())
        if agency == "USTR" and (r.get("type") or "") == "Notice" and ADMIN_TITLE.search(title):
            continue
        pub = r["publication_date"]
        abstract = " ".join((r.get("abstract") or "").split())
        out.append({
            "id": r["document_number"], "agency": agency, "type": r.get("type") or "Rule",
            "action": (r.get("action") or "").strip(), "title": title,
            "published_date": pub, "effective_on": r.get("effective_on"),
            "comments_close_on": r.get("comments_close_on"),
            "named_dates": named_dates(r.get("dates"), pub),
            "url": r.get("html_url") or "https://www.federalregister.gov/",
            "abstract": abstract if len(abstract) <= 500 else abstract[:497].rsplit(" ", 1)[0] + "...",
            "countries": countries_in(title),
            "rins": sorted(set(r.get("regulation_id_numbers") or [])),
            "dockets": docket_tokens(r.get("docket_ids")),
        })
    if (doc.get("count") or 0) > len(doc.get("results") or []):
        raise ValueError(f"Federal Register returned {len(doc.get('results') or [])} of {doc.get('count')} documents")
    out.sort(key=lambda x: (x["published_date"], x["id"]), reverse=True)
    return out


def scheduled(docs: list[dict], today: date) -> list[dict]:
    """The register of scheduled dates: each date a document set (named in its DATES paragraph, its effective date,
    the close of its comment period), from today less REGISTER_KEEP_DAYS on. Each entry keeps what a later filing
    is matched on: the document's RINs and dockets, and for USTR the investigation its title names."""
    lo = (today - timedelta(days=REGISTER_KEEP_DAYS)).isoformat()
    out = {}
    for r in docs:
        dated = [(d, "a date its DATES paragraph names") for d in r.get("named_dates") or []]
        if r.get("effective_on"):
            dated.append((r["effective_on"], "its effective date"))
        if r.get("comments_close_on"):
            dated.append((r["comments_close_on"], "the close of its comment period"))
        for d, what in dated:
            if d < lo:
                continue
            out.setdefault((d, r["id"]), {
                "date": d, "doc": r["id"], "agency": r["agency"], "published": r["published_date"], "what": what,
                "title": r["title"], "url": r["url"], "rins": r.get("rins") or [], "dockets": r.get("dockets") or [],
                "subject": subject(r["title"]) if r["agency"] == "USTR" else None})
    return sorted(out.values(), key=lambda e: (e["date"], e["doc"]))


def build_events(rules: list[dict], today: date, horizon_days: int = 180) -> list[dict]:
    """Future dates from the rules, in Verdict's sync_calendar format (kind rule_date)."""
    lo, hi = today.isoformat(), (today + timedelta(days=horizon_days)).isoformat()
    events = {}
    for r in rules:
        dated = [(d, "date named in the rule") for d in r.get("named_dates") or []]
        if r.get("effective_on"):
            dated.append((r["effective_on"], "effective date"))
        if r.get("comments_close_on"):
            dated.append((r["comments_close_on"], "comments close"))
        for d, what in dated:
            if lo <= d <= hi:
                eid = f"{d}-fr-{r['id']}"
                events.setdefault(eid, {
                    "id": eid, "date": d, "kind": "rule_date", "countries": r.get("countries") or [], "ref": r["id"],
                    "title": f"{r['agency']}: {r['title']} ({what})",
                    "source": {"publisher": f"US Federal Register ({r['agency']})", "url": r["url"]},
                })
    return sorted(events.values(), key=lambda e: (e["date"], e["id"]))


def recent(rules: list[dict], generated_at: str, days: int) -> list[dict]:
    cutoff = (datetime.fromisoformat(generated_at.replace("Z", "+00:00")) - timedelta(days=days)).date().isoformat()
    return [r for r in rules if r["published_date"] >= cutoff]
