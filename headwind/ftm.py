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
publisher's own (`Sanction:listingDate`); `Interval:retrievedAt` is when Headwind last read the list.

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
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from . import sanctions

MODEL_PATH = Path(__file__).with_name("ftm_model.json")
DOCS = "https://followthemoney.tech/docs/"
OUT_NAME = "headwind-entities.ftm.gz"
ABOUT_NAME = "headwind-entities.about.json"
RELEASE = "entities"
RELEASE_URL = "https://github.com/metacog-osint/headwind/releases/tag/" + RELEASE

SCHEMA = {"individual": "Person", "entity": "Organization", "vessel": "Vessel", "aircraft": "Airplane",
          "not stated": "LegalEntity"}

# The sanctions lists exported: the sanctioning jurisdiction (Sanction:country) and the terms each is reused under,
# with the attribution or statement those terms ask for. `types` limits a list to some entry types. Every listing
# carries Headwind's key for the entry as `Interval:recordId`, and the publisher's own entry id as
# `Sanction:authorityId` where the key is that id (`authority_ids`): Canada's list gives none, so its key is the
# regime, schedule and item number (sanctions.canada_key).
LISTS = {
    "ofac-sdn": {"country": "us", "terms": "US government work, not subject to copyright in the US (17 U.S.C. 105)."},
    "eu-fsf": {"country": "eu", "terms": "Reused under Commission Decision 2011/833/EU on the reuse of Commission "
                                         "documents (the licence the EU open data portal gives the Financial Sanctions "
                                         "Files). Source: European Commission, Financial Sanctions Files."},
    "uk-sanctions": {"country": "gb", "types": ("entity", "vessel", "aircraft"),
                     "terms": "Contains public sector information licensed under the Open Government Licence v3.0. "
                              "The licence does not cover personal data, so individuals are not exported."},
    "canada-sema": {"country": "ca", "authority_ids": False,
                    "terms": "Reproduced in part, for non-commercial purposes, under the Government of Canada's terms "
                             "(canada.ca/en/transparency/terms.html): Consolidated Canadian Autonomous Sanctions "
                             "List, Global Affairs Canada. This reproduction is a copy of part of the version "
                             "available at " + sanctions.CA_PAGE + "."},
    "australia-dfat": {"country": "au",
                       "terms": "Australian Sanctions Consolidated List, CC BY 4.0. Source: Department of Foreign "
                                "Affairs and Trade website - www.dfat.gov.au"},
    "japan-mof": {"country": "jp",
                  "terms": "出典：財務省ウェブサイト（" + sanctions.JP_PAGE + "）、PDL1.0（" + sanctions.PDL_URL
                           + "）を加工して作成. Edited by Headwind (The Intelligence Company): entry numbers, types, "
                           "programs, English names and countries, with Headwind's own English program names."},
}
# The trade.gov Consolidated Screening List (every list but the SDN list, which comes from OFAC above): US government
# works. FtM topics by list: the Commerce lists are export controls, the State Department's ITAR debarments are
# debarments, and the State and Treasury sanctions lists are sanctions. A list not named here carries no topic.
SCREENING_TERMS = ("US government work, not subject to copyright in the US (17 U.S.C. 105), from the US "
                   "International Trade Administration's Consolidated Screening List.")
SCREENING_TOPIC = {"EL": "export.control", "UVL": "export.control", "MEU": "export.control", "DPL": "export.control",
                   "DTC": "debarment", "ISN": "sanction", "ACN": "sanction", "FSE": "sanction", "SSI": "sanction",
                   "PLC": "sanction", "CAP": "sanction", "CMIC": "sanction", "NS-MBS": "sanction"}
LEFT_OUT = {
    "un-consolidated": "The UN Security Council's terms withhold redistribution of its list; Headwind counts it only, "
                       "so its state holds no names.",
    "france-gels": "The French Treasury's own reuse notice (tresor.economie.gouv.fr, Mentions légales) treats making a "
                   "product from its information available to third parties, free or not, as reuse needing its "
                   "authorization, so the register is not exported.",
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
        written = Counter()
        for entry_id in sorted(index):
            e = index[entry_id]
            kind = e[0]
            det = e[2] if len(e) > 2 and isinstance(e[2], dict) else {}
            if kind not in spec.get("types", (kind,)):
                skipped[(list_id, "type not exported")] += 1
                continue
            if not det.get("name"):
                skipped[(list_id, "no name in the state")] += 1
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
        about_lists.append({"list": list_id, "name": meta["name"], "publisher": meta["publisher"], "url": meta["url"],
                            "checked_at": st.get("checked_at"), "entries": len(index),
                            "exported": dict(sorted(written.items())), "terms": spec["terms"]})
    s_checked = screening_state.get("checked_at")
    for abbr in sorted(screening_state.get("lists") or {}):
        lst = screening_state["lists"][abbr]
        index = lst.get("index") or {}
        list_id = "csl-" + abbr.lower()
        base = {"authority": lst.get("publisher"), "country": "us", "sourceUrl": lst.get("url"),
                "publisher": f"{lst.get('name')} (Consolidated Screening List)", "retrievedAt": _ftm_time(s_checked)}
        written = Counter()
        for entry_id in sorted(index):
            e = index[entry_id]
            if len(e) < 5 or not e[4]:
                skipped[(list_id, "no name in the state")] += 1
                continue
            party, sanction = _pair(list_id, entry_id, e[0], e[4], countries.codes_for(e[2], list_id), None,
                                    list(e[1]) or [lst.get("name")], base, SCREENING_TOPIC.get(abbr), False)
            out += [party, sanction]
            written[party["schema"]] += 1
        about_lists.append({"list": list_id, "name": lst.get("name"), "publisher": lst.get("publisher"),
                            "url": lst.get("url"), "checked_at": s_checked, "entries": len(index),
                            "exported": dict(sorted(written.items())), "terms": SCREENING_TERMS,
                            "topic": SCREENING_TOPIC.get(abbr)})
    about = {
        "format": "FollowTheMoney entity stream (one JSON entity per line), gzip",
        "followthemoney": {"docs": DOCS, "model_version": model.get("version"), "model": model.get("source")},
        "file": OUT_NAME, "release": RELEASE_URL,
        "what": ("The entities on the sanctions and screening lists Headwind reads, as of each list's last reading: "
                 "one entity per listed party and one Sanction per listing. Names as the publisher prints them; "
                 "countries of addresses and nationality; vessels with IMO number, MMSI, flag and type. Not an "
                 "official list: check the publisher's own list before acting on an entry."),
        "entities": len(out), "lists": about_lists,
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
    args = ap.parse_args(argv)
    state = Path(args.state)
    s = json.loads((state / "sanctions_index.json").read_text(encoding="utf-8"))
    c = json.loads((state / "screening_index.json").read_text(encoding="utf-8"))
    model = load_model()
    stream, about = entities(s, c, model)
    validate(stream, model)
    write(stream, Path(args.out))
    Path(args.about).write_text(json.dumps(about, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    kinds = Counter(e["schema"] for e in stream)
    print(f"{args.out}: {len(stream)} entities ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); "
          f"{sum(x['entries'] for x in about['not_written'])} entries not written; "
          f"{sum(x['times'] for x in about['countries_not_placed'])} country values not placed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
