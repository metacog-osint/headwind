"""Monthly lane: the FAO Food Price Index, and WFP food prices by market for the watched countries.

FAO revises earlier months, so every collect keeps the latest twelve months as issued in the
snapshot ("as_issued"); a later reader can see what the number was on the day.
WFP prices are nominal, in local currency. Each country's figure is the median three-month change
across its market-and-commodity price series, judged against that country's own past medians, so
a country with chronic inflation is not flagged for being itself.
"""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import defaultdict

from . import stats

FAO_PAGE = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
FAO_CSV_FALLBACK = ("https://www.fao.org/media/docs/worldfoodsituationlibraries/wfs-library/"
                    "food_price_indices_data.csv?download=true")
HDX_SEARCH = "https://data.humdata.org/api/3/action/package_search?fq=name:wfp-food-prices-for-*&rows=300"

FAO_COLUMNS = {
    "Food Price Index": ("ffpi", "FAO Food Price Index"),
    "Cereals": ("cereals", "FAO Cereal Price Index"),
    "Oils": ("oils", "FAO Vegetable Oil Price Index"),
    "Dairy": ("dairy", "FAO Dairy Price Index"),
    "Meat": ("meat", "FAO Meat Price Index"),
    "Sugar": ("sugar", "FAO Sugar Price Index"),
}
FAO_HORIZON, FAO_WINDOW, FAO_FLOOR = 1, 120, 2.0       # one month against ten years; at least 2%
WFP_HORIZON, WFP_WINDOW, WFP_FLOOR = 3, 60, 10.0       # three months against five years; at least 10%
WFP_MIN_SERIES = 5
WFP_STALE_MONTHS = 4

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"])}


def fao_csv_url(page_html: str) -> str:
    m = re.search(r'href="([^"]*food_price_indices_data\.csv[^"]*)"', page_html)
    return m.group(1).replace("&amp;", "&") if m else FAO_CSV_FALLBACK


def fao_release_dates(page_html: str) -> list[str]:
    """ISO dates from "Monthly release dates for 2026: 9 January, 6 February, ..."."""
    text = re.sub(r"<[^>]+>", " ", page_html)
    out = []
    for m in re.finditer(r"release dates for (\d{4})\s*:\s*([^.]+)\.", text, flags=re.I):
        year = int(m.group(1))
        for d, mon in re.findall(r"(\d{1,2})\s+([A-Za-z]+)", m.group(2)):
            if mon.lower() in MONTHS:
                out.append(f"{year:04d}-{MONTHS[mon.lower()]:02d}-{int(d):02d}")
    return sorted(set(out))


def parse_fao_csv(text: str) -> dict[str, list[tuple[str, float]]]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    hi = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Date")
    header = [h.strip() for h in rows[hi]]
    out: dict[str, list[tuple[str, float]]] = {c: [] for c in FAO_COLUMNS if c in header}
    for r in rows[hi + 1:]:
        if not r or not re.fullmatch(r"\d{4}-\d{2}", r[0].strip()):
            continue
        for col in out:
            try:
                out[col].append((r[0].strip(), float(r[header.index(col)])))
            except (ValueError, IndexError):
                pass
    return out


def measure_fao(series: dict[str, list[tuple[str, float]]]) -> list[dict]:
    out = []
    for col, (sid, name) in FAO_COLUMNS.items():
        pts = series.get(col) or []
        m = stats.measure(pts, FAO_HORIZON, FAO_WINDOW, FAO_FLOOR)
        if not m:
            continue
        ups = [1 for a, b in zip(pts[-121:-1], pts[-120:]) if b[1] > a[1]]
        out.append({
            "id": sid, "name": name, "period": m["date"], "value": m["value"], "prior_period": m["prior_date"],
            "prior_value": m["prior_value"],
            **{k: m[k] for k in ("change_pct", "z", "baseline_n", "flag_rate", "anomaly")},
            "rose_share_120m": round(len(ups) / max(1, min(120, len(pts) - 1)), 3),
            "as_issued": [{"period": d, "value": v} for d, v in pts[-12:]],
        })
    return out


def next_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y + (m == 12):04d}-{(m % 12) + 1:02d}"


# ---- WFP food prices by market (HDX) ----

def hdx_resources(search_json: dict) -> dict[str, dict]:
    """{ISO3: {url, last_modified, dataset}} for every per-country WFP price file HDX lists."""
    out = {}
    for pkg in (search_json.get("result") or {}).get("results") or []:
        for res in pkg.get("resources") or []:
            m = re.fullmatch(r"wfp_food_prices_([a-z]{3})\.csv", (res.get("url") or "").rsplit("/", 1)[-1])
            if m:
                out[m.group(1).upper()] = {
                    "url": res["url"],
                    "last_modified": res.get("last_modified") or pkg.get("last_modified"),
                    "dataset": f"https://data.humdata.org/dataset/{pkg.get('name')}",
                }
    return out


def measure_wfp(csv_text: str, today_period: str) -> dict | None:
    """One country's reading from its WFP price file, or None when it holds too few series."""
    by_series: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    markets = set()
    for r in csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))):
        date = (r.get("date") or "")[:7]
        if not re.fullmatch(r"\d{4}-\d{2}", date) or "forecast" in (r.get("priceflag") or "").lower():
            continue
        try:
            price = float(r.get("price") or "")
        except ValueError:
            continue
        if price <= 0:
            continue
        key = (r.get("market_id") or r.get("market"), r.get("commodity_id") or r.get("commodity"),
               r.get("unit"), r.get("pricetype"), r.get("currency"))
        by_series[key][date].append(price)
        markets.add(key[0])
    if not by_series:
        return None
    monthly = {k: {d: statistics.fmean(v) for d, v in months.items()} for k, months in by_series.items()}
    periods = sorted({d for m in monthly.values() for d in m})

    def shift(period: str, n: int) -> str:
        y, m = int(period[:4]), int(period[5:7]) - n
        while m < 1:
            y, m = y - 1, m + 12
        return f"{y:04d}-{m:02d}"

    medians: list[tuple[str, float, int, float]] = []
    for p in periods:
        prev = shift(p, WFP_HORIZON)
        ch = [m[p] / m[prev] - 1.0 for m in monthly.values() if p in m and prev in m and m[prev] > 0]
        if len(ch) >= WFP_MIN_SERIES:
            medians.append((p, statistics.median(ch), len(ch), sum(1 for c in ch if c > 0) / len(ch)))
    if not medians:
        return None
    period, med, n, up_share = medians[-1]
    # Baseline: the country's own medians, ending WFP_HORIZON months before the latest, so none overlaps it.
    cutoff = shift(period, WFP_HORIZON)
    base = [m for p, m, _, _ in medians if p <= cutoff][-WFP_WINDOW:]
    sc = stats.score(med, base, WFP_FLOOR / 100.0)
    pct = med * 100.0
    months_old = (int(today_period[:4]) - int(period[:4])) * 12 + int(today_period[5:7]) - int(period[5:7])
    stale = months_old > WFP_STALE_MONTHS
    return {
        "period": period, "median_change_pct": round(pct, 1), "series": n, "markets": len(markets),
        "share_rising": round(up_share, 2), "z": sc["z"], "baseline_n": sc["baseline_n"],
        "flag_rate": sc["flag_rate"], "months_old": months_old, "stale": stale,
        "anomaly": bool(sc["anomaly"] and not stale),
    }
