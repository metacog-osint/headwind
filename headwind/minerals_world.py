"""World supply concentration for mineral commodities, from the USGS Mineral Commodity Summaries chapters.

The same data release as minerals.py (DOI 10.5066/P1WKQ63T, CC0) has a second ScienceBase item, "Mineral
Commodity Summaries 2026", whose one table holds every commodity chapter in long form
(MCS2026_ALLchapters_Reconcile.csv). Its columns, from the item's metadata (read 25 Nov 2026): MCS chapter,
Section, Commodity, Country, Statistics, Statistics_detail, Unit, Year, Value, Notes, Other notes. Value is a number
or one of USGS's codes (W withheld, NA not available, XX not applicable, E estimated, a dash for zero).

Headwind reads the world rows: production (and reserves, where the chapter gives them) by country. From them it
works out, for each commodity, statistic and year, which country produces most and its share of the world total, the
top three countries' share, China's share and a Herfindahl-Hirschman index over the countries USGS names. These
are context, written to site/data/minerals.json beside the import-reliance tables; not feed items. Shares are
Headwind's arithmetic on USGS's figures; the figures themselves are copied as published.

The Section and Statistics wording was not read before this was written (no real ScienceBase
file was recorded), so the parser does not trust fixed strings: it picks rows by words ("production", "reserves") and keeps a
count of every Section and Statistics value it saw, which the page and the data file show, so a mismatch is visible
on the first live run.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from pathlib import Path

from . import minerals

WORLD_ITEM_ID = "69837e43b66b01367d7ec7c7"   # "Mineral Commodity Summaries 2026", same DOI as minerals.ITEM_ID
WORLD_FILE = "MCS2026_ALLchapters_Reconcile.csv"
MIN_SERIES = 20

# USGS country names that differ from the kit's (Natural Earth) names. Unknown names are kept with no code.
NAME_CC = {"Republic of Korea": "KR", "Korea, North": "KP", "Korea, Republic of": "KR", "Burma": "MM",
           "Congo (Kinshasa)": "CD", "Congo (Brazzaville)": "CG", "Russia": "RU", "Turkey": "TR", "Turkiye": "TR",
           "Türkiye": "TR", "Vietnam": "VN", "Laos": "LA", "Iran": "IR", "Syria": "SY", "Bolivia": "BO",
           "Venezuela": "VE", "Tanzania": "TZ", "Czechia": "CZ", "Czech Republic": "CZ", "Cote d'Ivoire": "CI",
           "Côte d'Ivoire": "CI", "United States": "US", "United Kingdom": "GB", "Macedonia": "MK",
           "North Macedonia": "MK", "Taiwan": "TW", "Kosovo": "XK", "Eswatini": "SZ"}
# Rows that are not one country.
TOTAL_RE = re.compile(r"world total", re.I)
NOT_A_COUNTRY_RE = re.compile(r"world|other countries|others|total|rest of", re.I)

# The EU Critical Raw Materials Act, Regulation (EU) 2024/1252, Annex I (17 strategic raw materials) and Annex II
# (34 critical raw materials, the strategic ones included). European Commission content, CC BY 4.0 (Commission
# Decision 2011/833/EU). Copied from the Commission's Raw Materials Information System list (read 25 Nov 2026);
# the annexes are reviewed by 24 May 2027 and every three years after, so this is changed by hand then. Keys are the
# words Headwind matches against a USGS commodity's first word; the value is the Annex's own wording.
EU_LIST = {
    "title": "Critical Raw Materials Act, Annexes I and II", "publisher": "European Union",
    "citation": "Regulation (EU) 2024/1252", "published": "2024-05-03",
    "url": "https://eur-lex.europa.eu/eli/reg/2024/1252/oj/eng",
    "licence": "CC BY 4.0 (European Commission reuse policy, Decision 2011/833/EU)",
}
EU_STRATEGIC = {
    "aluminum": "bauxite, alumina and aluminium", "bauxite": "bauxite, alumina and aluminium",
    "bismuth": "bismuth", "boron": "boron (metallurgy grade)", "cobalt": "cobalt", "copper": "copper",
    "gallium": "gallium", "germanium": "germanium", "lithium": "lithium (battery grade)",
    "magnesium": "magnesium metal", "manganese": "manganese (battery grade)", "graphite": "graphite (battery grade)",
    "nickel": "nickel (battery grade)", "platinum": "platinum group metals", "palladium": "platinum group metals",
    "rare": "rare earth elements for magnets", "silicon": "silicon metal", "titanium": "titanium metal",
    "tungsten": "tungsten",
}
EU_CRITICAL_ONLY = {
    "antimony": "antimony", "arsenic": "arsenic", "barite": "baryte", "beryllium": "beryllium",
    "metallurgical": "coking coal", "feldspar": "feldspar", "fluorspar": "fluorspar", "hafnium": "hafnium",
    "helium": "helium", "niobium": "niobium", "phosphate": "phosphate rock", "phosphorus": "phosphorus",
    "scandium": "scandium", "strontium": "strontium", "tantalum": "tantalum", "vanadium": "vanadium",
}
EU_STRATEGIC_COUNT, EU_CRITICAL_COUNT = 17, 34


def eu_mark(commodity: str) -> dict | None:
    """The EU annex entry a USGS commodity falls under, or None: {"list": "strategic"|"critical", "as": wording}."""
    w = minerals._words(commodity)  # noqa: SLF001
    if not w:
        return None
    key = w[0]
    if key == "rare" and w[1:2] == ["earths"]:
        return {"list": "strategic", "as": "rare earth elements for magnets; heavy and light rare earths"}
    if key in EU_STRATEGIC:
        return {"list": "strategic", "as": EU_STRATEGIC[key]}
    if key in EU_CRITICAL_ONLY:
        return {"list": "critical", "as": EU_CRITICAL_ONLY[key]}
    return None


def find_world_file(item_body: bytes | str) -> dict:
    """From the ScienceBase item: the all-chapters table's link and MD5, and the publication date."""
    doc = json.loads(item_body)
    pub = next((d.get("dateString") for d in doc.get("dates") or [] if d.get("type") == "Publication"), None)
    for f in doc.get("files") or []:
        if (f.get("name") or "").endswith(WORLD_FILE) and f.get("url"):
            return {"title": doc.get("title"), "published": pub, "name": f["name"], "url": f["url"],
                    "md5": ((f.get("checksum") or {}).get("value") or "").lower() or None}
    raise ValueError(f"USGS data release: no {WORLD_FILE} in item {WORLD_ITEM_ID}")


