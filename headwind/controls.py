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
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doctrine" / "kit" / "python"))
from tic_doctrine import geo  # noqa: E402

AGENCIES = {"industry-and-security-bureau": "BIS", "foreign-assets-control-office": "OFAC",
            "trade-representative-office-of-united-states": "USTR"}
USTR = "trade-representative-office-of-united-states"
ITA = "international-trade-administration"
EOP = "executive-office-of-the-president"
# Labels for every agency a record can carry. The rules query asks only for AGENCIES; ITA's notices are asked for
# only with "section 232" in their text, and presidential documents by their type.
LABELS = {**AGENCIES, ITA: "ITA", EOP: "President"}
# A presidential document or a Section 232 notice is a tariff action when its title says so. Read against every
# presidential document of Sep 2024 to Nov 2026 (60 of 839 matched, all by their titles). "Duty" alone is left out:
# "Line of Duty" titles are not tariff actions; "Heavy-Duty Vehicles" ones are matched by "Adjusting Imports".
TARIFF_TITLE = re.compile(r"tariff|duties|duty-free|adjusting imports|import adjustment|section (?:122|232|301|338)\b|"
                          r"harmonized tariff", re.I)
# Section 232 notices also open and close inclusion windows (products added to a tariff on request).
INCLUSION = re.compile(r"\binclusions?\b", re.I)
PRES_FIELDS = ["document_number", "title", "type", "subtype", "publication_date", "signing_date", "html_url",
               "agencies", "abstract", "raw_text_url", "proclamation_number", "executive_order_number"]
PACE_WINDOW = 28          # days in one window of the tariff-action count
PACE_WINDOWS = 27         # earlier windows in its baseline (27 x 28 = 756 days, inside REGISTER_DAYS)
PACE_FLOOR = 4            # documents: fewer than this in a window is never unusual
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
               "Democratic Republic of the Congo": "CD",
               # Names OFAC's titles use that the kit's list does not: "Burma Sanctions Regulations",
               # "Darfur Sanctions Regulations" (Darfur is a region of Sudan).
               "Burma": "MM", "Darfur": "SD"}


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


def presidential_url(today: date) -> str:
    """Every presidential document of the last REGISTER_DAYS (about 840 on 15 Nov 2026, 760 KB): the tariff
    actions among them are kept, and their count over time is the pace's baseline."""
    since = (today - timedelta(days=REGISTER_DAYS)).isoformat()
    return _url([], ("PRESDOCU",), since, REGISTER_PER_PAGE, PRES_FIELDS)


def section232_url(today: date) -> str:
    """BIS's and ITA's notices of the last REGISTER_DAYS whose text says "section 232" (53 on 15 Nov 2026):
    investigations, comment requests, inclusion windows, tariff procedures."""
    since = (today - timedelta(days=REGISTER_DAYS)).isoformat()
    return (_url(["industry-and-security-bureau", ITA], ("NOTICE",), since, REGISTER_PER_PAGE, FIELDS)
            + "&conditions%5Bterm%5D=%22section+232%22")


def is_tariff(title: str | None) -> bool:
    return bool(TARIFF_TITLE.search(title or ""))


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
    """Countries a title names outright. A rule that names none stays unplaced.

    Longest name first, and each match is blanked before shorter names are tried, so a name inside a longer one
    does not count again: "Democratic Republic of the Congo" is CD only (not also "Republic of the Congo", CG),
    "South Sudan" SS only, "Guinea-Bissau" GW only (15 Nov 2026 suite review)."""
    names = dict(_ADJECTIVES)
    for c in geo._countries():                      # the kit's own list of names
        name = c.get("name") or ""
        if len(name) >= 4 and c["cc"] != "US":
            names.setdefault(name, c["cc"])
    out, text = set(), title or ""
    for name in sorted(names, key=len, reverse=True):
        pat = re.compile(rf"\b{re.escape(name)}\b")
        if pat.search(text):
            out.add(names[name])
            text = pat.sub(lambda m: "\x00" * len(m.group(0)), text)
    return sorted(out)


def agency_of(agencies) -> str | None:
    return next((LABELS[a.get("slug")] for a in agencies or [] if a.get("slug") in LABELS), None)


def parse_section232(body: bytes | str) -> list[dict]:
    """BIS's and ITA's Section 232 notices, in the rules' form, less the office's own (information collections)
    and those whose title is not about a tariff (ITA's antidumping notices that mention Section 232 in passing)."""
    return [r for r in parse_fr(body)
            if (is_tariff(r["title"]) or INCLUSION.search(r["title"])) and not ADMIN_TITLE.search(r["title"])]


