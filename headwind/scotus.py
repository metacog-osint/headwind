"""The US Supreme Court: every signed opinion and per curiam opinion, and the dockets of the tariff-authority cases.

Sources (supremecourt.gov, keyless): the slip opinion RSS feed for a term (`slipopinion_rss.aspx?TYear=26` is the
term that began in October 2026) and each case's docket as JSON (`/RSS/Cases/JSON/<docket>.json`). Opinions and
dockets are US government works (17 USC 105, stated from memory; the Court's site policies give no reuse statement).

Names (15 Nov 2026): an item carries the Court's own case title and docket number as the Court publishes them,
and `us_person_data` says when a party may be a US person (`party_kind`). Nothing is summarized or judged: an item
says the Court issued an opinion in a case on a date, by whom, with the link.

Dates: the feed's pubDate is when the PDF was last posted, and moves when the reporter version replaces the slip
opinion, so the decision date is read from the docket: the entry that links the opinion (`decided`). The docket is
read once per case.

Not covered: orders lists (no feed), opinions relating to orders and in-chambers opinions (other feeds, not read).
"""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

FEED = "https://www.supremecourt.gov/rss/slipopinion_rss.aspx?TYear={yy:02d}"
DOCKET_JSON = "https://www.supremecourt.gov/RSS/Cases/JSON/{docket}.json"
DOCKET_PAGE = "https://www.supremecourt.gov/search.aspx?filename=/docket/docketfiles/html/public/{docket}.html"
OPINIONS_PAGE = "https://www.supremecourt.gov/opinions/slipopinion/{yy:02d}"
# Tariff-authority cases tracked by docket (Learning Resources v. Trump and Trump v. V.O.S. Selections, argued
# together 5 Nov 2025; judgment 20 Feb 2026, read from the dockets 15 Nov 2026). Dockets each tracked one names as
# related are followed too. A later tariff case is added here by hand.
TARIFF_DOCKETS = ("24-1287", "25-250")
FEED_DAYS = 14          # opinions and docket entries in the feed
MIN_ITEMS = 1           # a term feed with no item at all is read as broken, except early in a term (see parse)

_TITLE = re.compile(r"^(?P<title>.*\S)\s*\((?P<docket>[^()]+)\)\s*$")
_PER_CURIAM_TAIL = re.compile(r"\s*-\s*\(per curiam\)\s*$", re.IGNORECASE)   # "FCC v. Brown (26A476) - (per curiam)"
_DOCKET = re.compile(r"^(?:\d{2}-\d{1,5}|\d{2}A\d{1,5}|\d{1,3},\s*Orig\.)$")
_SIGNED = re.compile(r"^(?:Chief\s+)?Justice\s+")
_OPINION_LINK = re.compile(r"opinions/[0-9a-z]+pdf/[^'\" >]+\.pdf", re.IGNORECASE)
# The entry that records an opinion without linking it (25A312, 29 Jun 2026: "... Roberts, C. J., delivered the
# opinion of the Court ...").
_OPINION_WORDS = re.compile(r"delivered the opinion|opinion per curiam|per curiam opinion", re.IGNORECASE)


def term_years(today: date) -> tuple[int, int]:
    """The current term and the one before, as two-digit years: a term starts on the first Monday of October."""
    current = today.year % 100 if today.month >= 10 else (today.year - 1) % 100
    return current, (current - 1) % 100


def _utc(text: str | None) -> str | None:
    try:
        dt = parsedate_to_datetime((text or "").strip())
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_feed(body: bytes, term: int) -> list[dict]:
    """The opinions in one term's feed: docket, the Court's case title, signed or per curiam, author, link, and when
    the PDF was posted. Other categories (decrees in original cases) are left out."""
    root = ET.fromstring(body)
    out = []
    for i in root.iter("item"):
        cats = [(c.text or "").strip() for c in i.findall("category")]
        kind = "per curiam" if "Unsigned Per Curiam Opinion" in cats else \
            "signed" if any(_SIGNED.match(c) for c in cats) else None
        m = _TITLE.match(_PER_CURIAM_TAIL.sub("", " ".join((i.findtext("title") or "").split())))
        if not kind or not m or not _DOCKET.match(m.group("docket").strip()):
            continue
        out.append({"docket": m.group("docket").strip(), "title": m.group("title").strip(), "kind": kind,
                    "author": next((c for c in cats if _SIGNED.match(c)), None), "term": f"{term:02d}",
                    "link": (i.findtext("link") or "").strip().replace("http://", "https://", 1),
                    "posted": _utc(i.findtext("pubDate"))})
    return out


def _day(text: str | None) -> str | None:
    try:
        return datetime.strptime(" ".join((text or "").split()), "%b %d %Y").date().isoformat()
    except ValueError:
        return None


def parse_docket(body: bytes) -> dict:
    """What Headwind keeps from a docket: the Court's titles for each side, the lower court, the decision date (the
    entry that links an opinion), the related dockets, and the newest entry. Attorneys and parties' contact details
    are never read."""
    d = json.loads(body.decode("utf-8-sig"))
    entries = [{"date": _day(p.get("Date")), "text": _plain(p.get("Text"))} for p in d.get("ProceedingsandOrder") or []]
    po = d.get("ProceedingsandOrder") or []
    opinion = next((p for p in po if _OPINION_LINK.search(p.get("Text") or "")), None) or \
        next((p for p in po if _OPINION_WORDS.search(p.get("Text") or "")), None)
    dated = [e for e in entries if e["date"]]
    return {"docket": (d.get("CaseNumber") or "").strip(), "petitioner": (d.get("PetitionerTitle") or "").strip(),
            "respondent": (d.get("RespondentTitle") or "").strip(), "lower_court": (d.get("LowerCourt") or "").strip(),
            "docketed": _iso_long(d.get("DocketedDate")), "decided": _day(opinion.get("Date")) if opinion else None,
            "decision": judgment(_plain(opinion.get("Text"))) if opinion else None,
            "related": sorted({(r.get("DisplayCaseNumber") or "").strip() for r in d.get("RelatedCaseNumber") or []} - {""}),
            "last_entry": dated[-1] if dated else None, "entries": len(entries)}