# A stored copy of the all-chapters table, read only when ScienceBase does not answer (its firewall refuses
# scheduled runners). It goes in STORED_DIR as two files: WORLD_ITEM_FILE, the item's JSON record
# (catalog/item/<WORLD_ITEM_ID>?format=json, as ScienceBase serves it), and the table itself under its own name, both
# downloaded in a browser. The table is checked against the MD5 the record lists, so only USGS's own bytes are read.
STORED_DIR = Path(__file__).resolve().parent / "stored" / "usgs_mcs2026"
WORLD_ITEM_FILE = "world_item.json"


def stored_world(stored_dir: Path | None = None) -> tuple[dict, bytes]:
    """The stored copy as (file record, table bytes), checked against the USGS MD5. FileNotFoundError when none."""
    d = Path(stored_dir or STORED_DIR)
    item = d / WORLD_ITEM_FILE
    if not item.exists():
        raise FileNotFoundError(f"no stored copy of {WORLD_FILE}")
    f = find_world_file(item.read_bytes())
    body = (d / f["name"]).read_bytes()
    minerals.check_md5(body, f["md5"], f["name"])
    return f, body


def _col(row: dict, *names: str) -> str:
    """A column by any of its spellings (case and spaces or underscores ignored)."""
    want = {re.sub(r"[\s_]+", "", n).lower() for n in names}
    for k, v in row.items():
        if k is not None and re.sub(r"[\s_]+", "", k).lower() in want:
            return (v or "").strip()
    return ""


def value(text: str) -> tuple[float | None, str | None]:
    """'1,234' -> (1234.0, None); '12e' or 'E 12' -> (12.0, 'E'); 'W' -> (None, 'W'); '—' -> (0.0, None)."""
    t = (text or "").strip()
    if t in ("—", "–", "-", "--"):
        return 0.0, None
    flag = None
    m = re.fullmatch(r"(?i)(e)?\s*([<>]?)\s*([\d,]*\.?\d+)\s*(e)?", t)
    if m:
        flag = "E" if (m.group(1) or m.group(4)) else (m.group(2) or None)
        return float(m.group(3).replace(",", "")), flag
    return None, (t.upper() or None)


def kind_of(section: str, statistics: str) -> str | None:
    """By the Statistics wording; the Section only when Statistics names neither (a section such as "World Mine
    Production and Reserves" names both)."""
    for text in (statistics.lower(), section.lower()):
        has_r, has_p = "reserve" in text, "production" in text and "capacity" not in text
        if has_r != has_p:
            return "reserves" if has_r else "production"
    return None


