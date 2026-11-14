"""Slow lane: US import reliance for mineral commodities, from the USGS Mineral Commodity Summaries.

Two tables from the USGS data release that goes with each year's Mineral Commodity Summaries
(ScienceBase, keyless, CC0): net import reliance by commodity (Figure 2), and the share of imports
by source country for the commodities in the Summaries' import-sources figure (Figure 3). The figures are annual. They are
context, written to site/data/minerals.json. They are not feed items: nothing here changes day to day.

Headwind copies the figures as USGS gives them, including the bounds USGS prints (">95", "<25")
where it withholds the exact number. The only thing Headwind adds is a count: for how many
commodities each country is named first among the major import sources.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter

# The 2026 edition (data for 2025, published 6 Feb 2026). A new edition is a new ScienceBase item,
# so this id has to be changed by hand each year, when USGS publishes the next Summaries.
EDITION = "MCS2026"
ITEM_ID = "69837ec8b66b01367d7ec7d9"
ITEM_URL = "https://www.sciencebase.gov/catalog/item/{item}?format=json"
DOI_URL = "https://doi.org/10.5066/P1WKQ63T"
REPORT_URL = "https://doi.org/10.3133/mcs2026"
RELIANCE_FILE = "Net_Import_Reliance.csv"
SOURCES_FILE = "Major_Import_Sources.csv"
MIN_COMMODITIES = 30

# USGS country names that differ from the suite's own.
NAME_CC = {"Republic of Korea": "KR"}

# The Final 2025 List of Critical Minerals (Interior Department, US Geological Survey), 90 FR 50494,
# Federal Register document 2025-19813, published 7 Nov 2025. Copied from the notice's own sentence
# ("includes the following 60 minerals: ..."); a test reads that sentence from the notice's text and
# checks it against this tuple. The list is revised at least every three years, as a new notice, so
# this has to be changed by hand when the next final list is published.
CRITICAL_LIST = {
    "title": "Final 2025 List of Critical Minerals", "publisher": "US Department of the Interior (USGS)",
    "published": "2025-11-07", "citation": "90 FR 50494", "document": "2025-19813",
    "url": "https://www.federalregister.gov/documents/2025/11/07/2025-19813/final-2025-list-of-critical-minerals",
    "licence": "US public domain (Federal Register)",
}
CRITICAL_2025 = (
    "aluminum", "antimony", "arsenic", "barite", "beryllium", "bismuth", "boron", "cerium", "cesium", "chromium",
    "cobalt", "copper", "dysprosium", "erbium", "europium", "fluorspar", "gadolinium", "gallium", "germanium",
    "graphite", "hafnium", "holmium", "indium", "iridium", "lanthanum", "lead", "lithium", "lutetium", "magnesium",
    "manganese", "metallurgical coal", "neodymium", "nickel", "niobium", "palladium", "phosphate", "platinum",
    "potash", "praseodymium", "rhenium", "rhodium", "rubidium", "ruthenium", "samarium", "scandium", "silicon",
    "silver", "tantalum", "tellurium", "terbium", "thulium", "tin", "titanium", "tungsten", "uranium", "vanadium",
    "ytterbium", "yttrium", "zinc", "zirconium",
)
# USGS reports these list members together as one commodity, "Rare earths". Scandium and yttrium,
# which the list also names, have their own rows.
RARE_EARTHS = ("cerium", "dysprosium", "erbium", "europium", "gadolinium", "holmium", "lanthanum", "lutetium",
               "neodymium", "praseodymium", "samarium", "terbium", "thulium", "ytterbium")


def parse_list_sentence(text: str) -> list[str]:
    """The minerals named in a list notice's sentence 'includes the following N minerals: a, b, ..., and z.'

    Used by the tests to check CRITICAL_2025 against the notice, and by hand for the next notice.
    """
    flat = " ".join(text.split())
    m = re.search(r"following (\d+) minerals: (.+?)\.(?:\s|$)", flat)
    if not m:
        raise ValueError("critical minerals notice: no 'following N minerals' sentence")
    names = [n.strip() for n in re.split(r",\s*(?:and\s+)?", m.group(2)) if n.strip()]
    if len(names) != int(m.group(1)):
        raise ValueError(f"critical minerals notice: says {m.group(1)}, lists {len(names)}")
    return names


def critical_members(commodity: str) -> list[str]:
    """The 2025 list members a USGS commodity row stands for: [] for none.

    Matched on the commodity's first word ("COPPER, refined" -> copper, "Phosphate, rock" -> phosphate),
    with two exceptions: "Rare earths" stands for the fourteen rare earths the list names one by one, and
    "Metallurgical coal" is two words. A row for one form of a mineral ("MAGNESIUM COMPOUNDS", "TITANIUM,
    sponge metal") is marked with the mineral; the list names minerals, not forms.
    """
    w = _words(commodity)
    if w[:2] == ["rare", "earths"]:
        return list(RARE_EARTHS)
    if w[:2] == ["metallurgical", "coal"]:
        return ["metallurgical coal"]
    return [w[0]] if w and w[0] in CRITICAL_2025 else []


def find_files(item_body: bytes | str) -> dict:
    """From the ScienceBase item: the two tables' download links and MD5s, and the publication date."""
    doc = json.loads(item_body)
    out = {"title": doc.get("title"), "published": None, "files": {}}
    for d in doc.get("dates") or []:
        if d.get("type") == "Publication":
            out["published"] = d.get("dateString")
    for f in doc.get("files") or []:
        for key, suffix in (("reliance", RELIANCE_FILE), ("sources", SOURCES_FILE)):
            if (f.get("name") or "").endswith(suffix) and f.get("url"):
                out["files"][key] = {"name": f["name"], "url": f["url"],
                                     "md5": ((f.get("checksum") or {}).get("value") or "").lower() or None}
    missing = {"reliance", "sources"} - set(out["files"])
    if missing:
        raise ValueError(f"USGS data release: no file found for {sorted(missing)}")
    return out


def check_md5(body: bytes, expected: str | None, name: str) -> None:
    if expected and hashlib.md5(body).hexdigest() != expected:
        raise ValueError(f"{name}: the download does not match the checksum USGS lists for it")


def _number(text: str):
    """'100' -> (100, None); '>95' -> (95, '>'); 'NA' -> (None, None)."""
    t = (text or "").strip()
    bound = t[0] if t[:1] in "<>" else None
    digits = t[1:] if bound else t
    return (int(digits), bound) if digits.isdigit() else (None, None)


def _names(text: str) -> list[str]:
    return [n.strip() for n in (text or "").split(",") if n.strip() and n.strip() != "NA"]


def parse_reliance(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        nir_key = next((k for k in r if k.startswith("Net_Import_Reliance_pct")), None)
        src_key = next((k for k in r if k.startswith("Major_Import_Sources")), None)
        if not nir_key or not src_key or not (r.get("Commodity") or "").strip():
            continue
        value, bound = _number(r[nir_key])
        rows.append({"commodity": r["Commodity"].strip(), "reliance_text": r[nir_key].strip(),
                     "reliance_pct": value, "bound": bound, "sources": _names(r[src_key]),
                     "year": nir_key.rsplit("_", 1)[-1], "sources_period": src_key.split("Sources_", 1)[-1].replace("_", "-")})
    if len(rows) < MIN_COMMODITIES:
        raise ValueError(f"USGS net import reliance: only {len(rows)} commodities parsed")
    return rows


def parse_sources(text: str) -> list[dict]:
    """Import shares by source country, one record per commodity in the import-sources table.

    The table's Critical_Mineral column is kept as usgs_flag and not used: the release's metadata does
    not define it, and it is "N" for commodities that are on the 2025 critical minerals list (arsenic,
    natural graphite, niobium, tantalum).
    """
    out: dict[str, dict] = {}
    for r in csv.DictReader(io.StringIO(text)):
        src_key = next((k for k in r if k.startswith("Import_Source")), None)
        name = (r.get("Commodity") or "").strip()
        if not src_key or not name:
            continue
        rec = out.setdefault(name, {"commodity": name, "reliance_pct": _number(r.get("NIR"))[0], "shares": [],
                                    "usgs_flag": (r.get("Critical_Mineral") or "").strip() or None,
                                    "sources_period": src_key.split("Source_", 1)[-1].replace("_", "-")})
        pct = _number(r.get("Percent"))[0]
        source = (r.get(src_key) or "").strip()
        if pct is not None and source and source != "NA":
            rec["shares"].append({"source": source, "pct": pct})
    return sorted(out.values(), key=lambda m: (-(m["reliance_pct"] if m["reliance_pct"] is not None else -1), m["commodity"]))


def first_named(reliance: list[dict], cc_of) -> list[dict]:
    """For each country: the commodities for which it is named first among the major import sources."""
    lead, named = Counter(), Counter()
    which: dict[str, list[str]] = {}
    for r in reliance:
        for i, s in enumerate(r["sources"]):
            named[s] += 1
            if i == 0:
                lead[s] += 1
                which.setdefault(s, []).append(r["commodity"])
    return [{"source": s, "country": cc_of(s), "named_first": lead.get(s, 0), "named": n,
             "commodities_named_first": which.get(s, [])}
            for s, n in sorted(named.items(), key=lambda kv: (-lead.get(kv[0], 0), -kv[1], kv[0]))]


def _words(name: str) -> list[str]:
    return re.findall(r"[a-z]+", name.lower())


def reliance_as_printed(critical: list[dict], reliance: list[dict]) -> None:
    """Give each critical-mineral record the reliance figure as the reliance table prints it.

    The import-sources table carries a bare number (75) where the reliance table prints a bound
    (">75"). The two tables name commodities differently ("Graphite, natural", "GRAPHITE (NATURAL)"),
    so they are matched on the same words in any order, or failing that on the first word when only
    one commodity in the reliance table starts with it. No match leaves the bare number.
    """
    by_words = {tuple(sorted(_words(r["commodity"]))): r for r in reliance}
    by_first: dict[str, list[dict]] = {}
    for r in reliance:
        by_first.setdefault(_words(r["commodity"])[0], []).append(r)
    for m in critical:
        w = _words(m["commodity"])
        hit = by_words.get(tuple(sorted(w)))
        if hit is None and len(by_first.get(w[0], [])) == 1:
            hit = by_first[w[0]][0]
        if hit is not None and hit["reliance_pct"] == m["reliance_pct"]:
            m["reliance_text"] = hit["reliance_text"]
        else:
            m["reliance_text"] = None if m["reliance_pct"] is None else str(m["reliance_pct"])


def build(found: dict, reliance: list[dict], critical: list[dict], cc_of) -> dict:
    reliance_as_printed(critical, reliance)
    for r in reliance:
        r["critical"] = critical_members(r["commodity"])
    for m in critical:
        m["critical"] = critical_members(m["commodity"])
    in_reliance = {c for r in reliance for c in r["critical"]}
    in_sources = {c for m in critical for c in m["critical"]}
    return {
        "edition": EDITION, "title": found.get("title"), "published": found.get("published"),
        "url": DOI_URL, "report_url": REPORT_URL, "licence": "CC0 1.0 (US Geological Survey)",
        "reliance_year": reliance[0]["year"], "sources_period": reliance[0]["sources_period"],
        "reliance": [{k: r[k] for k in ("commodity", "reliance_text", "reliance_pct", "bound", "sources", "critical")}
                     for r in reliance],
        "import_sources": [{k: m[k] for k in ("commodity", "reliance_pct", "reliance_text", "shares", "critical",
                                              "usgs_flag")} for m in critical],
        "critical_list": {**CRITICAL_LIST, "count": len(CRITICAL_2025), "minerals": list(CRITICAL_2025),
                          "rare_earths_as_one": list(RARE_EARTHS),
                          "not_in_reliance_table": [c for c in CRITICAL_2025 if c not in in_reliance],
                          "not_in_import_sources": [c for c in CRITICAL_2025 if c not in in_sources]},
        "with_sources": sum(1 for r in reliance if r["sources"]),
        "by_source": first_named(reliance, cc_of),
    }
