"""US screening lists: what was added or removed since Headwind last looked.

One keyless file from the US International Trade Administration (trade.gov), the Consolidated
Screening List: the export-control and sanctions lists of Commerce (BIS), State and Treasury in one
JSON document, re-imported hourly. Headwind reads the lists other than the SDN list, which the
sanctions lane already reads from OFAC directly.

Same measure as sanctions.py: each run reduces every list to an index of entry id -> [type,
programs, countries], compares it with the index kept from the run before, and reports the
difference as counts. Countries are the address countries the list itself gives for an entry.
Headwind publishes counts and a link to the publisher's list. It does not republish names.

What a delta means: the change between two of Headwind's own readings. The date on it is when
Headwind saw the change, not the date of the listing.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

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
    """A short hash of an entry's name, kept only in the private state, so that an entry whose id changes
    when its publisher edits it can be paired with itself. Never published."""
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
                           "source_last_updated": s.get("source_last_updated"), "index": {}}
    for e in results:
        abbr, name, pub = split_source(e.get("source"))
        if abbr in SKIP:
            continue
        entry_id = str(e.get("id") or "").strip()
        if not entry_id:
            raise ValueError(f"screening list: an entry on {abbr} has no id")
        lst = lists.setdefault(abbr, {"name": name, "publisher": pub, "url": CSL_PAGE,
                                      "source_last_updated": None, "index": {}})
        if e.get("source_list_url") and lst["url"] == CSL_PAGE:
            lst["url"] = e["source_list_url"]
        lst["index"][entry_id] = [(e.get("type") or "not stated").lower(), sorted(e.get("programs") or []),
                                  _countries(e), name_key(e.get("name"))]
    return lists


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


def edits(prev_index: dict, index: dict, pairs: list[tuple[str, str]]) -> dict:
    """Entries on both readings (or re-keyed) whose type, programs or address countries changed. Counts only."""
    changed, gained, lost = [], Counter(), Counter()
    both = [(i, i) for i in sorted(set(index) & set(prev_index))] + list(pairs)
    for old_id, new_id in both:
        old, new = prev_index[old_id][:3], index[new_id][:3]
        if old[0] != new[0] or sorted(old[1]) != sorted(new[1]) or sorted(old[2]) != sorted(new[2]):
            changed.append(new_id)
            gained.update(set(new[1]) - set(old[1]))
            lost.update(set(old[1]) - set(new[1]))
    return {"changed": len(changed), "programs_gained": dict(gained.most_common()),
            "programs_lost": dict(lost.most_common())}


def delta(abbr: str, lst: dict, prev_index: dict, detected_at: str, prior_checked_at: str | None) -> dict | None:
    """The difference between two readings of one list, or None when nothing changed.

    An id that went and one that came with the same name and type are counted once, as re-keyed, and not as a
    removal and an addition."""
    index = lst["index"]
    added = sorted(set(index) - set(prev_index))
    removed = sorted(set(prev_index) - set(index))
    pairs = rekeyed(index, prev_index, added, removed)
    added = sorted(set(added) - {n for _, n in pairs})
    removed = sorted(set(removed) - {o for o, _ in pairs})
    ed = edits(prev_index, index, pairs)
    if not added and not removed and not pairs and not ed["changed"]:
        return None
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
        "countries": sorted(c for c in set(a_cc) | set(r_cc) if _CC_RE.match(c)),
    }


def compare(lists: dict[str, dict], state: dict, now: str) -> tuple[list[dict], list[dict], dict]:
    """Return (deltas, statuses, new_state). The first reading of the file only sets the baseline."""
    prev_lists = state.get("lists") or {}
    check_size(lists, prev_lists)
    had_baseline = bool(state.get("baseline_set_at"))
    baseline_set = state.get("baseline_set_at") or now
    deltas, statuses = [], []
    # A list that was known and is gone from the file is compared as an empty list.
    gone = {a: {**{k: old.get(k) for k in ("name", "publisher", "url")}, "source_last_updated": None, "index": {}}
            for a, old in prev_lists.items() if a not in lists}
    for abbr, lst in sorted({**lists, **gone}.items()):
        if had_baseline and abbr in prev_lists:
            d = delta(abbr, lst, prev_lists[abbr].get("index") or {}, now, state.get("checked_at"))
            if d:
                deltas.append(d)
        statuses.append(status(abbr, lst, now, (prev_lists.get(abbr) or {}).get("baseline_set_at") or
                               (baseline_set if abbr in prev_lists or not had_baseline else now)))
    new_state = {"checked_at": now, "baseline_set_at": baseline_set,
                 "lists": {s["id"]: {"name": s["name"], "publisher": s["publisher"], "url": s["url"],
                                     "baseline_set_at": s["baseline_set_at"],
                                     "index": ({**lists, **gone})[s["id"]]["index"]} for s in statuses}}
    return deltas, sorted(statuses, key=lambda s: -s["total"]), new_state
