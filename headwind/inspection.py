"""Filings on Federal Register public inspection by BIS, OFAC and USTR (keyless API). Plan step 10.

A document goes on public inspection at the Office of the Federal Register a business day or more before it is
published: the earliest public sight of a rule, a stay or a notice. Each run reads the issues of the last
DAYS_READ days (the API's agency filter is ignored for public inspection, so each issue is read whole and
filtered here), keeps the three agencies' filings for KEEP_DAYS, and reads the text of each rule, proposed rule
and USTR notice for its action line, RINs, docket numbers and the dates it says were scheduled.

HW-IND-2 (doctrine/indicators.json) is measured here: a BIS or USTR stay, suspension, extension or Entity List
filing made within WINDOW_DAYS before a scheduled date. A scheduled date is one an earlier document set (the
register in controls.scheduled(), matched on RIN, docket number or, for USTR, the investigation its title names)
or one the filing itself says was scheduled ("The suspension was set to end November 9, 2026.").

OFAC's and BIS's notices (sanctions actions, denial orders) carry their titles since `headwind-1.9` (15 Nov
2026: publish what the licences allow; Federal Register documents may be reproduced without restriction). A BIS
order names its party in the title, so such a filing carries us_person_data `individuals` (`person_label`).
Filings kept from before as counted only (no title) age out within 30 days.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from . import controls

PI_API = "https://www.federalregister.gov/api/v1/public-inspection-documents.json"
PI_PAGE = "https://www.federalregister.gov/public-inspection/current"
DOC_PAGE = "https://www.federalregister.gov/d/{id}"   # the register's short address: the number, no title slug
DAYS_READ = 5          # issues read each run, today's included: covers a long weekend between runs
KEEP_DAYS = 30         # a filing stays in the snapshot this long
FEED_DAYS = 7          # and in the feed this long (by then it is published and shows as a rule or notice)
WINDOW_DAYS = 14       # HW-IND-2: filed within this many days before a scheduled date
PER_PAGE = 1000
FIELDS = ["document_number", "title", "type", "filing_type", "agencies", "filed_at", "publication_date", "html_url",
          "pdf_url", "raw_text_url", "pdf_updated_at", "editorial_note", "docket_numbers", "num_pages"]
INDICATOR_AGENCIES = ("BIS", "USTR")     # HW-IND-2 is written for BIS or USTR

_STAY = re.compile(r"\b(?:stay(?:s|ed)?|suspen\w*|extend\w*|extension\w*|delay\w*|postpon\w*)\b", re.I)
_NOT_STAY = re.compile(r"comment period|information collection|time to comment", re.I)
_ENTITY = re.compile(r"\bEntity List\b", re.I)
# A phrase that says a date was already scheduled; the first date after it (within a few words) is the date.
_SCHEDULED = re.compile(r"\b(?:set|scheduled|due|was|were) to (?:end|expire|terminate|lapse|take effect|resume|be "
                        r"reimposed)\b|\bscheduled (?:expiration|expiry|end|termination)\b", re.I)
_ABBREV = re.compile(r"(?:\b(?:U\.S|U\.N|No|Nos|Inc|Co|Corp|Ltd|Dept|e\.g|i\.e|a\.m|p\.m|Mr|Ms|Dr|St|Jr|vs?|etc|"
                     r"Fed|Reg|Pub|Stat|Sec|Secs|Art)|\b[A-Z])\.$")
_ACTION = re.compile(r"ACTION:\s*(.+?)\s*(?:SUMMARY|DATES|ADDRESSES|FOR FURTHER INFORMATION CONTACT|"
                     r"SUPPLEMENTARY INFORMATION|AGENCY):")


def days_to_read(today: date, last_ok: str | None) -> int:
    """DAYS_READ after a good reading; back to the last good reading after a gap; KEEP_DAYS on a first run."""
    if not last_ok:
        return KEEP_DAYS
    try:
        gap = (today - date.fromisoformat(last_ok[:10])).days
    except ValueError:
        return KEEP_DAYS
    return max(DAYS_READ, min(KEEP_DAYS, gap + DAYS_READ))


def pi_url(day: str) -> str:
    q = [f"conditions%5Bavailable_on%5D={day}", f"per_page={PER_PAGE}"] + [f"fields%5B%5D={f}" for f in FIELDS]
    return PI_API + "?" + "&".join(q)


def to_utc(iso: str | None) -> str | None:
    """The API's local time with offset ("2026-11-05T16:15:00.000-05:00") in UTC ("2026-11-05T21:15:00Z")."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def parse_issue(body: bytes | str, day: str) -> list[dict]:
    """The three agencies' filings in one issue. A short page is an error, not a quiet day."""
    doc = json.loads(body)
    results = doc.get("results") or []
    if (doc.get("count") or 0) > len(results):
        raise ValueError(f"public inspection for {day} returned {len(results)} of {doc.get('count')} filings")
    out = []
    for r in results:
        agency = controls.agency_of(r.get("agencies"))
        if not agency or not r.get("document_number"):
            continue
        title = " ".join((r.get("title") or "").split())
        kind = (r.get("type") or "").strip()
        if agency == "USTR" and kind == "Notice" and controls.ADMIN_TITLE.search(title):
            continue
        counted_only = False            # headwind-1.9: every filing is titled; the key stays for kept records
        note = " ".join((r.get("editorial_note") or "").split())
        out.append(public_form({
            "id": r["document_number"], "agency": agency, "type": kind or "Unknown",
            "filing_type": r.get("filing_type"), "issue": day,
            "filed_at": r.get("filed_at"), "filed_at_utc": to_utc(r.get("filed_at")),
            "filed_on": (r.get("filed_at") or "")[:10] or day,
            "publication_date": r.get("publication_date"),
            "url": r.get("html_url") or PI_PAGE, "raw_text_url": r.get("raw_text_url"),
            "pdf_updated_at": r.get("pdf_updated_at"), "pages": r.get("num_pages"),
            "withdrawn": bool(re.search(r"withdraw", note, re.I)), "note": note[:300] or None,
            "counted_only": counted_only,
            "title": None if counted_only else title,
            "dockets": [] if counted_only else controls.docket_tokens(r.get("docket_numbers")),
        }))
    return out


