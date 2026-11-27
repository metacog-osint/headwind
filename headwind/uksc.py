"""The UK Supreme Court: every judgment the Court has handed down this calendar year and the last.

Source: the Court's own site, supremecourt.uk (keyless). Its terms (/about/terms-and-conditions, read 18 Nov 2026):
"You may use and re-use Crown copyright material from this website, other than the Royal Arms and departmental
logos, under the terms of the Open Government Licence, provided it is reproduced accurately and not in a misleading
context." Video footage of proceedings is under a separate licence (the Open Supreme Court Licence) and is not used.

How judgments are found: the site is a Next.js app whose case list filters only through a server action (the
`?cs=Judgment+given` query is ignored when the page is fetched), and it has no feed. Its sitemap (`/sitemap.xml`)
lists every case page and, for each case with a judgment, a judgment page `/cases/judgments/<case>` with the time it
last changed. Checked 18 Nov 2026: the 159 real judgment pages cover [2024] UKSC 1-43, [2025] UKSC 1-49 and [2026]
UKSC 1-36 with no gap, and no judgment page is older than its hand-down. So a judgment page last changed before the
window cannot hold a judgment inside it, and is not read. Each case page in the window is read once (again only when
its judgment page changes) for the Court's case title, case id, judgment date, neutral citation and links. The
latest-judgments page is read every run as a cross-check: a case it names that the sitemap does not yet list is read
too.

Names (15 Nov 2026, for court items): the Court's own case title, case id and neutral citation as the Court
publishes them, with `us_person_data` from the title (`party_kind`). Nothing is summarized or judged, and no judgment
text is read or kept: an item says the Court gave judgment in a case on a date, with the link.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime

from headwind import scotus

BASE = "https://supremecourt.uk"
SITEMAP = BASE + "/sitemap.xml"
LATEST = BASE + "/news/latest-judgments"
CASE_PAGE = BASE + "/cases/{slug}"
CASES_PAGE = BASE + "/cases"
FEED_DAYS = 14          # judgments in the feed, from the judgment date
YEARS = 2               # this calendar year and the last (a neutral citation is numbered by calendar year)
MIN_JUDGMENT_PAGES = 100   # 159 on 18 Nov 2026; a sitemap with far fewer is read as broken

_URL = re.compile(r"<url>\s*<loc>\s*([^<\s]+)\s*</loc>\s*(?:<lastmod>\s*([^<\s]+)\s*</lastmod>)?", re.S)
_JUDGMENT_PAGE = re.compile(r"/cases/judgments/(uksc-\d{4}-\d{4})(?:-[a-z])?/?$")
_CASE_PAGE = re.compile(r"/cases/(uksc-\d{4}-\d{4})/?$")
_CITATION = re.compile(r"^\[(?P<year>\d{4})\] UKSC (?P<number>\d+)$")


def parse_sitemap(body: bytes) -> dict:
    """The judgment pages in the sitemap, by case page slug, with the newest time any of them last changed (a case
    can have two, as uksc-2025-0058 and uksc-2025-0058-a do), and when the sitemap itself was generated (the
    home page's lastmod, which follows the sitemap's own clock)."""
    text = body.decode("utf-8-sig")
    urls = _URL.findall(text)
    judgments: dict[str, str] = {}
    other = 0
    for loc, lastmod in urls:
        if "/cases/judgments/" not in loc:
            continue
        m = _JUDGMENT_PAGE.search(loc)
        if not m:
            other += 1          # "mock-case-id2" on 18 Nov 2026, a test page that answers 404
            continue
        judgments[m.group(1)] = max(judgments.get(m.group(1)) or "", lastmod or "")
    if len(judgments) < MIN_JUDGMENT_PAGES:
        raise ValueError(f"the sitemap lists {len(judgments)} judgment pages (at least {MIN_JUDGMENT_PAGES} expected)")
    home = next((lm for loc, lm in urls if loc.rstrip("/") == BASE), None)
    return {"judgment_pages": judgments, "other_judgment_pages": other, "generated": home or None, "urls": len(urls)}


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _field(page: str, ident: str) -> list[str]:
    return [_text(m) for m in re.findall(r'<p id="%s"[^>]*>(.*?)</p>' % re.escape(ident), page, re.S)]


def _link(page: str, ident: str) -> str | None:
    m = re.search(r'<a\b[^>]*\bid="%s"[^>]*>' % re.escape(ident), page)
    h = re.search(r'href="([^"]+)"', m.group(0)) if m else None
    if not h:
        return None
    url = html.unescape(h.group(1))
    return BASE + url if url.startswith("/") else url


def _iso(text: str | None) -> str | None:
    try:
        return datetime.strptime(" ".join((text or "").split()), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def parse_case(body: bytes, slug: str) -> dict:
    """What Headwind keeps from a case page: the Court's case id and case title, and, when judgment has been given,
    the judgment date, the neutral citation and the links to the judgment (the Court's PDF and the National
    Archives' copy). Parties' details, the issue, the facts and the written arguments are never kept."""
    page = body.decode("utf-8", errors="replace")
    title = re.search(r'<h1\b[^>]*\bid="case-title"[^>]*>(.*?)</h1>', page, re.S)
    ids = _field(page, "case-id")
    dates, cites = _field(page, "judgment-date"), _field(page, "neutral-citation-number")
    if not title or not ids:
        raise ValueError(f"{slug}: no case title or case id on the page")
    case = {"slug": slug, "case_id": ids[0], "title": _text(title.group(1)), "url": CASE_PAGE.format(slug=slug)}
    if dates and cites:
        m = _CITATION.match(cites[0])
        if not m or not _iso(dates[0]):
            raise ValueError(f"{slug}: judgment date {dates[0]!r} or citation {cites[0]!r} not understood")
        case.update({"judgment_date": _iso(dates[0]), "citation": cites[0], "judgment_pdf": _link(page, "judgment-pdf"),
                     "tna_url": _link(page, "judgment-on-tna-link")})
        if len(dates) > 1 or len(cites) > 1:      # not seen on 18 Nov 2026 (160 pages); the first is kept
            case["more_judgments"] = max(len(dates), len(cites)) - 1
    return case


def parse_latest(body: bytes) -> list[str]:
    """Case page slugs linked from the latest-judgments page (the Court's newest hand-down)."""
    page = body.decode("utf-8", errors="replace")
    main = re.search(r"<main\b.*?</main>", page, re.S)
    return sorted(set(re.findall(r'href="/cases/(uksc-\d{4}-\d{4})"', main.group(0) if main else page)))


def window_start(today: date) -> str:
    return date(today.year - YEARS + 1, 1, 1).isoformat()


def to_read(judgment_pages: dict[str, str], read: dict[str, str], latest: list[str], today: date,
            limit: int) -> list[str]:
    """Case pages to read this run, newest first: a judgment page in the window (last changed on or after 1 January
    of last year) that has not been read since it last changed, and any case on the latest-judgments page not read
    yet."""
    start = window_start(today)
    due = sorted(((lm, s) for s, lm in judgment_pages.items() if lm[:10] >= start and read.get(s) != lm),
                 reverse=True)
    out = [s for s in latest if s not in read and s not in judgment_pages] + [s for _, s in due]
    return list(dict.fromkeys(out))[:limit]


def merge(previous: list[dict], cases: list[dict], today: date, now: str) -> list[dict]:
    """Judgments in the window, one per neutral citation (joined appeals share one judgment), newest first. A
    judgment keeps its first-seen time; each case on it is listed by case id with the Court's own title."""
    start = window_start(today)
    out = {j["citation"]: {**j, "cases": list(j.get("cases") or [])} for j in previous or []
           if (j.get("judgment_date") or "") >= start}
    for c in cases:
        if not c.get("citation") or c["judgment_date"] < start:
            continue
        j = out.setdefault(c["citation"], {"citation": c["citation"], "first_seen": now, "cases": []})
        j["judgment_date"] = c["judgment_date"]
        m = _CITATION.match(c["citation"])
        j["year"], j["number"] = int(m.group("year")), int(m.group("number"))
        entry = {"case_id": c["case_id"], "title": c["title"], "url": c["url"]}
        j["cases"] = sorted([x for x in j["cases"] if x["case_id"] != c["case_id"]] + [entry],
                            key=lambda x: x["case_id"])
        for k in ("judgment_pdf", "tna_url"):
            if c.get(k):
                j[k] = c[k]
    for j in out.values():
        kinds = {us_person_data(x["title"]) for x in j["cases"]}
        j["us_person_data"] = "individuals" if "individuals" in kinds else \
            "organizations" if "organizations" in kinds else "none"
    return sorted(out.values(), key=lambda j: (j["judgment_date"], j.get("year") or 0, j.get("number") or 0),
                  reverse=True)


# --- us_person_data -----------------------------------------------------------------------------------------
# The same test as the US Supreme Court's (scotus.us_person_data): "individuals" when any side of the title reads as
# a person, else "organizations" when a side is an organization that is not a government, else "none". A UK title
# needs its own clean-up first: role tags ("(Appellant)"), "R (on the application of X)", "In the matter of",
# "and others", "No 2". UK government words are added to scotus's, and so are "Limited" and the like. Two UK
# differences: "R" alone is the Crown, and initials ("BDN", "CHK", "X and Y") are anonymised people, not
# acronyms, so a side in capitals reads as a person (scotus reads it as an organization).
_ROLE = re.compile(r"\s*\((?:Appellants?|Respondents?|Petitioners?|Applicants?|Interveners?|Claimants?|"
                   r"Defendants?)\)", re.IGNORECASE)
_R_APP = re.compile(r"^R\s*\(on the application of\s+(?P<name>[^()]+)\)", re.IGNORECASE)
_PREFIX = re.compile(r"^(?:In the matter of\s+(?:an application by\s+)?|In the Petition of\s+|In re\s+)",
                     re.IGNORECASE)
_NUMBER = re.compile(r"\s+No\.?\s*\d+\s*$")
_OTHERS = re.compile(r",?\s+and (?:another|others)\b", re.IGNORECASE)
_GOV_UK = re.compile(
    r"^(?:R|The Crown|Crown)$|\b(?:Secretary of State|His Majesty|Her Majesty|Revenue and Customs|Inland Revenue|"
    r"Attorney General|Advocate General|Lord Advocate|Ministers?|Ministry|Comptroller|Prosecution Service|"
    r"Director of Public Prosecutions|Chief Constable|Police|Borough|Council|Kingdom|Republic|State|Government|"
    r"Tax Administration|Commissioners?|Executive|Assembly|Parliament|Court|Embassy)\b", re.IGNORECASE)
# Company suffixes, read first and outside brackets ("Cresta Court E RTM Company Limited" is a company, not a court;
# "Mitchell (Joint Liquidators of MBI International & Partners Inc)" is a person). Not "AB", "SE", "SA" and the like
# on their own: they are also initials of anonymised people.
_COMPANY = re.compile(r"\b(?:Ltd|Limited|Plc|LLP|LLC|Inc|Corp|Corporation|Company|GmbH|S\.?A\.?R\.?L)\b",
                      re.IGNORECASE)
_BRACKETS = re.compile(r"\s*\([^()]*\)")


def party_kind(side: str) -> str:
    """government, organization or person, from one side of a case title as the UK Supreme Court prints it."""
    s = _ROLE.sub("", " ".join(side.split())).strip()
    m = _R_APP.match(s)
    if m:
        s = m.group("name")
    s = _OTHERS.sub("", _NUMBER.sub("", _PREFIX.sub("", s))).strip(" ,")
    core = s
    while _BRACKETS.search(core):
        core = _BRACKETS.sub("", core)
    if _COMPANY.search(core):
        return "organization"
    if _GOV_UK.search(s) or scotus._GOV.search(s):
        return "government"
    if scotus._ORG.search(core):
        return "organization"
    return "person"


def us_person_data(title: str) -> str:
    sides = [s for s in re.split(r"\s+v\.?\s+", " ".join(title.split())) if s.strip()]
    kinds = {party_kind(s) for s in sides} or {"person"}
    if "person" in kinds:
        return "individuals"
    return "organizations" if "organization" in kinds else "none"
