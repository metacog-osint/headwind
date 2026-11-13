"""Daily lane: exchange rates (ECB reference rates) and energy spot prices (EIA's own API).

Exchange rates are restated as units of local currency per 1 US dollar, so a rise is a weaker
currency. The ECB publishes about 30 currencies on TARGET business days; currencies it does not
quote (the rouble since March 2022, for one) are simply absent, and Headwind says so on the page.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.parse
import zipfile

from . import stats

ECB_HIST_ZIP = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
EIA_API = "https://api.eia.gov/v2/{route}/data/"
EIA_MAX_ROWS = 5000                                    # EIA returns at most 5,000 rows of JSON per request

# Currency -> ISO 3166-1 alpha-2 country. EUR is the euro area and gets no single country.
CURRENCY_COUNTRY = {
    "JPY": "JP", "CZK": "CZ", "DKK": "DK", "GBP": "GB", "HUF": "HU", "PLN": "PL", "RON": "RO", "SEK": "SE",
    "CHF": "CH", "ISK": "IS", "NOK": "NO", "TRY": "TR", "AUD": "AU", "BRL": "BR", "CAD": "CA", "CNY": "CN",
    "HKD": "HK", "IDR": "ID", "ILS": "IL", "INR": "IN", "KRW": "KR", "MXN": "MX", "MYR": "MY", "NZD": "NZ",
    "PHP": "PH", "SGD": "SG", "THB": "TH", "ZAR": "ZA", "BGN": "BG", "RUB": "RU", "HRK": "HR",
}

# EIA series id -> what Headwind calls it. The route is the EIA API v2 dataset the series sits in.
ENERGY_SERIES = {
    "RBRTE": {"id": "brent", "name": "Brent crude oil spot price", "unit": "US dollars per barrel",
              "route": "petroleum/pri/spt"},
    "RWTC": {"id": "wti", "name": "WTI crude oil spot price", "unit": "US dollars per barrel",
             "route": "petroleum/pri/spt"},
    "RNGWHHD": {"id": "henry-hub", "name": "Henry Hub natural gas spot price", "unit": "US dollars per million Btu",
                "route": "natural-gas/pri/fut"},
}

FX_HORIZON, FX_WINDOW, FX_FLOOR = 5, 250, 1.0          # 5 business days against a year; at least 1%
EN_HORIZON, EN_WINDOW, EN_FLOOR = 5, 250, 5.0          # 5 trading days against a year; at least 5%
KEEP_ROWS = 400


def parse_ecb_zip(body: bytes) -> dict[str, list[tuple[str, float]]]:
    """{currency: [(date, units per USD), ...]} in time order, for currencies quoted on the latest day."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = zf.read(name).decode("utf-8-sig")
    return parse_ecb_csv(text)


def parse_ecb_csv(text: str) -> dict[str, list[tuple[str, float]]]:
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rows[0]]
    data = [r for r in rows[1:] if r and r[0].strip()]
    data.sort(key=lambda r: r[0])
    data = data[-KEEP_ROWS:]
    usd_i = header.index("USD")

    def num(s: str) -> float | None:
        try:
            v = float(s)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    out: dict[str, list[tuple[str, float]]] = {}
    last = data[-1]
    for i, cur in enumerate(header):
        if i == 0 or not cur or cur == "USD" or i >= len(last) or num(last[i]) is None:
            continue
        pts = []
        for r in data:
            usd, loc = num(r[usd_i]) if usd_i < len(r) else None, num(r[i]) if i < len(r) else None
            if usd and loc:
                pts.append((r[0].strip(), loc / usd))
        out[cur] = pts
    # The euro itself: euros per US dollar.
    out["EUR"] = [(r[0].strip(), 1.0 / num(r[usd_i])) for r in data if num(r[usd_i])]
    return out


def measure_fx(series: dict[str, list[tuple[str, float]]]) -> list[dict]:
    out = []
    for cur, pts in sorted(series.items()):
        m = stats.measure(pts, FX_HORIZON, FX_WINDOW, FX_FLOOR)
        if not m:
            continue
        out.append({
            "currency": cur,
            "country": CURRENCY_COUNTRY.get(cur),
            "per_usd": round(m["value"], 6),
            "prior_per_usd": round(m["prior_value"], 6),
            **{k: m[k] for k in ("date", "prior_date", "change_pct", "z", "baseline_n", "flag_rate", "anomaly")},
            "direction": "weaker" if m["change_pct"] > 0 else "stronger" if m["change_pct"] < 0 else "unchanged",
        })
    return out


def eia_routes() -> dict[str, list[str]]:
    """{route: [series id, ...]}: one request per EIA dataset."""
    out: dict[str, list[str]] = {}
    for sid, meta in ENERGY_SERIES.items():
        out.setdefault(meta["route"], []).append(sid)
    return out


def eia_url(route: str, series_ids: list[str], start: str) -> str:
    """The request without the API key. The key is added only when the request is sent, so it
    never reaches the raw-copy index, the snapshot or an error message."""
    q = [("frequency", "daily"), ("data[0]", "value"), ("start", start),
         ("sort[0][column]", "period"), ("sort[0][direction]", "asc"), ("offset", "0"), ("length", str(EIA_MAX_ROWS))]
    q += [("facets[series][]", s) for s in series_ids]
    return EIA_API.format(route=route) + "?" + urllib.parse.urlencode(q, safe="[]")


def parse_eia_json(body: bytes | str, wanted: list[str]) -> dict[str, list[tuple[str, float]]]:
    """{series id: [(date, value), ...]} in time order. EIA gives values as strings and leaves a
    missing day out or blank. A series that comes back empty, or a reply cut off at the row limit,
    is an error, never a quiet gap."""
    doc = json.loads(body)
    resp = doc.get("response")
    if not isinstance(resp, dict) or not isinstance(resp.get("data"), list):
        raise ValueError(f"EIA reply has no data rows: {str(doc.get('error') or list(doc))[:120]}")
    rows = resp["data"]
    try:
        total = int(resp.get("total") or len(rows))
    except (TypeError, ValueError):
        total = len(rows)
    if total > len(rows):
        raise ValueError(f"EIA reply cut short: {len(rows)} of {total} rows")
    out: dict[str, list[tuple[str, float]]] = {s: [] for s in wanted}
    for r in rows:
        sid = r.get("series")
        if sid not in out:
            continue
        try:
            out[sid].append((str(r["period"]), float(r["value"])))
        except (KeyError, TypeError, ValueError):
            pass
    for sid, pts in out.items():
        if not pts:
            raise ValueError(f"EIA reply has no rows for series {sid}")
        pts.sort()
    return out


def measure_energy(series: dict[str, list[tuple[str, float]]]) -> list[dict]:
    out = []
    for sid, meta in ENERGY_SERIES.items():
        m = stats.measure(series.get(sid) or [], EN_HORIZON, EN_WINDOW, EN_FLOOR)
        if not m:
            continue
        out.append({**{k: v for k, v in meta.items() if k != "route"}, "eia_series": sid,
                    "price": m["value"], "prior_price": m["prior_value"],
                    **{k: m[k] for k in ("date", "prior_date", "change_pct", "z", "baseline_n", "flag_rate", "anomaly")}})
    return out