def public_form(rec: dict) -> dict:
    """A counted-only filing as it may be published. The register's addresses carry the title as a slug
    ("denial-of-export-privileges-<names>"), and an editorial note can quote it, so such a filing keeps the
    document number's short address and no text address or note. Applied to kept filings too (merge)."""
    if not rec.get("counted_only"):
        return rec
    return {**rec, "url": DOC_PAGE.format(id=rec["id"]), "raw_text_url": None, "note": None, "title": None,
            "dockets": []}


# A BIS notice that names a party: denial orders, orders and their renewals or modifications.
_BIS_PARTY = re.compile(r"\b(denial|denying|order|in the matter of|temporary denial)\b", re.I)


def person_label(rec: dict) -> str:
    """us_person_data for a filing item. A BIS order names its party in the title, and parties are often in the US
    (export violators convicted in US courts), so it is `individuals` (cautious: it never keeps an item out). OFAC's
    notice titles are generic ("Notice of OFAC Sanctions Actions") and USTR's and the rules name no person: none."""
    if rec.get("agency") == "BIS" and rec.get("type") == "Notice" and _BIS_PARTY.search(rec.get("title") or ""):
        return "individuals"
    return "none"


def party_notice(rec: dict) -> bool:
    """OFAC's and BIS's notices (sanctions actions, denial orders): titled since headwind-1.9, but their texts are
    not read and HW-IND-2 is not measured on them, as before."""
    return rec.get("type") == "Notice" and rec.get("agency") in ("BIS", "OFAC")


def wants_text(rec: dict) -> bool:
    return not rec.get("counted_only") and not party_notice(rec) and bool(rec.get("raw_text_url"))


def sentences(flat: str) -> list[str]:
    """Sentences of a flattened text. A closing quote after the full stop (".'' The") still ends one, and a
    heading label ("SUMMARY: ") is taken off the front. "U.S." and the like do not end a sentence."""
    out = []
    for s in re.split(r"(?<=[.;])[\u2019\u201d\"']*\s+(?=[A-Z(\u2018\u201c])", flat):
        s = re.sub(r"^(?:[A-Z][A-Z ]{2,}:\s*)+", "", s).strip()
        if not s:
            continue
        if out and _ABBREV.search(out[-1]):
            out[-1] = out[-1] + " " + s
        else:
            out.append(s)
    return out


def read_text(body: bytes | str) -> dict:
    """What a filing's text says, without keeping the text: its action line, RINs, docket numbers (from the
    heading, before SUMMARY), the first sentence of its SUMMARY, and each date it says was already scheduled,
    with that sentence."""
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    flat = " ".join(text.split())
    head = flat.split("SUMMARY:", 1)[0][:3000]
    m = _ACTION.search(flat[:6000])
    summary = flat.split("SUMMARY:", 1)[1] if "SUMMARY:" in flat else ""
    first = (sentences(summary[:2000]) or [""])[0][:400] or None
    schedule = {}
    for sentence in sentences(flat):
        for ph in _SCHEDULED.finditer(sentence):
            d = controls._DATE_RE.search(sentence, ph.end())
            if not d or d.start() - ph.end() > 40:
                continue
            try:
                iso = date(int(d.group(3)), controls._MONTHS[d.group(1)], int(d.group(2))).isoformat()
            except ValueError:
                continue
            schedule.setdefault(iso, sentence[:240])
    return {"action": m.group(1).rstrip(" .;")[:160] if m else None,
            "summary_first": first,
            "rins": sorted(set(controls._RIN.findall(head))),
            "dockets": controls.docket_tokens([head]),
            "schedule": [{"date": k, "sentence": v} for k, v in sorted(schedule.items())]}


