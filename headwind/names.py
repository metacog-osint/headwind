"""Names on list changes (`headwind-1.9`, 15-16 Nov 2026: publish what the licences allow).

Every list but the UN Security Council's is named: people, organizations and ships, with the few fields Headwind
carries for them (name as the publisher prints it, type, programs, and the countries of the entry's addresses and
nationality). Birth dates, passports, street addresses, statements of reasons and other personal detail are never
carried. UN content stays counts, ids, types and dates (the UN's terms bar redistribution).

A named entry in a list index is `[type, programs, {"name": ..., "countries": [...]}]` (sanctions lists; a vessel's
third member is its vessel record) or the screening index's fifth member. The state is public with the repository,
so nothing goes into it that may not be published.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# The form of the names kept in each list's index (`name_format` in the state). A reading kept in an older form,
# or before names were kept, is not compared name by name, so a change of form is never reported as renames.
NAME_FORMAT = 1

US_WORDS = {"us", "usa", "u s", "u s a", "united states", "united states of america", "etats unis",
            "etats unis d amerique", "etats-unis"}


def clean(text: str | None) -> str | None:
    t = " ".join((text or "").split())
    return t or None


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z]+", " ", t.casefold()).split())


def is_us(country: str | None) -> bool:
    """A country as a list prints it ('US', 'United States', 'ETATS-UNIS', 'United States of America')."""
    return bool(country) and _fold(country) in {_fold(w) for w in US_WORDS}


def countries(values) -> list[str]:
    """Distinct countries as printed, without blanks and OFAC's '-0-'."""
    out = {clean(v) for v in values or []}
    return sorted(v for v in out if v and v != "-0-")


def details(name: str | None, cs=()) -> dict:
    return {"name": clean(name), "countries": countries(cs)}


def name_set_digest(values) -> str | None:
    """The first 12 hex digits of the SHA-256 of an entry's distinct names, sorted: the same for the same names in
    any order, different when one is added, removed or edited. None for an entry with no name."""
    names = sorted({c for c in (clean(v) for v in values or []) if c})
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()[:12] if names else None


def entry(index: dict, i: str, dates: dict | None = None) -> dict | None:
    """One named entry of a sanctions index (people and organizations; vessels are named in their own lists)."""
    e = index[i]
    if e[0] == "vessel" or len(e) < 3 or not isinstance(e[2], dict) or not e[2].get("name"):
        return None
    rec = {"list_id": i, "name": e[2]["name"], "type": e[0], "programs": list(e[1]),
           "countries": list(e[2].get("countries") or [])}
    if dates and dates.get(i):
        rec["listed"] = dates[i]
    return rec


def sort_key(rec: dict):
    return ((rec.get("name") or "").casefold(), rec.get("list_id") or "")


def person_data(*groups) -> str:
    """us_person_data for an item that names these entries: individuals when a named individual has a US address
    or nationality, else organizations when a named organization has one, else none. An entry of unstated type
    (trade.gov gives none for the Entity List and the Denied Persons List) counts as an individual: cautious, since
    the label never keeps an item out. Entries without a country (Canada's list prints none) cannot set it."""
    us = [r for g in groups for r in g or [] if any(is_us(c) for c in r.get("countries") or [])]
    if any(r.get("type") not in ("entity", "vessel", "aircraft") for r in us):
        return "individuals"
    if us:
        return "organizations"
    return "none"