def parse_presidential(body: bytes | str) -> list[dict]:
    """The tariff actions among presidential documents, in the rules' form: agency "President", the document's
    subtype (Proclamation, Executive Order, Memorandum) as its action, its signing date and number. Dates come
    later from its text (`text_dates`)."""
    doc = json.loads(body)
    rows = doc.get("results") or []
    if (doc.get("count") or 0) > len(rows):
        raise ValueError(f"Federal Register returned {len(rows)} of {doc.get('count')} presidential documents")
    out = []
    for r in rows:
        title = " ".join((r.get("title") or "").split())
        if not r.get("document_number") or not r.get("publication_date") or not is_tariff(title):
            continue
        abstract = " ".join((r.get("abstract") or "").split())
        number = r.get("proclamation_number") or r.get("executive_order_number")
        out.append({
            "id": r["document_number"], "agency": "President", "type": "Presidential Document",
            "action": r.get("subtype") or "Presidential document", "title": title,
            "published_date": r["publication_date"], "signing_date": r.get("signing_date"),
            "number": str(number) if number else None, "effective_on": None, "comments_close_on": None,
            "named_dates": [], "url": r.get("html_url") or "https://www.federalregister.gov/",
            "raw_text_url": r.get("raw_text_url"),
            "abstract": abstract if len(abstract) <= 500 else abstract[:497].rsplit(" ", 1)[0] + "...",
            "countries": countries_in(title), "rins": [], "dockets": [],
        })
    out.sort(key=lambda x: (x["published_date"], x["id"]), reverse=True)
    return out


# "... on or after 12:01 a.m. eastern time on October 30, 2026" (proclamations give effective times this way).
_AT_1201 = re.compile(r"12:01 a\.\s?m\.[^.;]{0,40}?\bon\s+((?:" + "|".join(_MONTHS) + r")\s+\d{1,2},\s+\d{4})")
_WITHIN_DAYS = re.compile(r"within (\d{1,3}) days (?:of|after) the date of this (?:proclamation|order|memorandum)",
                          re.I)


def text_dates(text: str, published: str, signed: str | None) -> tuple[list[str], list[str]]:
    """Dates a presidential document's text sets: each "12:01 a.m. ... on <date>" from its publication day on, and
    (computed, so listed apart) each "within N days of the date of this proclamation" counted from its signing
    date. Earlier dates in the text (what an older proclamation did) are left out by the publication date."""
    flat = " ".join(re.sub(r"<[^>]+>", " ", text or "").split())
    named = set()
    day_before = (date.fromisoformat(published) - timedelta(days=1)).isoformat()   # effective the day it is published
    for s in _AT_1201.findall(flat):
        named.update(named_dates(s, day_before))
    computed = set()
    if signed:
        base = date.fromisoformat(signed)
        for n in _WITHIN_DAYS.findall(flat):
            d = (base + timedelta(days=int(n))).isoformat()
            if d > published:
                computed.add(d)
    return sorted(named), sorted(computed)


def pace(docs: list[dict], today: date, window: int = PACE_WINDOW, n_windows: int = PACE_WINDOWS,
         floor: int = PACE_FLOOR) -> dict:
    """How many tariff actions were published in the last `window` days, against the same count in each of the
    `n_windows` windows before it (robust z, stats.score, `floor` documents at least). Counted by publication
    date in the Federal Register, which is when a document becomes public."""
    from . import stats
    def count(k):
        hi = today - timedelta(days=window * k)
        lo = hi - timedelta(days=window - 1)
        return [d for d in docs if lo.isoformat() <= d["published_date"] <= hi.isoformat()]
    latest = count(0)
    base = [float(len(count(k))) for k in range(1, n_windows + 1)]
    lo = (today - timedelta(days=window - 1)).isoformat()
    return {"window_days": window, "from": lo, "to": today.isoformat(), "count": len(latest),
            "ids": sorted(d["id"] for d in latest), "median": statistics.median(base) if base else None,
            "baseline_windows": len(base), **stats.score(float(len(latest)), base, float(floor))}


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
        dated = [(d, "a date its DATES paragraph names" if r["agency"] != "President"
                  else "a date its text sets (12:01 a.m. on that day)") for d in r.get("named_dates") or []]
        dated += [(d, "a date counted from its signing date (\"within N days of the date of this proclamation\")")
                  for d in r.get("computed_dates") or []]
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
        president = r["agency"] == "President"
        dated = [(d, "date its text sets" if president else "date named in the rule") for d in r.get("named_dates") or []]
        dated += [(d, "counted from its signing date") for d in r.get("computed_dates") or []]
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
                    "source": {"publisher": "US Federal Register (presidential documents)" if president
                               else f"US Federal Register ({r['agency']})", "url": r["url"]},
                })
    return sorted(events.values(), key=lambda e: (e["date"], e["id"]))


def recent(rules: list[dict], generated_at: str, days: int) -> list[dict]:
    cutoff = (datetime.fromisoformat(generated_at.replace("Z", "+00:00")) - timedelta(days=days)).date().isoformat()
    return [r for r in rules if r["published_date"] >= cutoff]
