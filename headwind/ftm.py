"""The entities on the sanctions and screening lists Headwind reads, in the FollowTheMoney format.

FollowTheMoney (FtM, https://followthemoney.tech/docs/) is the entity format of OpenSanctions and Aleph. In its
words, entities have "a unique `id`, a specification of the type of the entity called `schema`, and a set of
`properties`", whose values "are always strings"; a stream of them is "serialized to JSON as single lines without
indentation, separated by newlines", stored with the extension `.ftm`. This module writes one such stream from the
run state (data/state/sanctions_index.json and screening_index.json): for every named entry on an exported list, the
listed party (schema Person, Organization, LegalEntity, Vessel or Airplane) and one Sanction entity that links it to
the list, with the list's authority, the entry's own id on that list and its programs.

Schema and property names are FtM's own, checked line by line against the extract of FtM's published model in
headwind/ftm_model.json (tools/ftm_model.py, FtM 4.11.3): every schema exists and is not abstract, every property
belongs to the schema or one it extends, every value is a string within its type's length, countries and topics
are values FtM's types accept, dates are FtM dates, required properties are present and every entity a Sanction
names is in the file. A stream that fails is not written.

What each entity carries is what the run state carries, and nothing more: the name as the publisher prints it, the
countries of the entry's addresses and nationality (FtM `country`, the generic association; a country the model
cannot place is left out and counted), and for vessels the IMO number, MMSI, flag and vessel type. Birth dates,
identity documents, street addresses and reasons are not in the state and so not here. Ship listing dates are the
publisher's own (`Sanction:listingDate`); `Interval:retrievedAt` is when Headwind last read the list. A screening
list's start and end dates, where the CSL gives them, are the Sanction's `startDate` and `endDate`; a listing whose
end date is before the list's reading has ended, and its party carries no topic (FtM's `topics` mark what an
entity is now; OpenSanctions sets them only while a sanction is in force), so it does not read as current.

Credit: LISTS and SCREENING are the one table of each list's publisher, title, source, licence and its link, the
attribution statement its terms ask for and what Headwind changed; about.json (`attribution` per list), the
release notes (release_notes) and the site's Sources text (sources_html) are all written from it.

Lists: each one's terms were read before it was exported; `LISTS` gives the terms each is reused under and
`LEFT_OUT` the lists and parts left out and why. Entries with no name in the state (the UN Security Council's list,
and Australia's and Japan's entries under Security Council programs, which are counted only; Japan's ship list,
which gives IMO numbers and no names) cannot be written, since FtM requires a name, and are counted.

Standard library only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from . import sanctions, screening

MODEL_PATH = Path(__file__).with_name("ftm_model.json")
DOCS = "https://followthemoney.tech/docs/"
OUT_NAME = "headwind-entities.ftm.gz"
ABOUT_NAME = "headwind-entities.about.json"
RELEASE = "entities"
RELEASE_URL = "https://github.com/metacog-osint/headwind/releases/tag/" + RELEASE

SCHEMA = {"individual": "Person", "entity": "Organization", "vessel": "Vessel", "aircraft": "Airplane",
          "not stated": "LegalEntity"}

# Licences the exported lists are reused under, and where each is published.
US_WORK = "US government work, not subject to copyright in the US (17 U.S.C. 105)"
US_WORK_URL = "https://www.law.cornell.edu/uscode/text/17/105"
EU_REUSE = "Commission Decision 2011/833/EU on the reuse of Commission documents"
EU_REUSE_URL = "http://data.europa.eu/eli/dec/2011/833/oj"
OGL3 = "Open Government Licence v3.0"
OGL3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
CA_TERMS = "Government of Canada terms and conditions: reproduction for non-commercial purposes"
CA_TERMS_URL = "https://www.canada.ca/en/transparency/terms.html"
CC_BY_4 = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
PDL1 = "Public Data License 1.0 (PDL1.0)"

# What Headwind changed on every exported list. Each list's own entry in LISTS adds what was changed on it.
CHANGES_ALL = ("Modified by Headwind (The Intelligence Company): converted to FollowTheMoney entities, one listed "
               "party and one Sanction per entry. Kept: the entry's id, one name, its type, its programs and, where "
               "the list gives them, the countries of its addresses and nationality, merged into one property "
               "(`country`) as FtM country codes (a country name FtM cannot place is left out and counted); for "
               "ships the IMO number, MMSI, flag and type the list gives. Dropped: aliases, birth dates and places, "
               "identity documents, street addresses, reasons, remarks and every other field.")

# The sanctions lists exported, and how each is credited: one table, from which about.json, the release notes and
# the site's Sources text are written (`attribution`). Per list: the sanctioning jurisdiction (Sanction:country);
# `title`, `publisher`, `source` (the publisher's page, then the files read), `licence` and `licence_url`; the
# attribution statement the terms ask for (`statement`); and what Headwind changed on that list (`changes`, after
# CHANGES_ALL). `types` limits a list to some entry types. Every listing carries Headwind's key for the entry as
# `Interval:recordId`, and the publisher's own entry id as `Sanction:authorityId` where the key is that id
# (`authority_ids`): Canada's list gives none, so its key is the regime, schedule and item number
# (sanctions.canada_key).
LISTS = {
    "ofac-sdn": {
        "country": "us", "title": "Specially Designated Nationals and Blocked Persons List (SDN list)",
        "publisher": "US Department of the Treasury, Office of Foreign Assets Control (OFAC)",
        "source": [sanctions.LISTS["ofac-sdn"]["url"], sanctions.OFAC_SDN_CSV, sanctions.OFAC_ADD_CSV,
                   sanctions.OFAC_ADVANCED_ZIP],
        "licence": US_WORK, "licence_url": US_WORK_URL,
        "statement": "Source: US Department of the Treasury, Office of Foreign Assets Control (OFAC), SDN list.",
        "changes": "Names as sdn.csv prints them; countries from OFAC's address file (add.csv); ships' listing dates "
                   "from the SDN advanced XML (sdn_advanced.zip)."},
    "eu-fsf": {
        "country": "eu",
        "title": "Consolidated list of persons, groups and entities subject to EU financial sanctions",
        "publisher": "European Commission, Directorate-General for Financial Stability, Financial Services and "
                     "Capital Markets Union (Financial Sanctions Files)",
        "source": [sanctions.EU_PAGE, sanctions.EU_XML],
        "licence": EU_REUSE + " (the licence the EU open data portal gives the Financial Sanctions Files)",
        "licence_url": EU_REUSE_URL,
        "statement": "Source: European Commission, Financial Sanctions Files.",
        "changes": "One name per entry: the alias the file marks strong with the lowest alias id (else the lowest of "
                   "its aliases); countries from its citizenships and addresses."},
    "uk-sanctions": {
        "country": "gb", "types": ("entity", "vessel", "aircraft"), "title": "UK Sanctions List",
        "publisher": "UK Foreign, Commonwealth and Development Office (FCDO)",
        "source": [sanctions.UK_PAGE, sanctions.UK_XML],
        "licence": OGL3, "licence_url": OGL3_URL,
        "statement": "Contains public sector information licensed under the Open Government Licence v3.0.",
        "changes": "Individuals left out (the licence does not cover personal data): organizations and ships only. "
                   "The primary name as FCDO prints it; a ship the list names by its IMO number takes the name in "
                   "brackets, else its first alias; countries from addresses; ships' owners and operators dropped."},
    "canada-sema": {
        "country": "ca", "authority_ids": False, "title": "Consolidated Canadian Autonomous Sanctions List",
        "publisher": "Global Affairs Canada", "source": [sanctions.CA_PAGE, sanctions.CA_XML],
        "licence": CA_TERMS, "licence_url": CA_TERMS_URL,
        "statement": "Reproduced in part, for non-commercial purposes: Consolidated Canadian Autonomous Sanctions "
                     "List, Global Affairs Canada. This reproduction is a copy of part of the version available at "
                     + sanctions.CA_PAGE + ".",
        "changes": "Reproduced in part. People's names joined as 'Last, Given'; the regime named from the record's "
                   "country field; the list prints no address or nationality, so no countries; the list gives no "
                   "entry id, so the record id is Headwind's key (regime, schedule and item number); records with no "
                   "name left out."},
    "australia-dfat": {
        "country": "au", "title": "Australian Sanctions Consolidated List",
        "publisher": "Australian Department of Foreign Affairs and Trade (Australian Sanctions Office)",
        "source": [sanctions.AU_PAGE, sanctions.AU_XLSX],
        "licence": CC_BY_4, "licence_url": CC_BY_4_URL,
        "statement": "Department of Foreign Affairs and Trade website – www.dfat.gov.au. Licensed under CC BY 4.0 "
                     "(" + CC_BY_4_URL + "); modified by Headwind as stated.",
        "changes": "Australia's own designations only: entries under a UN Security Council regime, which restate "
                   "the UN's lists, are left out. The primary name only (aliases and original scripts dropped); "
                   "countries from citizenship and from the country an address ends with; for ships the name and "
                   "IMO number."},
    "japan-mof": {
        "country": "jp", "title": "経済制裁措置及び対象者リスト (Japan's asset-freeze list)",
        "publisher": "Ministry of Finance Japan (財務省)", "source": [sanctions.JP_PAGE],
        "licence": PDL1, "licence_url": sanctions.PDL_URL,
        "statement": "出典：財務省ウェブサイト（" + sanctions.JP_PAGE + "）、PDL1.0（" + sanctions.PDL_URL
                     + "）を加工して作成. Edited by Headwind (The Intelligence Company); not the Ministry's own data.",
        "changes": "Edited: Japan's own programs only (UN Security Council restatements left out); entry numbers, "
                   "types, programs with Headwind's own English program names, the English name as printed (NFKC) "
                   "and countries; the ship file gives IMO numbers and no names, so its ships are left out."},
}
# The trade.gov Consolidated Screening List (every list but the SDN list, which comes from OFAC above): US government
# works, credited per list from this template (screening_attribution). FtM topics by list: the Commerce lists are
# export controls, the State Department's ITAR debarments are debarments, and the State and Treasury sanctions lists
# are sanctions. A list not named here carries no topic.
SCREENING = {
    "publisher": "US International Trade Administration (Consolidated Screening List)",
    "source": [screening.CSL_PAGE, screening.CSL_URL], "licence": US_WORK, "licence_url": US_WORK_URL,
    "statement": "Source: US International Trade Administration, Consolidated Screening List. The CSL asks users to "
                 "check the official publication of restricted parties in the Federal Register.",
    "changes": "The name, type (an entry the CSL gives no type is a LegalEntity), programs and address countries as "
               "the CSL gives them; the listing's start and end dates as the CSL gives them (`startDate`, `endDate`). "
               "An entry whose end date is before the list's reading carries no topic, so it does "
               "not read as a current listing."}
SCREENING_TERMS = SCREENING["statement"]
SCREENING_TOPIC = {"EL": "export.control", "UVL": "export.control", "MEU": "export.control", "DPL": "export.control",
                   "DTC": "debarment", "ISN": "sanction", "ACN": "sanction", "FSE": "sanction", "SSI": "sanction",
                   "PLC": "sanction", "CAP": "sanction", "CMIC": "sanction", "NS-MBS": "sanction"}
LEFT_OUT = {
    "un-consolidated": "The UN Security Council's terms withhold redistribution of its list; Headwind counts it only, "
                       "so its state holds no names.",
    "france-gels": "The register's site states no licence, and the French Treasury's legal notice for its own site "
                   "(tresor.economie.gouv.fr, Mentions légales) treats making a product from its information for "
                   "third parties, free or not, as reuse needing its authorization; its terms do not clearly cover "
                   "a derived file, so the register is not exported.",
    "uk-sanctions individuals": "The Open Government Licence v3.0 does not cover personal data.",
}

# Countries as the lists print them that FtM's English labels do not match. Regions (OFAC's "Region: Gaza") and
# "Unknown" are left out.
COUNTRY_ALIASES = {
    "turkey": "tr", "korea north": "kp", "north korea": "kp", "dprk": "kp", "democratic people s republic of korea": "kp",
    "democratic people s republic of korea north korea": "kp", "korea south": "kr", "burma": "mm",
    "congo democratic republic of the": "cd", "congo democratic republic": "cd", "congo republic of the": "cg",
    "hong kong": "hk", "russian federation": "ru", "virgin islands british": "vg",
    "occupied palestinian territories": "ps", "state of palestine": "ps", "palestinian": "ps",
    "the gambia": "gm", "syrian arab republic": "sy", "north macedonia the republic of": "mk", "czech republic": "cz",
    "st kitts and nevis": "kn", "republic of palau": "pw", "antigua barbuda": "ag", "kyrgyz republic": "kg",
    "iran islamic republic of": "ir", "lao people s democratic republic": "la", "the bahamas": "bs",
    "macau": "mo", "vatican city": "va", "cote d ivoire": "ci", "ivory coast": "ci", "east timor": "tl",
    "united states of america": "us", "usa": "us", "uk": "gb", "great britain": "gb", "laos": "la", "vietnam": "vn",
    "viet nam": "vn", "brunei darussalam": "bn", "moldova republic of": "md", "tanzania united republic of": "tz",
    "venezuela bolivarian republic of": "ve", "bolivia plurinational state of": "bo", "republic of korea": "kr",
    "democratic peoples republic of korea": "kp", "republic of belarus": "by", "slovak republic": "sk",
    "bahamas the": "bs", "man isle of": "im", "sao tome principe": "st", "st kitts nevis": "kn",
    "st vincent and grenadines": "vc", "st vincent and the grenadines": "vc", "st vincent": "vc", "u s a": "us",
}

_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2})?)?)?)?)?$")
_SAFE = re.compile(r"[^A-Za-z0-9.-]+")
# FtM's own rule for an entity id (followthemoney/types/entity.py, EntityType.REGEX_RAW, 4.11.3): letters, digits,
# dots and hyphens, starting and ending with a letter or digit.
ENTITY_ID = re.compile(r"^[0-9a-zA-Z]([0-9a-zA-Z\.\-]*[0-9a-zA-Z])?$")


def load_model(path: Path = MODEL_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z]+", " ", t.casefold()).split())


class Countries:
    """Country names and codes as the lists print them, to FtM country codes ('Iran' -> 'ir', 'IQ' -> 'iq')."""

    def __init__(self, model: dict):
        self.codes = model["types"]["country"]["values"]
        self.labels = {_fold(label): code for code, label in self.codes.items()}
        self.missed: Counter = Counter()

    def code(self, value: str | None, list_id: str = "") -> str | None:
        v = " ".join((value or "").split())
        if not v:
            return None
        if re.fullmatch(r"[A-Za-z]{2}", v) and v.lower() in self.codes:
            return v.lower()
        f = _fold(v)
        c = self.labels.get(f) or COUNTRY_ALIASES.get(f)
        if c is None:
            self.missed[(list_id, v)] += 1
        return c

    def codes_for(self, values, list_id: str = "") -> list[str]:
        return sorted({c for c in (self.code(v, list_id) for v in values or []) if c})


_IMO = re.compile(r"(?:IMO[\s:.#-]*)?(\d{5,7})", re.I)


def imo_number(value: str | None) -> str | None:
    """An IMO number in FtM's form ('9187629' -> 'IMO9187629'), or None when it fails both IMO check-digit schemes.

    FtM's `imoNumber` has the identifier format `imo` (rigour.ids.imo, used by followthemoney 4.11.3): a value is
    cleaned to `IMO` and seven digits (five or six are left-padded with zeros) when the ship or the company check
    digit holds, and dropped otherwise. A number that fails is counted in the about file, not written."""
    m = _IMO.fullmatch((value or "").strip())
    if not m:
        return None
    v = m.group(1).zfill(7)
    d = [int(x) for x in v]
    if not any(d):
        return None
    ship = sum(x * (7 - i) for i, x in enumerate(d[:6])) % 10 == d[6]
    company = (11 - sum(x * w for x, w in zip(d, (8, 6, 4, 2, 9, 7))) % 11) % 10 == d[6]
    return f"IMO{v}" if ship or company else None


def entity_id(list_id: str, entry_id: str) -> str:
    """'hw-<list>-<entry id>'; an entry id that FtM's id rule would not take as it is (characters outside
    [A-Za-z0-9.-], or a dot or hyphen at an end) is slugged and given a short hash of the original, so two ids
    never meet."""
    safe = _SAFE.sub("-", entry_id).strip("-.")
    if safe != entry_id or not safe:
        safe = f"{safe}-{hashlib.sha1(entry_id.encode('utf-8')).hexdigest()[:8]}".lstrip("-")
    return f"hw-{list_id}-{safe}"


def _ftm_time(stamp: str | None) -> str | None:
    """An ISO UTC time as FtM writes dates (UTC, no zone): '2026-11-27T05:46:26Z' -> '2026-11-27T05:46:26'."""
    if not stamp:
        return None
    return stamp.replace("Z", "").replace("+00:00", "")[:19]


def _props(**kw) -> dict:
    """Properties with empty values dropped; every value a list of distinct strings in first-seen order."""
    out = {}
    for k, v in kw.items():
        vals = v if isinstance(v, (list, tuple)) else [v]
        vals = list(dict.fromkeys(str(x) for x in vals if x not in (None, "")))
        if vals:
            out[k] = vals
    return out


def _pair(list_id, entry_id, kind, name, countries, vessel, programs, sanction_props, topic, authority_id=True):
    eid = entity_id(list_id, entry_id)
    schema = SCHEMA.get(kind, "LegalEntity")
    props = _props(name=name, country=countries, topics=topic)
    if schema == "Vessel" and vessel:
        props.update(_props(imoNumber=vessel.get("imo_ftm"), mmsi=vessel.get("mmsi"), flag=vessel.get("flag_code"),
                            type=vessel.get("vessel_type")))
    party = {"id": eid, "schema": schema, "properties": props}
    sanction = {"id": eid + "-sanction", "schema": "Sanction",
                "properties": _props(entity=eid, recordId=entry_id, program=programs,
                                     authorityId=entry_id if authority_id else None, **sanction_props)}
    return party, sanction


ENDED_NOTE = ("Entries whose list gives an end date before Headwind's reading of that list (the Denied Persons List "
              "gives one for most of its orders, and keeps an order in the file after it ends). Each is exported "
              "with its Sanction's endDate (and startDate) and with no topic on the listed party, so it does not read "
              "as a current listing; it is not left out.")


def _day(value) -> str | None:
    d = str(value or "").strip()[:10]
    return d if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None


def has_ended(end: str | None, checked_at: str | None) -> bool:
    """Whether an end date (YYYY-MM-DD) is before the day a list was read: such a listing is no longer in force."""
    day = _day(checked_at)
    return bool(end and day and end < day)


def attribution(list_id: str, left_out: Counter | dict | None = None) -> dict:
    """The credit for one exported sanctions list, from LISTS: what the release, about.json and the site print."""
    spec = LISTS[list_id]
    return {"list": list_id, "title": spec["title"], "publisher": spec["publisher"], "source": list(spec["source"]),
            "licence": spec["licence"], "licence_url": spec["licence_url"], "statement": spec["statement"],
            "changes": f"{CHANGES_ALL} {spec['changes']}", "left_out": dict(sorted((left_out or {}).items()))}


def screening_attribution(abbr: str, lst: dict, left_out: Counter | dict | None = None) -> dict:
    """The credit for one list of the Consolidated Screening List, from SCREENING and the list's own name and
    publisher as the CSL gives them."""
    own = lst.get("url")
    source = list(SCREENING["source"]) + ([own] if own and own not in SCREENING["source"] else [])
    return {"list": "csl-" + abbr.lower(), "title": f"{lst.get('name')} ({abbr})",
            "publisher": f"{lst.get('publisher')}, in the {SCREENING['publisher']}", "source": source,
            "licence": SCREENING["licence"], "licence_url": SCREENING["licence_url"],
            "statement": SCREENING["statement"], "changes": f"{CHANGES_ALL} {SCREENING['changes']}",
            "left_out": dict(sorted((left_out or {}).items()))}


def all_attributions(screening_lists) -> list[dict]:
    """One credit per exported list: the sanctions lists of LISTS, then each screening list (`screening_lists`:
    {abbr: list} as the state keeps them, or the page's statuses, [{id, name, publisher, url}])."""
    if isinstance(screening_lists, dict):
        items = sorted(screening_lists.items())
    else:
        items = sorted(((s["id"], s) for s in screening_lists or []), key=lambda x: x[0])
    return [attribution(l) for l in LISTS] + [screening_attribution(a, lst) for a, lst in items]


NOTES_INTRO = ("The people, organizations, vessels and aircraft on the sanctions and screening lists Headwind reads, as "
               "FollowTheMoney entities (" + DOCS + "), one JSON entity per line: each listed party and a Sanction "
               "linking it to its list. As of each list's last reading; replaced every run. Not an official list: "
               "check the publisher's own list before acting on an entry. Lists, counts, what is left out and each "
               "source's terms: headwind-entities.about.json. Checksums: SHA256SUMS.")


def release_notes(about: dict) -> str:
    """The `entities` release's notes, from about.json: what the file is, then every exported list's credit
    (publisher, title, source, licence and its link, attribution statement, what was changed, entries left out)."""
    lines = [NOTES_INTRO, ""]
    ended = about.get("ended") or {}
    if ended.get("entries"):
        by = ", ".join(f"{k} {v:,}" for k, v in sorted(ended["by_list"].items()))
        n = ended["entries"]
        lines += [f"Ended listings: {n:,} {'entry' if n == 1 else 'entries'} ({by}). {ended['why']}", ""]
    lines += ["## Sources, licences and changes", "",
              f"Changed on every list: {about['changes']}", ""]
    for item in about["lists"]:
        a = item["attribution"]
        own = a["changes"][len(about["changes"]):].strip()
        left = "; ".join(f"{why}: {n:,}" for why, n in a["left_out"].items())
        lines.append(f"- **{a['title']}**, {a['publisher']}. Source: {a['source'][0]}. Licence: "
                     f"[{a['licence']}]({a['licence_url']}). {a['statement']} Changed: as on every list, and: {own}"
                     + (f" Entries left out: {left}." if left else ""))
    lines += ["", "Left out of the export: " + " ".join(f"{k}: {v}" for k, v in about["left_out"].items())]
    return "\n".join(lines) + "\n"


def sources_html(screening_lists) -> str:
    """The site's list of the export's sources (site_src/index.html, `<!-- ftm-sources -->`), from the same table."""
    rows = []
    for a in all_attributions(screening_lists):
        own = a["changes"][len(CHANGES_ALL):].strip()
        rows.append(f'<li><b>{html.escape(a["title"])}</b>, {html.escape(a["publisher"])}. '
                    f'<a href="{html.escape(a["source"][0])}">Source</a>. Licence: '
                    f'<a href="{html.escape(a["licence_url"])}">{html.escape(a["licence"])}</a>. '
                    f'{html.escape(a["statement"])} Changed: {html.escape(own)}</li>')
    return ('<details class="small"><summary>Sources, licences and changes, list by list</summary>'
            f'<p>Changed on every list: {html.escape(CHANGES_ALL)}</p><ul>' + "".join(rows) + "</ul></details>")


def entities(sanctions_state: dict, screening_state: dict, model: dict) -> tuple[list[dict], dict]:
    """(entities, about): the FtM entities of every exported list, in list then entry order, and what was written,
    left out and why."""
    countries = Countries(model)
    out: list[dict] = []
    about_lists, skipped, bad_imo = [], Counter(), Counter()
    for list_id, spec in LISTS.items():
        st = sanctions_state.get(list_id) or {}
        index = st.get("index") or {}
        meta = sanctions.LISTS[list_id]
        dates = st.get("vessel_dates") or {}
        base = {"authority": meta["publisher"], "country": spec["country"], "sourceUrl": meta["url"],
                "publisher": meta["name"], "retrievedAt": _ftm_time(st.get("checked_at"))}
        written, left = Counter(), Counter()
        for entry_id in sorted(index):
            e = index[entry_id]
            kind = e[0]
            det = e[2] if len(e) > 2 and isinstance(e[2], dict) else {}
            if kind not in spec.get("types", (kind,)):
                left["type not exported"] += 1
                continue
            if not det.get("name"):
                left["no name in the state"] += 1
                continue
            vessel = None
            cs = det.get("countries") or []
            if kind == "vessel":
                vessel = {**det, "flag_code": countries.code(det.get("flag"), list_id),
                          "imo_ftm": imo_number(det.get("imo"))}
                if det.get("imo") and not vessel["imo_ftm"]:
                    bad_imo[list_id] += 1
            party, sanction = _pair(list_id, entry_id, kind, det["name"], countries.codes_for(cs, list_id), vessel,
                                    e[1], {**base, "listingDate": dates.get(entry_id) if kind == "vessel" else None},
                                    "sanction", spec.get("authority_ids", True))
            out += [party, sanction]
            written[party["schema"]] += 1
        skipped.update({(list_id, why): n for why, n in left.items()})
        about_lists.append({"list": list_id, "name": meta["name"], "publisher": meta["publisher"], "url": meta["url"],
                            "checked_at": st.get("checked_at"), "entries": len(index),
                            "exported": dict(sorted(written.items())), "terms": spec["statement"],
                            "attribution": attribution(list_id, left)})
    s_checked = screening_state.get("checked_at")
    for abbr in sorted(screening_state.get("lists") or {}):
        lst = screening_state["lists"][abbr]
        index = lst.get("index") or {}
        list_id = "csl-" + abbr.lower()
        base = {"authority": lst.get("publisher"), "country": "us", "sourceUrl": lst.get("url"),
                "publisher": f"{lst.get('name')} (Consolidated Screening List)", "retrievedAt": _ftm_time(s_checked)}
        entry_dates = lst.get("entry_dates") or {}
        written, left, dated, ended = Counter(), Counter(), Counter(), 0
        for entry_id in sorted(index):
            e = index[entry_id]
            if len(e) < 5 or not e[4]:
                left["no name in the state"] += 1
                continue
            start, end = (list(entry_dates.get(entry_id) or []) + [None, None])[:2]
            start, end = _day(start), _day(end)
            gone = has_ended(end, s_checked)
            party, sanction = _pair(list_id, entry_id, e[0], e[4], countries.codes_for(e[2], list_id), None,
                                    list(e[1]) or [lst.get("name")], {**base, "startDate": start, "endDate": end},
                                    None if gone else SCREENING_TOPIC.get(abbr), False)
            out += [party, sanction]
            written[party["schema"]] += 1
            dated["start"] += bool(start)
            dated["end"] += bool(end)
            ended += gone
        skipped.update({(list_id, why): n for why, n in left.items()})
        about_lists.append({"list": list_id, "name": lst.get("name"), "publisher": lst.get("publisher"),
                            "url": lst.get("url"), "checked_at": s_checked, "entries": len(index),
                            "exported": dict(sorted(written.items())), "terms": SCREENING_TERMS,
                            "topic": SCREENING_TOPIC.get(abbr),
                            "with_start_date": dated["start"], "with_end_date": dated["end"], "ended": ended,
                            "attribution": screening_attribution(abbr, lst, left)})
    about = {
        "format": "FollowTheMoney entity stream (one JSON entity per line), gzip",
        "followthemoney": {"docs": DOCS, "model_version": model.get("version"), "model": model.get("source")},
        "file": OUT_NAME, "release": RELEASE_URL,
        "what": ("The entities on the sanctions and screening lists Headwind reads, as of each list's last reading: "
                 "one entity per listed party and one Sanction per listing. Names as the publisher prints them; "
                 "countries of addresses and nationality; vessels with IMO number, MMSI, flag and type. Not an "
                 "official list: check the publisher's own list before acting on an entry."),
        "entities": len(out), "lists": about_lists,
        "changes": CHANGES_ALL,
        "ended": {"why": ENDED_NOTE, "entries": sum(x.get("ended", 0) for x in about_lists),
                  "by_list": {x["list"]: x["ended"] for x in about_lists if x.get("ended")}},
        "left_out": LEFT_OUT,
        "not_written": [{"list": l, "why": why, "entries": n} for (l, why), n in sorted(skipped.items())],
        "imo_numbers_not_valid": {"why": "fail both IMO check-digit schemes, so FtM would drop them; left out",
                                  "by_list": dict(sorted(bad_imo.items()))},
        "countries_not_placed": [{"list": l, "value": v, "times": n}
                                 for (l, v), n in sorted(countries.missed.items(), key=lambda x: (-x[1], x[0]))],
    }
    return out, about


class InvalidEntity(ValueError):
    pass


def validate(stream: list[dict], model: dict) -> None:
    """Check every entity against FtM's model (headwind/ftm_model.json); raise InvalidEntity on the first fault."""
    schemata = model["schemata"]
    countries = model["types"]["country"]["values"]
    topics = model["types"]["topic"]["values"]
    max_len = model["types"]["maxLength"]
    chains: dict[str, tuple[dict, set]] = {}

    def chain(name):
        if name not in chains:
            props, required, todo, seen = {}, set(), [name], []
            while todo:
                n = todo.pop()
                if n in seen:
                    continue
                seen.append(n)
                s = schemata[n]
                for p, d in s["properties"].items():
                    props.setdefault(p, d)
                required |= set(s["required"])
                todo += s["extends"]
            chains[name] = (props, required)
        return chains[name]

    ids = set()
    for ent in stream:
        if set(ent) != {"id", "schema", "properties"}:
            raise InvalidEntity(f"{ent.get('id')}: keys {sorted(ent)}")
        eid, schema = ent["id"], ent["schema"]
        if not isinstance(eid, str) or not ENTITY_ID.match(eid) or len(eid) > max_len["entity"]:
            raise InvalidEntity(f"bad id {eid!r}")
        if eid in ids:
            raise InvalidEntity(f"{eid}: id used twice")
        ids.add(eid)
        if schema not in schemata or schemata[schema]["abstract"]:
            raise InvalidEntity(f"{eid}: schema {schema!r} is not a concrete FtM schema")
        props, required = chain(schema)
        for p, values in ent["properties"].items():
            if p not in props:
                raise InvalidEntity(f"{eid}: {schema} has no property {p!r}")
            if not isinstance(values, list) or not values:
                raise InvalidEntity(f"{eid}: {p} is not a non-empty list")
            ptype = props[p]["type"]
            limit = props[p].get("maxLength") or max_len.get(ptype)
            for v in values:
                if not isinstance(v, str) or not v.strip() or v != v.strip():
                    raise InvalidEntity(f"{eid}: {p} value {v!r} is not a clean string")
                if limit and len(v) > limit:
                    raise InvalidEntity(f"{eid}: {p} value longer than {limit}")
                if ptype == "country" and v not in countries:
                    raise InvalidEntity(f"{eid}: {p} {v!r} is not an FtM country code")
                if ptype == "topic" and v not in topics:
                    raise InvalidEntity(f"{eid}: {p} {v!r} is not an FtM topic")
                if props[p].get("format") == "imo" and imo_number(v) != v:
                    raise InvalidEntity(f"{eid}: {p} {v!r} is not an IMO number in FtM's form")
                if ptype == "entity" and not ENTITY_ID.match(v):
                    raise InvalidEntity(f"{eid}: {p} {v!r} is not an FtM entity id")
                if ptype == "date" and not _DATE.match(v):
                    raise InvalidEntity(f"{eid}: {p} {v!r} is not an FtM date")
        for p in required:
            if not ent["properties"].get(p):
                raise InvalidEntity(f"{eid}: {schema} requires {p}")
    for ent in stream:
        if ent["schema"] == "Sanction":
            for target in ent["properties"].get("entity") or []:
                if target not in ids:
                    raise InvalidEntity(f"{ent['id']}: entity {target} is not in the stream")


def write(stream: list[dict], path: Path) -> None:
    """One entity per line, gzip with no name or time in its header, so the same entities give the same bytes."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=9, mtime=0) as gz:
        for ent in stream:
            gz.write((json.dumps(ent, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))
    path.write_bytes(buf.getvalue())


def read(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write Headwind's FollowTheMoney entity export from the run state.")
    ap.add_argument("--state", default="data/state", help="folder holding sanctions_index.json and screening_index.json")
    ap.add_argument("--out", default=OUT_NAME)
    ap.add_argument("--about", default=ABOUT_NAME)
    ap.add_argument("--notes", help="also write the release notes (Markdown) to this file")
    args = ap.parse_args(argv)
    state = Path(args.state)
    s = json.loads((state / "sanctions_index.json").read_text(encoding="utf-8"))
    c = json.loads((state / "screening_index.json").read_text(encoding="utf-8"))
    model = load_model()
    stream, about = entities(s, c, model)
    validate(stream, model)
    write(stream, Path(args.out))
    Path(args.about).write_text(json.dumps(about, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    if args.notes:
        Path(args.notes).parent.mkdir(parents=True, exist_ok=True)
        Path(args.notes).write_text(release_notes(about), encoding="utf-8", newline="\n")
    kinds = Counter(e["schema"] for e in stream)
    print(f"{args.out}: {len(stream)} entities ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); "
          f"{sum(x['entries'] for x in about['not_written'])} entries not written; "
          f"{about['ended']['entries']} ended listings marked ended; "
          f"{sum(x['times'] for x in about['countries_not_placed'])} country values not placed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
