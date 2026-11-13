"""Sanctions lists: what was added or removed since Headwind last looked.

Two official lists, both keyless: the US Treasury's SDN list (OFAC, sdn.csv) and the UN Security
Council consolidated list (XML). Each run reduces a list to an index of entry id -> [type, groups],
compares it with the index kept from the run before, and reports the difference as counts by type
and by sanctions program. Headwind publishes counts and a link to the official list. People and
organizations are counts only. Vessels are the exception (Tom, 13 Nov 2026): a vessel is not a
person, so its name, IMO number, MMSI, flag and type are carried, which is what Wake needs to match.

What a delta means: the change between two of Headwind's own readings. The date on it is when
Headwind saw the change, not the date of the designation.
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
UN_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
OFAC_RECENT = "https://ofac.treasury.gov/recent-actions"
UN_PAGE = "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"

LISTS = {
    "ofac-sdn": {"name": "OFAC SDN list", "publisher": "US Treasury (OFAC)", "url": OFAC_RECENT, "min_entries": 5000},
    "un-consolidated": {"name": "UN Security Council consolidated list", "publisher": "United Nations Security Council",
                        "url": UN_PAGE, "min_entries": 300},
}
KEEP_DAYS = 30          # how long a delta stays in the snapshot
SHRINK_LIMIT = 0.5      # a list that loses more than half its entries is a broken download, not a delisting

# Sanctions programs that name a country (a tuple where a program is about two). Programs aimed at
# conduct (terrorism, narcotics, cyber, Global Magnitsky) are left out on purpose: their targets sit
# in many countries and the list does not say which. Tags were read against OFAC's program tag
# definitions page on 13 Nov 2026.
PROGRAM_COUNTRY = {
    "RUSSIA": "RU", "UKRAINE": "RU", "IRAN": "IR", "IFSR": "IR", "IFCA": "IR", "IRGC": "IR", "HRIT": "IR", "NPWMD": None,
    "DPRK": "KP", "CUBA": "CU", "SYRIA": "SY", "VENEZUELA": "VE", "BELARUS": "BY", "BURMA": "MM", "LIBYA": "LY",
    "IRAQ": "IQ", "SUDAN": "SD", "DARFUR": "SD", "SOUTH SUDAN": "SS", "SOMALIA": "SO", "YEMEN": "YE", "CAR": "CF",
    "DRCONGO": "CD", "MALI": "ML", "NICARAGUA": "NI", "ETHIOPIA": "ET", "LEBANON": "LB", "ZIMBABWE": "ZW",
    "HONG KONG": "HK", "BALKANS": None, "AFGHANISTAN": "AF", "HAITI": "HT",
    # Tags the prefix rule misplaced or missed, found against the live list on 13 Nov 2026
    "HRIT-SY": "SY", "CAATSA - RUSSIA": "RU", "CAATSA - IRAN": "IR", "MAGNIT": "RU", "PEESA": "RU",
    "SSIDES": "RU",          # the 2014 Ukraine support act, in OFAC's Ukraine/Russia program (not South Sudan)
    "UHRPA": "CN",
    "PAARSSR": "SY",         # EO 13894 as amended: accountability for Assad and regional stabilization
    # OFAC's Ukraine/Russia program. EO 13661 and 13662 name Russian officials and sectors; EO 13660
    # (undermining Ukraine) and EO 13685 (Crimea) are about both countries (Tom, 13 Nov 2026).
    "UKRAINE-EO13660": ("RU", "UA"), "UKRAINE-EO13685": ("RU", "UA"),
    # UN list types
    "Iran": "IR", "Iraq": "IQ", "DRC": "CD", "Libya": "LY", "Somalia": "SO", "Sudan": "SD", "Haiti": "HT",
    "Yemen": "YE", "GB": "GW", "SouthSudan": "SS", "Taliban": "AF",
}


def countries_for(groups) -> list[str]:
    out = set()
    for g in groups:
        cc = PROGRAM_COUNTRY.get(g) or PROGRAM_COUNTRY.get(re.split(r"[-\d]", g, maxsplit=1)[0].strip())
        if cc:
            out.update((cc,) if isinstance(cc, str) else cc)
    return sorted(out)


def parse_sdn_csv(text: str) -> dict[str, list]:
    """sdn.csv has no header: uid, name, type, programs, ... A blank type ("-0-") is an entity."""
    index = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4 or not row[0].strip().isdigit():
            continue
        kind = row[2].strip()
        programs = [p.strip() for p in re.split(r"\]\s*\[", row[3].strip().strip("[]")) if p.strip() and p.strip() != "-0-"]
        entry = ["entity" if kind in ("", "-0-") else kind, sorted(programs)]
        if kind == "vessel":
            entry.append(_vessel(row))
        index[row[0].strip()] = entry
    return index


def _blank(s: str) -> str | None:
    s = (s or "").strip()
    return None if s in ("", "-0-") else s


def _vessel(row: list[str]) -> dict:
    """The public vessel fields of an sdn.csv row. The owner column is left out: it can name a person."""
    remarks = row[11] if len(row) > 11 else ""
    imo = re.search(r"\bIMO\s+(\d{7})\b", remarks)
    mmsi = re.search(r"\bMMSI\s+(\d{9})\b", remarks)
    return {"name": _blank(row[1]), "imo": imo.group(1) if imo else None, "mmsi": mmsi.group(1) if mmsi else None,
            "flag": _blank(row[9]) if len(row) > 9 else None, "vessel_type": _blank(row[6]) if len(row) > 6 else None}


def _vessels(index: dict, ids) -> list[dict]:
    """Vessels among these entry ids, with their identifiers. An index written before 13 Nov 2026
    holds no vessel details; those vessels are counted but cannot be named."""
    out = []
    for i in ids:
        e = index[i]
        if e[0] == "vessel" and len(e) > 2 and e[2].get("name"):
            out.append({"list_id": i, **e[2], "programs": e[1]})
    return sorted(out, key=lambda v: v["name"])


def parse_un_xml(body: bytes) -> tuple[str | None, dict[str, list]]:
    root = ET.fromstring(body)
    index = {}
    for section, kind in (("INDIVIDUALS", "individual"), ("ENTITIES", "entity")):
        sec = root.find(section)
        for e in (sec if sec is not None else []):
            dataid = (e.findtext("DATAID") or "").strip()
            if dataid:
                index[dataid] = [kind, [(e.findtext("UN_LIST_TYPE") or "unknown").strip()]]
    return root.get("dateGenerated"), index


def check_size(list_id: str, index: dict, prev_index: dict | None) -> None:
    if len(index) < LISTS[list_id]["min_entries"]:
        raise ValueError(f"{list_id}: only {len(index)} entries parsed; the download looks cut short")
    if prev_index and len(index) < len(prev_index) * SHRINK_LIMIT:
        raise ValueError(f"{list_id}: {len(index)} entries against {len(prev_index)} before; not reported as delistings")


def _tally(index: dict, ids) -> tuple[dict, dict]:
    by_type, by_group = Counter(), Counter()
    for i in ids:
        kind, groups = index[i][0], index[i][1]
        by_type[kind] += 1
        for g in groups or ["none stated"]:
            by_group[g] += 1
    return dict(sorted(by_type.items())), dict(by_group.most_common())


def status(list_id: str, index: dict, checked_at: str, baseline_set_at: str, source_generated: str | None = None) -> dict:
    by_type, _ = _tally(index, index)
    return {"id": list_id, "name": LISTS[list_id]["name"], "publisher": LISTS[list_id]["publisher"],
            "url": LISTS[list_id]["url"], "total": len(index), "by_type": by_type, "checked_at": checked_at,
            "baseline_set_at": baseline_set_at, "source_generated": source_generated}


def delta(list_id: str, prev_index: dict, index: dict, detected_at: str, prior_checked_at: str | None) -> dict | None:
    """The difference between two readings of one list, or None when nothing changed."""
    added = sorted(set(index) - set(prev_index))
    removed = sorted(set(prev_index) - set(index))
    if not added and not removed:
        return None
    a_type, a_group = _tally(index, added)
    r_type, r_group = _tally(prev_index, removed)
    stamp = detected_at.replace("-", "").replace(":", "")[:13]
    return {
        "id": f"{list_id}:{stamp}", "list": list_id, "list_name": LISTS[list_id]["name"],
        "publisher": LISTS[list_id]["publisher"], "url": LISTS[list_id]["url"],
        "detected_at": detected_at, "prior_checked_at": prior_checked_at,
        "added": len(added), "removed": len(removed), "total": len(index),
        "added_by_type": a_type, "added_by_program": a_group,
        "removed_by_type": r_type, "removed_by_program": r_group,
        "vessels_added": _vessels(index, added), "vessels_removed": _vessels(prev_index, removed),
        "countries": countries_for(list(a_group) + list(r_group)),
    }


def roll(previous: list[dict], new: list[dict], now_iso: str) -> list[dict]:
    """Keep deltas for KEEP_DAYS so a change does not vanish on the next run."""
    cutoff = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen, out = set(), []
    for d in new + (previous or []):
        if d.get("id") in seen or d.get("detected_at", "") < cutoff:
            continue
        seen.add(d["id"])
        out.append(d)
    return sorted(out, key=lambda d: d["detected_at"], reverse=True)
