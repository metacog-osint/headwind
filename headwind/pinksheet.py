"""World Bank Commodity Price Data (the Pink Sheet), monthly: fertilizer prices and the prices of the metals on the
US Final 2025 List of Critical Minerals (plan step 12, built 16 Nov 2026).

The World Bank's data catalog lists the data as "Commodity Prices - History and Projections" (dataset 0038238,
read 16 Nov 2026): Creative Commons Attribution 4.0. The monthly file (`CMO-Historical-Data-Monthly.xlsx`) moves to
a new address each year, so the lane reads the address from the Commodity Markets page first. Prices are monthly
averages in nominal US dollars; the World Bank updates the file on the second business day of the month.

Each series is measured like FAO's indices: the latest month-on-month change against the series' own 120 earlier
monthly changes (robust z), an anomaly at |z| >= 3.5 and a move of at least FLOOR percent. Standard library only:
the workbook is a zip of XML parts.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

from . import stats

PAGE = "https://www.worldbank.org/en/research/commodity-markets"
CATALOG = "https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections"
HORIZON, WINDOW, FLOOR = 1, 120, 3.0     # one month against ten years; at least 3% (single prices move more than FAO's indices)
# Phosphate rock is flat for months and then steps: at 3% it would trip the rule in 27.5% of its last 120 months
# (5.8% at 10%, about TSP's rate). Measured on the 3 Nov 2026 file.
FLOORS = {"phosphate-rock": 10.0}

# Column header in "Monthly Prices" -> (id, name, group, name on the critical-minerals list or None).
# Phosphate rock and potash are on the 2025 list as "phosphate" and "potash"; DAP, TSP and urea are not.
# Iron ore and gold are in the file but not on the list, so they are not read.
SERIES = {
    "Phosphate rock": ("phosphate-rock", "Phosphate rock", "fertilizer", "phosphate"),
    "DAP": ("dap", "DAP (diammonium phosphate)", "fertilizer", None),
    "TSP": ("tsp", "TSP (triple superphosphate)", "fertilizer", None),
    "Urea": ("urea", "Urea", "fertilizer", None),
    "Potassium chloride": ("potash", "Potassium chloride (potash)", "fertilizer", "potash"),
    "Aluminum": ("aluminum", "Aluminum", "metal", "aluminum"),
    "Copper": ("copper", "Copper", "metal", "copper"),
    "Lead": ("lead", "Lead", "metal", "lead"),
    "Tin": ("tin", "Tin", "metal", "tin"),
    "Nickel": ("nickel", "Nickel", "metal", "nickel"),
    "Zinc": ("zinc", "Zinc", "metal", "zinc"),
    "Platinum": ("platinum", "Platinum", "metal", "platinum"),
    "Silver": ("silver", "Silver", "metal", "silver"),
}
MIN_SERIES = 10      # a file with fewer of these columns has changed layout: the lane fails

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def file_url(html: str) -> str:
    """The monthly file's address, from the Commodity Markets page."""
    m = re.search(r'https://thedocs\.worldbank\.org/[^"\'\s<>]*?CMO-Historical-Data-Monthly\.xlsx', html)
    if not m:
        raise ValueError("the Commodity Markets page links no CMO-Historical-Data-Monthly.xlsx")
    return m.group(0)


def _key(header: str) -> str:
    """'Potassium chloride **' -> 'Potassium chloride'; 'Urea ' -> 'Urea'."""
    return re.sub(r"\s*\*+\s*$", "", header or "").strip()


def _rows(zf: zipfile.ZipFile, sheet: str) -> list[dict[str, str]]:
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall(f"{_NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
    book = ET.fromstring(zf.read("xl/workbook.xml"))
    rid = next((s.get(_REL) for s in book.iter(f"{_NS}sheet") if s.get("name") == sheet), None)
    if rid is None:
        raise ValueError(f"no sheet named {sheet!r}")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    path = target.lstrip("/") if target.startswith("/") else "xl/" + target
    out = []
    for row in ET.fromstring(zf.read(path)).iter(f"{_NS}row"):
        cells = {}
        for c in row.findall(f"{_NS}c"):
            col = re.match(r"[A-Z]+", c.get("r") or "")
            if not col:
                continue
            t, v = c.get("t"), c.find(f"{_NS}v")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{_NS}t"))
            elif v is None:
                continue
            elif t == "s":
                val = shared[int(v.text)]
            else:
                val = v.text or ""
            cells[col.group(0)] = val
        out.append(cells)
    return out


rows = _rows         # one sheet of an xlsx as {column letter: text} per row; also read by sanctions.parse_au_xlsx


def parse(body: bytes) -> dict:
    """{'updated': 'YYYY-MM-DD' or None, 'units': {id: unit}, 'series': {id: [(YYYY-MM, value), ...]}}."""
    zf = zipfile.ZipFile(io.BytesIO(body))
    rows = _rows(zf, "Monthly Prices")
    updated = None
    for r in rows[:6]:
        m = re.search(r"Updated on (\w+ \d{1,2}, \d{4})", " ".join(r.values()))
        if m:
            updated = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    hi = next((i for i, r in enumerate(rows) if _key(r.get("B", "")) == "Crude oil, average"), None)
    if hi is None:
        raise ValueError("Monthly Prices has no header row")
    cols = {col: SERIES[_key(h)] for col, h in rows[hi].items() if _key(h) in SERIES}
    if len(cols) < MIN_SERIES:
        raise ValueError(f"Monthly Prices names only {len(cols)} of the {len(SERIES)} series read")
    units = {cols[c][0]: rows[hi + 1].get(c, "").strip("() ") for c in cols}
    series: dict[str, list[tuple[str, float]]] = {v[0]: [] for v in cols.values()}
    for r in rows[hi + 2:]:
        m = re.fullmatch(r"(\d{4})M(\d{2})", (r.get("A") or "").strip())
        if not m:
            continue
        period = f"{m.group(1)}-{m.group(2)}"
        for c, (sid, *_rest) in cols.items():
            try:
                series[sid].append((period, float(r[c])))
            except (KeyError, ValueError):
                pass           # '…' and '...' mark months with no price
    return {"updated": updated, "units": units, "series": series}


def measure(parsed: dict) -> list[dict]:
    out = []
    by_id = {v[0]: v for v in SERIES.values()}
    for sid, pts in parsed["series"].items():
        floor = FLOORS.get(sid, FLOOR)
        m = stats.measure(pts, HORIZON, WINDOW, floor)
        if not m:
            continue
        _, name, group, critical = by_id[sid]
        out.append({
            "id": sid, "name": name, "group": group, "critical_list_name": critical,
            "unit": parsed["units"].get(sid) or "", "floor_pct": floor, "period": m["date"], "value": m["value"],
            "prior_period": m["prior_date"], "prior_value": m["prior_value"],
            **{k: m[k] for k in ("change_pct", "z", "baseline_n", "flag_rate", "expected", "exceedance", "anomaly")},
            "as_issued": [{"period": d, "value": v} for d, v in pts[-12:]],
        })
    order = list(by_id)
    return sorted(out, key=lambda x: order.index(x["id"]))
