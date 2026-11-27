"""US screening lists: what was added or removed since Headwind last looked.

One keyless file from the US International Trade Administration (trade.gov), the Consolidated
Screening List: the export-control and sanctions lists of Commerce (BIS), State and Treasury in one
JSON document, re-imported hourly. Headwind reads the lists other than the SDN list, which the
sanctions lane already reads from OFAC directly.

Same measure as sanctions.py: each run reduces every list to an index of entry id -> [type,
programs, countries, name hash, name], compares it with the index kept from the run before, and
reports the difference by address country and program, naming the entries added, removed and changed
(`headwind-1.9`; US government works). Countries are the address countries the list itself gives for an
entry; street addresses, alternative names and remarks are not carried. Each entry's start and end dates, as the
file gives them, are kept beside the index (`entry_dates`, id -> [start, end]): the Denied Persons List gives an end
date for most of its orders, and an order whose end date has passed stays in the file. The comparison does not read
them, so a state kept before them compares as before; the entity export (ftm.py) writes them.

What a delta means: the change between two of Headwind's own readings. The date on it is when
Headwind saw the change, not the date of the listing.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from . import batches, names

CSL_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
CSL_PAGE = "https://www.trade.gov/consolidated-screening-list"

SKIP = {"SDN"}          # read from OFAC's own file by the sanctions lane
MIN_ENTRIES = 3000      # the lists Headwind keeps held about 6,700 entries on 13 Nov 2026
SHRINK_LIMIT = 0.5      # a list that loses more than half its entries is a broken import, not a delisting
SHRINK_FLOOR = 20       # lists smaller than this may empty without failing the lane

_SOURCE_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<abbr>[A-Z][A-Z-]*)(?: List)?\)(?P<tail> List)?\s*-\s*(?P<pub>.+)$")
_CC_RE = re.compile(r"^[A-Z]{2}$")


def split_source(source: str) -> tuple[str, str, str]:
    """'Entity List (EL) - Bureau of Industry and Security' -> ('EL', 'Entity List', 'US Bureau of ...')."""
    m = _SOURCE_RE.match(source or "")
    if not m:
        raise ValueError(f"screening list: source name not understood: {source!r}")
    return m["abbr"], m["name"] + (m["tail"] or ""), "US " + m["pub"].strip()


def name_key(name: str | None) -> str | None:
    """A short hash of an entry's name, kept in the run state (public with the repository), so that an entry
    whose id changes when its publisher edits it can be paired with itself."""
    norm = re.sub(r"[^0-9a-z]+", " ", (name or "").casefold()).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12] if norm else None


def _countries(entry: dict) -> list[str]:
    found = {(a or {}).get("country") for a in entry.get("addresses") or []} | {entry.get("country")}
    return sorted(c for c in found if isinstance(c, str) and _CC_RE.match(c))


def parse(body: bytes | str) -> dict[str, dict]:
    """Return {abbr: {name, publisher, url, source_last_updated, index}} for every list but the skipped ones.

    A list named in the file's own source table with no entries is returned with an empty index, so a
    later first entry on it is seen as an addition and not mistaken for a first reading.
    """
    doc = json.loads(body)
    results = doc.get("results")
    if not isinstance(results, list):
        raise ValueError("screening list: no results array")
    if isinstance(doc.get("total"), int) and doc["total"] != len(results):
        raise ValueError(f"screening list: file says {doc['total']} entries and holds {len(results)}")
    lists: dict[str, dict] = {}
    for s in doc.get("sources_used") or []:
        abbr, name, pub = split_source(s.get("source"))
        if abbr not in SKIP:
            lists[abbr] = {"name": name, "publisher": pub, "url": CSL_PAGE,
                           "source_last_updated": s.get("source_last_updated"), "index": {}, "dates": {},
                           "end_dates": {}}
    for e in results:
        abbr, name, pub = split_source(e.get("source"))
        if abbr in SKIP:
            continue
        entry_id = str(e.get("id") or "").strip()
        if not entry_id:
            raise ValueError(f"screening list: an entry on {abbr} has no id")
        lst = lists.setdefault(abbr, {"name": name, "publisher": pub, "url": CSL_PAGE,
                                      "source_last_updated": None, "index": {}, "dates": {}, "end_dates": {}})
        if e.get("source_list_url") and lst["url"] == CSL_PAGE:
            lst["url"] = e["source_list_url"]
        lst["index"][entry_id] = [(e.get("type") or "not stated").lower(), sorted(e.get("programs") or []),
                                  _countries(e), name_key(e.get("name")), names.clean(e.get("name"))]
        # The listing date (the batch measure, and the state's entry_dates) and the end date (entry_dates).
        lst["dates"][entry_id] = _day(e.get("start_date"))
        lst["end_dates"][entry_id] = _day(e.get("end_date"))
    return lists


def _day(value) -> str | None:
    d = str(value or "").strip()[:10]
    return d if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None


def entry_dates(lst: dict) -> dict[str, list]:
    """{entry id: [start date, end date]} for the entries of a parsed list that the file gives either date for."""
    starts, ends = lst.get("dates") or {}, lst.get("end_dates") or {}
    out = {}
    for i in sorted(lst.get("index") or {}):
        pair = [starts.get(i), ends.get(i)]
        if any(pair):
            out[i] = pair
    return out


def check_size(lists: dict[str, dict], prev_lists: dict[str, dict] | None) -> None:
    total = sum(len(l["index"]) for l in lists.values())
    if total < MIN_ENTRIES:
        raise ValueError(f"screening list: only {total} entries parsed; the download looks cut short")
    for abbr, old in (prev_lists or {}).items():
        before, now = len(old.get("index") or {}), len((lists.get(abbr) or {}).get("index") or {})
        if before >= SHRINK_FLOOR and now < before * SHRINK_LIMIT:
            raise ValueError(f"screening list {abbr}: {now} entries against {before} before; "
                             "not reported as delistings")


def _tally(index: dict, ids) -> tuple[dict, dict, dict]:
    by_type, by_program, by_country = Counter(), Counter(), Counter()
    for i in ids:
        kind, programs, countries = index[i][:3]
        by_type[kind] += 1
        for p in programs:
            by_program[p] += 1
        for c in countries or ["none stated"]:
            by_country[c] += 1
    return dict(sorted(by_type.items())), dict(by_program.most_common()), dict(by_country.most_common())


def status(abbr: str, lst: dict, checked_at: str, baseline_set_at: str) -> dict:
    return {"id": abbr, "name": lst["name"], "publisher": lst["publisher"], "url": lst["url"],
            "total": len(lst["index"]), "checked_at": checked_at, "baseline_set_at": baseline_set_at,
            "source_last_updated": lst.get("source_last_updated")}


def rekeyed(index: dict, prev_index: dict, added: list, removed: list) -> list[tuple[str, str]]:
    """(old id, new id) pairs: an id that went and an id that came on the same list with the same name and type,
    where that name is on no other entry going or coming. trade.gov assigns the ids of the BIS and State lists
    itself, and whether an edit changes them is not known; a pair like this is the same entry under a new id."""
    def by_key(idx, ids):
        groups: dict = {}
        for i in ids:
            e = idx[i]
            if len(e) > 3 and e[3]:
                groups.setdefault((e[3], e[0]), []).append(i)
        return {k: v[0] for k, v in groups.items() if len(v) == 1}
    gone, came = by_key(prev_index, removed), by_key(index, added)
    return sorted((gone[k], came[k]) for k in set(gone) & set(came))


def entry(index: dict, i: str, dates: dict | None = None) -> dict | None:
    """One named entry of a screening index, or None for an index kept before names were (headwind-1.9)."""
    e = index[i]
    if len(e) < 5 or not e[4]:
        return None
    rec = {"list_id": i, "name": e[4], "type": e[0], "programs": list(e[1]), "countries": list(e[2])}
    if dates and dates.get(i):
        rec["listed"] = dates[i]
    return rec


def edits(prev_index: dict, index: dict, pairs: list[tuple[str, str]], compare_names: bool = True) -> dict:
    """Entries on both readings (or re-keyed) whose type, programs, address countries or name changed: counted,
    and named with the programs gained and lost and, when renamed, the name before."""
    changed, gained, lost, named_changed = [], Counter(), Counter(), []
    both = [(i, i) for i in sorted(set(index) & set(prev_index))] + list(pairs)
    for old_id, new_id in both:
        old, new = prev_index[old_id][:3], index[new_id][:3]
        before, after = entry(prev_index, old_id), entry(index, new_id)
        renamed = bool(compare_names and before and after and before["name"] != after["name"])
        if old[0] != new[0] or sorted(old[1]) != sorted(new[1]) or sorted(old[2]) != sorted(new[2]) or renamed:
            changed.append(new_id)
            gained.update(set(new[1]) - set(old[1]))
            lost.update(set(old[1]) - set(new[1]))
            if after:
                rec = {**after, "gained": sorted(set(new[1]) - set(old[1])), "lost": sorted(set(old[1]) - set(new[1]))}
                if renamed:
                    rec["name_before"] = before["name"]
                if sorted(old[2]) != sorted(new[2]):
                    rec["countries_before"] = list(old[2])
                named_changed.append(rec)
    return {"changed": len(changed), "programs_gained": dict(gained.most_common()),
            "programs_lost": dict(lost.most_common()), "named_changed": sorted(named_changed, key=names.sort_key),
            "renamed": sum(1 for r in named_changed if "name_before" in r)}


def delta(abbr: str, lst: dict, prev_index: dict, detected_at: str, prior_checked_at: str | None,
          added_history: list | None = None, compare_names: bool = True) -> dict | None:
    """The difference between two readings of one list, or None when nothing changed.

    An id that went and one that came with the same name and type are counted once, as re-keyed, and not as a
    removal and an addition."""
    index = lst["index"]
    added = sorted(set(index) - set(prev_index))
    removed = sorted(set(prev_index) - set(index))
    pairs = rekeyed(index, prev_index, added, removed)
    added = sorted(set(added) - {n for _, n in pairs})
    removed = sorted(set(removed) - {o for o, _ in pairs})
    ed = edits(prev_index, index, pairs, compare_names)
    if not added and not removed and not pairs and not ed["changed"]:
        return None
    named_added = sorted(filter(None, (entry(index, i, lst.get("dates")) for i in added)), key=names.sort_key)
    named_removed = sorted(filter(None, (entry(prev_index, i) for i in removed)), key=names.sort_key)
    batch = batches.measure(added, lst.get("dates"), added_history, detected_at)
    a_type, a_prog, a_cc = _tally(index, added)
    r_type, r_prog, r_cc = _tally(prev_index, removed)
    stamp = detected_at.replace("-", "").replace(":", "")[:13]
    return {
        "id": f"{abbr.lower()}:{stamp}", "list": abbr, "list_name": lst["name"], "publisher": lst["publisher"],
        "url": lst["url"], "detected_at": detected_at, "prior_checked_at": prior_checked_at,
        "added": len(added), "removed": len(removed), "total": len(index),
        "added_by_type": a_type, "added_by_program": a_prog, "added_by_country": a_cc,
        "removed_by_type": r_type, "removed_by_program": r_prog, "removed_by_country": r_cc,
        "rekeyed": len(pairs), **ed,
        "batches": batch, "anomaly": any(b["anomaly"] for b in batch),
        "countries": sorted(c for c in set(a_cc) | set(r_cc) if _CC_RE.match(c)),
        "named_added": named_added, "named_removed": named_removed,
        "unnamed_removed": len(removed) - len(named_removed),
        "us_person_data": names.person_data(named_added, named_removed, ed["named_changed"]),
    }


def compare(lists: dict[str, dict], state: dict, now: str) -> tuple[list[dict], list[dict], dict]:
    """Return (deltas, statuses, new_state). The first reading of the file only sets the baseline."""
    prev_lists = state.get("lists") or {}
    check_size(lists, prev_lists)
    had_baseline = bool(state.get("baseline_set_at"))
    baseline_set = state.get("baseline_set_at") or now
    deltas, statuses = [], []
    history = {a: (old.get("added_history") or []) for a, old in prev_lists.items()}
    # A list that was known and is gone from the file is compared as an empty list.
    gone = {a: {**{k: old.get(k) for k in ("name", "publisher", "url")}, "source_last_updated": None, "index": {}}
            for a, old in prev_lists.items() if a not in lists}
    for abbr, lst in sorted({**lists, **gone}.items()):
        if had_baseline and abbr in prev_lists:
            d = delta(abbr, lst, prev_lists[abbr].get("index") or {}, now, state.get("checked_at"),
                      history.get(abbr), compare_names=state.get("name_format") == names.NAME_FORMAT)
            if d:
                deltas.append(d)
                history[abbr] = batches.remember(history.get(abbr), d["added"])
        statuses.append(status(abbr, lst, now, (prev_lists.get(abbr) or {}).get("baseline_set_at") or
                               (baseline_set if abbr in prev_lists or not had_baseline else now)))
    new_state = {"checked_at": now, "baseline_set_at": baseline_set, "name_format": names.NAME_FORMAT,
                 "lists": {s["id"]: {"name": s["name"], "publisher": s["publisher"], "url": s["url"],
                                     "baseline_set_at": s["baseline_set_at"],
                                     "added_history": history.get(s["id"]) or [],
                                     "index": ({**lists, **gone})[s["id"]]["index"],
                                     "entry_dates": entry_dates(({**lists, **gone})[s["id"]])} for s in statuses}}
    return deltas, sorted(statuses, key=lambda s: -s["total"]), new_state
