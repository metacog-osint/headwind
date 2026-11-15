"""US imports of critical minerals by source country, from the Census Bureau's international trade API.

Monthly general imports (customs value, US dollars, `GEN_VAL_MO`) by HS code and country of origin, for a set of HS
codes that stand for minerals on the Final 2025 List of Critical Minerals (`minerals.CRITICAL_2025`). One request per
code, the last 25 months. For each code: the newest month, imports in the last 12 months and the 12 before, the
change between them, the leading source countries and their shares, and China's share in both windows.

Context like the USGS figures, not feed items: there is no anomaly test here. The HS codes are Headwind's choice
(`CODES`): each is checked against the description the Census Bureau returns for it (`expect`), and a code whose
description no longer carries the expected word is reported, not silently read. An HS heading can hold more than the
mineral it is filed under (2615.90 holds niobium, tantalum and vanadium ores together), and ores, metals and
compounds are separate codes, so a code's figures are not a mineral's whole trade.

The key goes only into the request as it is sent (`&key=`), never into the recorded URL, the raw-copy index, the
snapshot or an error message. The Census Bureau's terms ask every product to say: "This product uses the Census
Bureau Data API but is not endorsed or certified by the Census Bureau." (read 15 Nov 2026).
"""
from __future__ import annotations

import json
import re
import urllib.parse

API = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
NOTICE = "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."
MONTHS = 25
TOP = 5

# HS code -> the list minerals it stands for, and a word the Census Bureau's own short description must carry.
CODES = {
    "2602": {"minerals": ["manganese"], "expect": "MANGANESE"},
    "2604": {"minerals": ["nickel"], "expect": "NICKEL"},
    "2605": {"minerals": ["cobalt"], "expect": "COBALT"},
    "2610": {"minerals": ["chromium"], "expect": "CHROM"},
    "2611": {"minerals": ["tungsten"], "expect": "TUNGSTEN"},
    "261510": {"minerals": ["zirconium"], "expect": "ZIRCON"},
    "261590": {"minerals": ["niobium", "tantalum", "vanadium"], "expect": "NIOB"},
    "261710": {"minerals": ["antimony"], "expect": "ANTIMONY"},
    "2504": {"minerals": ["graphite"], "expect": "GRAPHITE"},
    "280530": {"minerals": ["rare earths", "scandium", "yttrium"], "expect": "RARE"},
    "2846": {"minerals": ["rare earths", "scandium", "yttrium"], "expect": "RARE"},
    "282520": {"minerals": ["lithium"], "expect": "LITHIUM"},
    "283691": {"minerals": ["lithium"], "expect": "LITHIUM"},
    "7502": {"minerals": ["nickel"], "expect": "NICK"},          # Census spells it "NICKLE, UNWROUGHT"
    "8105": {"minerals": ["cobalt"], "expect": "COBALT"},
    "8101": {"minerals": ["tungsten"], "expect": "TUNGSTEN"},
    "8108": {"minerals": ["titanium"], "expect": "TITANIUM"},
    "8110": {"minerals": ["antimony"], "expect": "ANTIMONY"},
    "7601": {"minerals": ["aluminum"], "expect": "ALUMINUM"},
    "8001": {"minerals": ["tin"], "expect": "TIN"},
    "7901": {"minerals": ["zinc"], "expect": "ZINC"},
    "7403": {"minerals": ["copper"], "expect": "COPPER"},
    "7106": {"minerals": ["silver"], "expect": "SILVER"},
    "7110": {"minerals": ["platinum", "palladium", "rhodium", "iridium", "ruthenium"], "expect": "PLATINUM"},
}


def url(code: str, start: str) -> str:
    """The request for one HS code from month `start` (YYYY-MM), without the key."""
    q = [("get", "CTY_CODE,CTY_NAME,GEN_VAL_MO,I_COMMODITY_SDESC"), ("I_COMMODITY", code), ("time", f"from {start}")]
    return API + "?" + urllib.parse.urlencode(q)


