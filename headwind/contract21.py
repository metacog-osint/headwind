"""Feed contract revision 2.1 fields (doctrine/kit/docs/feed-contract-v2.md), added to items build_feed has made.

subject_id is the item's id. Series ids carry no date. A list change (`headwind:sanctions:<list>:<run stamp>`) keeps
its stamp on purpose: the stamp names one change, it never moves from run to run, and a list can have several changes
in the feed at once (France had five on 23 Nov 2026). Under one shared subject the kit's history would keep only the
newest under the subject, and a reader without a reading key (COP's ledger) would log no line for a new change.

last_change is stated here only for list changes, which Headwind dates itself. Every other item takes it from the
history log (`tic.py history --fill-last-change`). Nothing here reads or writes stored data.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import food

CONTRACT_REV = "2.1"
_END = "T00:00:00Z"


def _day(value: str) -> str:
    return f"{value[:10]}{_END}"


def _month(period: str) -> str:
    return f"{period[:7]}-01{_END}"


def _shift(period: str, months: int) -> str:
    """The month `months` before a YYYY-MM period."""
    n = int(period[:4]) * 12 + int(period[5:7]) - 1 - months
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def _rows(snapshot: dict) -> dict:
    """Each item's source row, by the family and key in its id."""
    def index(name: str, field: str) -> dict:
        return {r[field]: r for r in snapshot.get(name) or [] if r.get(field) is not None}
    return {
        "fx": index("fx", "currency"), "fxofficial": index("fx_official", "country"),
        "fxmarket": index("market_fx", "country"), "energy": index("energy", "id"), "food": index("fao", "id"),
        "pinksheet": index("pinksheet", "id"), "localfood": index("local_food", "country"),
        "sanctions": index("sanctions", "id"), "screening": index("screening", "id"),
        "control": index("controls", "id"),
        "hts": {r["name"]: r for r in (snapshot.get("hts_releases") or {}).get("revisions") or [] if r.get("name")},
        "tariffpace": {"presidential": snapshot.get("tariff_pace") or {}, "hts": snapshot.get("hts_pace") or {}},
    }


def event_times(family: str, row: dict, data_as_of: str) -> tuple[str, str | None, str | None]:
    """(event_start, event_end, event_time_precision) for one item."""
    if family in ("fx", "energy") and row.get("prior_date"):
        return _day(row["prior_date"]), _day(row["date"]), "day"
    if family in ("fxofficial", "food", "pinksheet") and row.get("prior_period"):
        return _month(row["prior_period"]), _month(row["period"]), "month"
    if family == "fxmarket" and row.get("period"):
        return _month(_shift(row["period"], food.WFPFX_HORIZON)), _month(row["period"]), "month"
    if family == "localfood" and row.get("period"):
        return _month(_shift(row["period"], food.WFP_HORIZON)), _month(row["period"]), "month"
    if family in ("sanctions", "screening") and row.get("detected_at"):
        # The change happened between Headwind's two readings of the list.
        return row.get("prior_checked_at") or row["detected_at"], row["detected_at"], None
    if family == "control":
        when = row.get("effective_on") or row.get("signing_date") or row.get("published_date")
        if when:
            return _day(when), None, "day"
    if family == "hts" and (row.get("in_effect_from") or row.get("posted")):
        end = row.get("in_effect_to")
        return _day(row.get("in_effect_from") or row["posted"]), _day(end) if end else None, "day"
    if family == "tariffpace" and row.get("from") and row.get("to"):
        return _day(row["from"]), _day(row["to"]), "day"
    return data_as_of, None, "day" if data_as_of.endswith(_END) else None


SERIES_SIGNAL = {
    "fx": ("change_pct", "change in currency units per US dollar over 5 business days"),
    "fxofficial": ("change_pct", "monthly change in the official rate per US dollar"),
    "fxmarket": ("median_change_pct", "median one-month change in market rates per US dollar"),
    "energy": ("change_pct", "price change over 5 trading days"),
    "food": ("change_pct", "monthly change in the index"),
    "pinksheet": ("change_pct", "monthly price change"),
    "localfood": ("median_change_pct", "median three-month change in local food prices"),
}


def signal(family: str, row: dict) -> dict | None:
    """The one number an anomaly's tier rests on, or None when the row does not hold it."""
    if family in SERIES_SIGNAL:
        field, name = SERIES_SIGNAL[family]
        if row.get(field) is None:
            return None
        out = {"name": name, "value": row[field], "unit": "percent", "expected": row.get("expected"), "tail": "both",
               "baseline_n": row.get("baseline_n"), "exceedance": row.get("exceedance")}
    elif family in ("sanctions", "screening"):
        hit = [b for b in row.get("batches") or [] if b.get("anomaly") and b.get("z") is not None]
        if not hit:
            return None
        top = max(hit, key=lambda b: b["z"])
        out = {"name": "entries added in one designation batch", "value": top["size"], "unit": "entries",
               "tail": "high", "baseline_n": top.get("baseline_n")}
    elif family == "tariffpace":
        if row.get("count") is None:
            return None
        out = {"name": f"documents in {row.get('window_days')} days", "value": row["count"], "unit": "documents",
               "expected": row.get("median"), "tail": "high", "baseline_n": row.get("baseline_n")}
    else:
        return None
    return {k: v for k, v in out.items() if v is not None}


def published_health(health: dict) -> dict:
    """The health block as the feed publishes it: a date-only data_as_of as midnight UTC, which revision 2.1 requires.
    A copy, so the stored snapshot keeps the date as it was read."""
    out = {}
    for lane, entry in (health or {}).items():
        when = entry.get("data_as_of") if isinstance(entry, dict) else None
        out[lane] = {**entry, "data_as_of": _day(when)} if isinstance(when, str) and len(when) == 10 else entry
    return out


def apply(features: list[dict], snapshot: dict) -> list[dict]:
    """Add the revision 2.1 fields to each item, in place."""
    rows = _rows(snapshot)
    for f in features:
        p = f["properties"]
        parts = p["id"].split(":", 2)
        family, key = parts[1], parts[2] if len(parts) > 2 else ""
        row = rows.get(family, {}).get(key) or {}
        p["subject_id"] = p["id"]
        start, end, precision = event_times(family, row, p["data_as_of"])
        p["event_start"] = start
        if end and end >= start:
            p["event_end"] = end
        if precision:
            p["event_time_precision"] = precision
        if family in ("sanctions", "screening") and row.get("detected_at"):
            p["last_change"], p["last_change_at"] = "new", min(row["detected_at"], p["published_at"])
        if p.get("tier") == "anomaly":
            sig = signal(family, row)
            if sig:
                p["signal"] = sig
    return features