def merge(prev: list[dict], read: list[dict], now: str, today: date) -> list[dict]:
    """This run's filings over the ones kept from earlier runs. A filing keeps when Headwind first saw it, and the
    reading of its text while the PDF has not been replaced."""
    old = {r["id"]: r for r in prev or []}
    out = {}
    for r in read:
        o = old.get(r["id"]) or {}
        r = {**r, "first_seen_at": o.get("first_seen_at") or now}
        if o.get("text") and o.get("pdf_updated_at") == r.get("pdf_updated_at"):
            r["text"] = o["text"]
        out[r["id"]] = r
    for rid, o in old.items():
        out.setdefault(rid, public_form(o))
    lo = (today - timedelta(days=KEEP_DAYS)).isoformat()
    keep = [r for r in out.values() if (r.get("filed_on") or r.get("issue") or "") >= lo]
    return sorted(keep, key=lambda r: (r.get("filed_at_utc") or r.get("issue") or "", r["id"]), reverse=True)


def kind(rec: dict) -> str:
    """stay_or_extension, entity_list or other, from the title, the action line and the SUMMARY's first sentence
    (a USTR notice titled "...; Modification" says "to further suspend that action" only there)."""
    text = rec.get("text") or {}
    words = " ".join(x for x in (rec.get("title"), text.get("action"), text.get("summary_first")) if x)
    if _ENTITY.search(words):
        return "entity_list"
    if _STAY.search(words) and not _NOT_STAY.search(words):
        return "stay_or_extension"
    return "other"


def match(records: list[dict], register: list[dict]) -> list[dict]:
    """Scheduled dates within WINDOW_DAYS after each filing, and HW-IND-2's state for BIS and USTR filings. A date
    counts when an earlier document of the same agency set it and shares the filing's RIN, a docket number or (USTR)
    the investigation its title names, or when the filing itself says the date was scheduled."""
    for r in records:
        for k in ("matches", "days_to_deadline", "kind", "indicator_state"):
            r.pop(k, None)
        if r.get("counted_only") or party_notice(r):
            continue
        filed = date.fromisoformat(r["filed_on"])
        lo, hi = filed.isoformat(), (filed + timedelta(days=WINDOW_DAYS)).isoformat()
        text = r.get("text") or {}
        rins = set(text.get("rins") or [])
        dockets = set(r.get("dockets") or []) | set(text.get("dockets") or [])
        subj = controls.subject(r.get("title")) if r["agency"] == "USTR" else None
        found = []
        for e in register or []:
            if e["agency"] != r["agency"] or e["doc"] == r["id"] or e["published"] >= lo or not lo <= e["date"] <= hi:
                continue
            same_rin = sorted(rins & set(e.get("rins") or []))
            same_docket = sorted(dockets & set(e.get("dockets") or []))
            if same_rin:
                basis = f"same RIN {', '.join(same_rin)}"
            elif same_docket:
                basis = f"same docket {', '.join(same_docket)}"
            elif subj and e.get("subject") == subj:
                basis = "same investigation"
            else:
                continue
            found.append({"date": e["date"], "days": (date.fromisoformat(e["date"]) - filed).days, "basis": basis,
                          "doc": e["doc"], "doc_published": e["published"], "what": e["what"], "url": e["url"]})
        for s in text.get("schedule") or []:
            if lo <= s["date"] <= hi:
                found.append({"date": s["date"], "days": (date.fromisoformat(s["date"]) - filed).days,
                              "basis": "the filing says it was scheduled", "sentence": s["sentence"]})
        found.sort(key=lambda m: (m["days"], m.get("doc") or "~"))
        r["matches"] = found
        r["days_to_deadline"] = found[0]["days"] if found else None
        r["kind"] = kind(r)
        if r["agency"] in INDICATOR_AGENCIES:
            if r["kind"] != "other" and found:
                r["indicator_state"] = "present"
            elif not text and not found:
                r["indicator_state"] = "no_data"
            else:
                r["indicator_state"] = "absent"
    return records


def counted(records: list[dict]) -> dict[str, int]:
    """Notices kept as counts only, by agency."""
    c: dict[str, int] = {}
    for r in records:
        if r.get("counted_only"):
            c[r["agency"]] = c.get(r["agency"], 0) + 1
    return dict(sorted(c.items()))