def _is_country(code: str) -> bool:
    """Census country codes are four digits; groupings (OECD, NATO, the EU) start with 0, the total is '-'."""
    return bool(re.fullmatch(r"[1-9]\d{3}", code or ""))


def parse(body: bytes | str) -> dict:
    """{"description", "months": {YYYY-MM: {"total": value, "countries": {name: value}}}} from one reply. A reply
    with no header row is an error; an empty body (Census answers 204 for a code with no trade) is no months."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    if not text.strip():
        return {"description": None, "months": {}}
    rows = json.loads(text)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
        raise ValueError("Census reply has no header row")
    head = rows[0]
    try:
        ic, iname, ival, idesc, itime = (head.index(k) for k in ("CTY_CODE", "CTY_NAME", "GEN_VAL_MO",
                                                                  "I_COMMODITY_SDESC", "time"))
    except ValueError:
        raise ValueError(f"Census reply lacks a column: {head}") from None
    months: dict[str, dict] = {}
    desc = None
    for r in rows[1:]:
        try:
            v = float(r[ival])
        except (TypeError, ValueError, IndexError):
            continue
        m = months.setdefault(r[itime], {"total": None, "countries": {}})
        desc = desc or r[idesc]
        if r[ic] == "-":
            m["total"] = v
        elif _is_country(r[ic]) and v > 0:
            m["countries"][r[iname]] = m["countries"].get(r[iname], 0.0) + v
    return {"description": desc, "months": months}


def _window(months: dict, keys: list[str]) -> tuple[float, dict]:
    total, by = 0.0, {}
    for k in keys:
        m = months.get(k) or {}
        total += m.get("total") if m.get("total") is not None else sum((m.get("countries") or {}).values())
        for c, v in (m.get("countries") or {}).items():
            by[c] = by.get(c, 0.0) + v
    return total, by


def month_back(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:7]) - n
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def summarize(code: str, parsed: dict, end: str | None = None, start: str | None = None) -> dict:
    """One HS code's record for the snapshot. The windows are calendar months ending at `end` (the newest month any
    code gave, so every code is read over the same year), because the Census Bureau leaves out a month with no
    trade: a month missing from the reply counts as none. The year before counts only when the request reached
    back to its first month (`start`)."""
    meta = CODES[code]
    out = {"hs": code, "minerals": meta["minerals"], "description": parsed.get("description"),
           "description_ok": bool(parsed.get("description") and meta["expect"] in parsed["description"].upper())}
    keys = sorted(parsed.get("months") or {})
    if not keys:
        return {**out, "newest_month": None}
    end = end or keys[-1]
    last12 = [month_back(end, i) for i in range(11, -1, -1)]
    prior12 = [month_back(end, i) for i in range(23, 11, -1)]
    now_total, now_by = _window(parsed["months"], last12)
    reached = start is None and len(keys) >= 24 or (start is not None and start <= prior12[0])
    before_total, before_by = _window(parsed["months"], prior12) if reached else (None, {})
    top = sorted(now_by.items(), key=lambda kv: -kv[1])[:TOP]

    def share(by, total, name):
        return round(by.get(name, 0.0) / total * 100.0, 1) if total else None
    return {**out, "newest_month": keys[-1], "window": [last12[0], last12[-1]],
            "imports_12m_usd": round(now_total), "imports_prior_12m_usd": None if before_total is None else round(before_total),
            "change_pct": (round((now_total / before_total - 1.0) * 100.0, 1) if before_total else None),
            "sources": [{"country": c, "usd": round(v), "share_pct": share(now_by, now_total, c)} for c, v in top],
            "countries": len(now_by),
            "china_share_pct": share(now_by, now_total, "CHINA"),
            "china_share_prior_pct": share(before_by, before_total, "CHINA") if before_total else None}


def build(records: list[dict], errors: list[str]) -> dict:
    newest = max((r["newest_month"] for r in records if r.get("newest_month")), default=None)
    return {"source": "US Census Bureau, international trade API (general imports, customs value)",
            "notice": NOTICE, "newest_month": newest, "codes": records, "errors": errors,
            "description_mismatch": [r["hs"] for r in records if r.get("description") and not r["description_ok"]]}
