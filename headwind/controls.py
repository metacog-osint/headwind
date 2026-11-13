"""Export-control and sanctions rules from the US Federal Register (keyless API).

Reads the rules and proposed rules that the Bureau of Industry and Security (BIS) and the Office of
Foreign Assets Control (OFAC) published in the last LOOKBACK_DAYS. Each record keeps the document's
own title, action line, effective date and the dates its DATES paragraph names. A named date in the
future (the day a stay ends, a comment period closes) becomes a calendar entry for Verdict.

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

AGENCIES = {"industry-and-security-bureau": "BIS", "foreign-assets-control-office": "OFAC"}
LOOKBACK_DAYS = 60
PER_PAGE = 200
FIELDS = ["document_number", "title", "type", "publication_date", "effective_on", "comments_close_on", "html_url",
          "agencies", "action", "abstract", "dates"]
FR_API = "https://www.federalregister.gov/api/v1/documents.json"

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
     "December"], 1)}
_DATE_RE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})\b")
_ADJECTIVES = {"Iranian": "IR", "Iran-Related": "IR", "Russian": "RU", "Cuban": "CU", "Venezuelan": "VE",
               "Syrian": "SY", "Chinese": "CN", "North Korea": "KP", "Belarus": "BY", "Burmese": "MM",
               "Democratic Republic of the Congo": "CD"}


def fr_url(today: date) -> str:
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    q = [f"conditions%5Bagencies%5D%5B%5D={a}" for a in AGENCIES]
    q += ["conditions%5Btype%5D%5B%5D=RULE", "conditions%5Btype%5D%5B%5D=PRORULE",
          f"conditions%5Bpublication_date%5D%5Bgte%5D={since}", f"per_page={PER_PAGE}", "order=newest"]
    q += [f"fields%5B%5D={f}" for f in FIELDS]
    return FR_API + "?" + "&".join(q)


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


def parse_fr(body: bytes | str) -> list[dict]:
    doc = json.loads(body)
    out = []
    for r in doc.get("results") or []:
        agency = next((AGENCIES[a.get("slug")] for a in r.get("agencies") or [] if a.get("slug") in AGENCIES), None)
        if not agency or not r.get("document_number") or not r.get("publication_date"):
            continue
        pub = r["publication_date"]
        abstract = " ".join((r.get("abstract") or "").split())
        out.append({
            "id": r["document_number"], "agency": agency, "type": r.get("type") or "Rule",
            "action": (r.get("action") or "").strip(), "title": " ".join((r.get("title") or "").split()),
            "published_date": pub, "effective_on": r.get("effective_on"),
            "comments_close_on": r.get("comments_close_on"),
            "named_dates": named_dates(r.get("dates"), pub),
            "url": r.get("html_url") or "https://www.federalregister.gov/",
            "abstract": abstract if len(abstract) <= 500 else abstract[:497].rsplit(" ", 1)[0] + "...",
            "countries": countries_in(r.get("title") or ""),
        })
    if (doc.get("count") or 0) > len(doc.get("results") or []):
        raise ValueError(f"Federal Register returned {len(doc.get('results') or [])} of {doc.get('count')} documents")
    out.sort(key=lambda x: (x["published_date"], x["id"]), reverse=True)
    return out


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
