"""Slow lane: one economic baseline per country from the World Bank's World Development Indicators.

Annual figures, usually a year or more old. They are context for the PMESII economic cell, written
to site/data/baseline.json. They are not feed items: nothing here changes day to day.
"""
from __future__ import annotations

import json
from datetime import date

WB_URL = "https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&mrnev=1&per_page=400"

INDICATORS = {
    "FP.CPI.TOTL.ZG": ("inflation_pct", "Consumer price inflation, annual %"),
    "NY.GDP.MKTP.KD.ZG": ("gdp_growth_pct", "Real GDP growth, annual %"),
    "SL.UEM.TOTL.ZS": ("unemployment_pct", "Unemployment, % of labour force (modelled ILO estimate)"),
    "GC.DOD.TOTL.GD.ZS": ("central_gov_debt_pct_gdp", "Central government debt, % of GDP"),
    "FI.RES.TOTL.MO": ("reserves_months_imports", "Total reserves in months of imports"),
    "BN.CAB.XOKA.GD.ZS": ("current_account_pct_gdp", "Current account balance, % of GDP"),
}


MAX_AGE_YEARS = 10


def parse_wb(body: bytes | str, known_countries: set[str], this_year: int | None = None) -> dict[str, dict]:
    """{ISO2: {"value": float, "year": "2024"}} from one World Bank API response.

    Regional aggregates are dropped, and so is any figure more than MAX_AGE_YEARS old: a 1999 debt
    ratio is not a baseline for today.
    """
    this_year = this_year or date.today().year
    doc = json.loads(body)
    rows = doc[1] if isinstance(doc, list) and len(doc) > 1 and doc[1] else []
    out = {}
    for r in rows:
        cc = ((r.get("country") or {}).get("id") or "").upper()
        year = str(r.get("date") or "")
        if year[:4].isdigit() and this_year - int(year[:4]) > MAX_AGE_YEARS:
            continue
        if cc in known_countries and r.get("value") is not None:
            out[cc] = {"value": round(float(r["value"]), 2), "year": str(r.get("date"))}
    return out


def merge(per_indicator: dict[str, dict[str, dict]]) -> dict[str, dict]:
    """{ISO2: {field: {value, year}}} across indicators."""
    out: dict[str, dict] = {}
    for ind, rows in per_indicator.items():
        field = INDICATORS[ind][0]
        for cc, v in rows.items():
            out.setdefault(cc, {})[field] = v
    return dict(sorted(out.items()))