def parse_world(text: str) -> dict:
    """The world rows by series: {(commodity, kind, statistic, unit): {year: [(country, value, flag)]}}, plus the
    count of every Section and Statistics value seen."""
    seen_sections: dict[str, int] = defaultdict(int)
    seen_stats: dict[str, int] = defaultdict(int)
    series: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    rows = 0
    for r in csv.DictReader(io.StringIO(text)):
        rows += 1
        section, stat = _col(r, "Section"), _col(r, "Statistics")
        seen_sections[section] += 1
        seen_stats[stat] += 1
        kind = kind_of(section, stat)
        commodity, country, year = _col(r, "Commodity"), _col(r, "Country"), _col(r, "Year")
        if not kind or not commodity or not country or not re.fullmatch(r"\d{4}", year):
            continue
        if country.lower() in ("united states", "u.s.") and "world" not in section.lower() and kind == "production" \
                and not re.search(r"world", stat, re.I):
            # A US salient-statistics row, not the world table. Kept only when the row is in a world section.
            continue
        detail = _col(r, "Statistics_detail", "Statistics detail")
        name = stat + (f" ({detail})" if detail else "")
        v, flag = value(_col(r, "Value"))
        series[(commodity, kind, name, _col(r, "Unit"))][year].append((country, v, flag))
    if rows == 0:
        raise ValueError(f"{WORLD_FILE}: no rows")
    return {"rows": rows, "series": series,
            "sections_seen": dict(sorted(seen_sections.items(), key=lambda kv: -kv[1])[:40]),
            "statistics_seen": dict(sorted(seen_stats.items(), key=lambda kv: -kv[1])[:60])}


def concentration(rows: list[tuple[str, float | None, str | None]], cc_of) -> dict | None:
    """Shares for one series-year. None when fewer than two countries have a figure or there is no total."""
    total_row = next((v for c, v, _ in rows if TOTAL_RE.search(c) and v), None)
    countries = [(c, v, f) for c, v, f in rows if not NOT_A_COUNTRY_RE.search(c)]
    named = [(c, v, f) for c, v, f in countries if v is not None]
    withheld = sorted(c for c, v, f in countries if v is None)
    if len(named) < 2:
        return None
    others = sum(v for c, v, _ in rows if v is not None and NOT_A_COUNTRY_RE.search(c) and not TOTAL_RE.search(c))
    total = total_row if total_row else sum(v for _, v, _ in named) + others
    if not total:
        return None
    named.sort(key=lambda x: (-x[1], x[0]))
    shares = [{"country": c, "cc": cc_of(c), "value": v, "share": round(v / total, 4),
               **({"flag": f} if f else {})} for c, v, f in named]
    china = next((s["share"] for s in shares if s["cc"] == "CN"), None)
    return {
        "total": total, "total_basis": "world total as USGS prints it" if total_row else
        "sum of the countries USGS names and its 'other countries' row",
        "top": shares[0], "top3_share": round(sum(s["share"] for s in shares[:3]), 4),
        "china_share": china, "hhi": round(sum((s["share"] * 100) ** 2 for s in shares)),
        "countries_named": len(named), "withheld": withheld, "shares": shares[:10],
    }


def build_world(parsed: dict, cc_of, critical_of=minerals.critical_members) -> dict:
    """One record per series, for its latest year with figures."""
    out = []
    for (commodity, kind, stat, unit), years in parsed["series"].items():
        for year in sorted(years, reverse=True):
            c = concentration(years[year], cc_of)
            if c:
                out.append({"commodity": commodity, "kind": kind, "statistic": stat, "unit": unit, "year": year,
                            "critical": critical_of(commodity), "eu": eu_mark(commodity), **c})
                break
    out.sort(key=lambda s: (s["kind"] != "production", -(s["top"]["share"]), s["commodity"], s["statistic"]))
    return {"series": out, "rows_read": parsed["rows"], "sections_seen": parsed["sections_seen"],
            "statistics_seen": parsed["statistics_seen"],
            "note": ("Shares are Headwind's arithmetic on USGS's figures for the latest year USGS gives: each country's "
                     "figure over the world total USGS prints, or over the sum of named countries and 'other countries' "
                     "where it prints none. The Herfindahl-Hirschman index (HHI) is the sum of squared percentage "
                     "shares of the countries USGS names (10,000 is one country; US antitrust practice calls above "
                     "2,500 highly concentrated). Withheld (W) figures are left out, so a share can be overstated "
                     "where a large producer is withheld.")}


def eu_list_record() -> dict:
    strategic = sorted(set(EU_STRATEGIC.values()) | {"rare earth elements for magnets"})
    # Annex II names the rare earths as heavy and light, where Annex I names those for magnets.
    critical = sorted((set(strategic) - {"rare earth elements for magnets"}) | set(EU_CRITICAL_ONLY.values())
                      | {"heavy rare earth elements", "light rare earth elements"})
    return {**EU_LIST, "strategic": strategic, "critical": critical,
            "strategic_count": EU_STRATEGIC_COUNT, "critical_count": EU_CRITICAL_COUNT}