_AUTHORSHIP = re.compile(r"\s(?:[A-Z][a-z]+,\s(?:C\.\s)?J\.,|Opinion per curiam|Per Curiam)")


def judgment(text: str, limit: int = 300) -> str:
    """The judgment in a decision entry, without who wrote and joined what ("Roberts, C. J., announced ..."): the
    entry up to that point, else its first `limit` characters at a word, marked as cut."""
    m = _AUTHORSHIP.search(text)
    head = text[:m.start()].strip() if m and m.start() > 0 else text
    if len(head) <= limit:
        return head
    return head[:limit].rsplit(" ", 1)[0] + " \u2026"


def _iso_long(text: str | None) -> str | None:
    try:
        return datetime.strptime((text or "").strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _plain(text: str | None) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text or "")).split())


# --- us_person_data -----------------------------------------------------------------------------------------
# A case title names one party or several on each side of " v. ". Headwind does not know a party's nationality, so
# the label is cautious: "individuals" when any side reads as a person (a name with no mark of a government or an
# organization; an official named in an official capacity is still a person), else "organizations" when any side
# is an organization that is not a government, else "none" (every side a government). A label for consumers bound
# by US-person rules; never a reason to leave a case out.
_GOV = re.compile(
    r"^(?:United States|District of Columbia|Puerto Rico|Guam|"
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|"
    r"Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|"
    r"Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|"
    r"North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|"
    r"Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)$"
    r"|\b(?:Department|Dept\.?|Bd|Commission|Comm'n|Comm’n|Board of|Bureau|Agency|Administration|Service|"
    r"County|Parish|City of|Town of|Village of|Township|Republic|Kingdom|Government|Authority|State of|"
    r"School District|Commonwealth)\b|^(?:FCC|SEC|FTC|NLRB|EPA|IRS|FBI|DHS|FDA|OPM|USPS)$", re.IGNORECASE)
_ORG = re.compile(
    r"\b(?:Inc|Corp|Corporation|Co|Company|LLC|L\.L\.C|Ltd|LP|L\.P|LLP|PLC|S\.\s?A|N\.\s?A|GmbH|AG|Association|"
    r"Committee|Council|Centers?|Church|Fund|Foundation|Union|Group|Systems|Communications|Pharmaceuticals?|"
    r"Trustees|Trust|University|College|Hospital|Medical|Bank|Partners|Holdings|Industries|Enterprises|"
    r"Coalition|League|Party|Federation|Institute|Society|Club|Network|Alliance|Project|Politicians|Friends|"
    r"Properties|Construction|Foods|Energy|Transport|Entertainment|Insurance|Services|Solutions|Labs?|Media|"
    r"Organization|Coop|Cooperative|Tribe|Nation|Pension|Plan)\b\.?|&", re.IGNORECASE)
_ACRONYM = re.compile(r"^[A-Z&]{2,}$")


def party_kind(party: str) -> str:
    """government, organization or person, from one side of a case title as the Court prints it."""
    p = re.sub(r",?\s+et al\.?$", "", " ".join(party.split()))
    p = re.sub(r"\s*\([^()]*\)\s*$", "", p)              # "(Cuba)"
    if _GOV.search(p):
        return "government"
    if _ORG.search(p) or _ACRONYM.match(p):
        return "organization"
    return "person"


def us_person_data(title: str) -> str:
    sides = [s for s in re.split(r"\s+v\.\s+", title) if s.strip()]
    kinds = {party_kind(s) for s in sides} or {"person"}
    if "person" in kinds:
        return "individuals"
    return "organizations" if "organization" in kinds else "none"


def merge(previous: list[dict], found: list[dict], dockets: dict[str, dict], now: str) -> list[dict]:
    """Opinions of the two terms read, keyed by docket, newest decision first. A docket keeps its first-seen time and
    its decision date once read; the title, link and posting time follow the feed (the reporter version replaces
    the slip opinion's link)."""
    old = {o["docket"]: o for o in previous or []}
    out = {}
    for f in found:
        if f["docket"] in out:            # a second opinion under one docket in the feeds: the first is kept
            continue
        o = {**old.get(f["docket"], {}), **f}
        o.setdefault("first_seen", now)
        dk = dockets.get(f["docket"])
        if dk and dk.get("decided"):
            o["decided"] = dk["decided"]
        o["docket_url"] = DOCKET_PAGE.format(docket=f["docket"])
        o["us_person_data"] = us_person_data(f["title"])
        out[f["docket"]] = o
    return sorted(out.values(), key=lambda o: (o.get("decided") or (o.get("posted") or "")[:10], o["docket"]),
                  reverse=True)


def needs_docket(opinions: list[dict]) -> list[str]:
    """Dockets whose decision date is not yet known."""
    return [o["docket"] for o in opinions if not o.get("decided")]
