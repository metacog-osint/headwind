"""Source health: was each source read on this run, how old is its newest data, and does it look right?

One entry per source, keyed by the source id the feed's items carry (the key the doctrine kit's history log
reads), in the shape Cordon and Elements use: state, last_ok, last_error, failures, checked_at, detail. Headwind
adds data_as_of (the newest date in the data), lane, and warnings (drift and quiet-publisher notes).

States are the kit's: "fresh" or "late" or "stale" when the source was read and its data carry a date that can
be judged against the source's own rhythm; "up" when it was read and its data have no such date; "failing" when
this run could not read it (the page shows the last good copy). A source whose data are stale was still read.

Drift: each run keeps the size of what a source gave (rows, dates, entries) for the last ten good readings. A
reading under half the usual size fails the lane for the sources that are parsed from pages or files Headwind
does not control (the last good copy is kept); under four fifths, or for sources whose size moves on its own, it
is a warning. "Usual" is the median of the kept readings, once there are three.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timezone

from headwind import minerals

HISTORY_N = 10          # readings kept per source for the drift check
MIN_HISTORY = 3         # readings needed before the drift check applies
FAIL_SHARE = 0.5        # under this share of the usual size, a strict source fails its lane
WARN_SHARE = 0.8        # under this share, a warning

# Days after its newest data date that a source is fresh, then late; past both it is stale. The ECB publishes on
# business days (a long weekend is four days), EIA's daily spot prices arrive a few days behind, FAO and WFP are
# monthly and dated by month (counted from the month's end).
WINDOWS = {"ecb-eurofxref": (4, 8), "eia-spot": (7, 14), "fao-ffpi": (40, 70), "wfp-food-prices-hdx": (75, 135)}

# A publisher date that has not moved for this many days is noted (not a failure: an unchanged list is still a
# reading). The UN regenerates its file every day, so two quiet days is already unusual.
QUIET_DAYS = {"un-sc-consolidated": 3, "eu-fsf": 30, "uk-sanctions-list": 30}
# OFAC's file carries no date of its own, so its note uses the last change Headwind itself saw.
QUIET_SEEN_DAYS = {"ofac-sdn": 21}

LANE_OF = {"ecb-eurofxref": "fx", "eia-spot": "energy", "fao-ffpi": "fao", "wfp-food-prices-hdx": "wfp",
           "worldbank-wdi": "baseline", "release-calendars": "calendar", "ofac-sdn": "sanctions",
           "un-sc-consolidated": "sanctions", "eu-fsf": "sanctions", "uk-sanctions-list": "sanctions",
           "trade-gov-csl": "screening", "us-federal-register": "controls", "fr-public-inspection": "inspection",
           "usgs-mcs": "minerals"}
LIST_KEY = {"ofac-sdn": "ofac-sdn", "un-consolidated": "un-sc-consolidated", "eu-fsf": "eu-fsf",
            "uk-sanctions": "uk-sanctions-list"}


def _day(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except ValueError:
        return None


def _month_end(period: str) -> date:
    y, m = int(period[:4]), int(period[5:7])
    first_of_next = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(first_of_next.toordinal() - 1)


# --- drift -----------------------------------------------------------------------------------------------

# What is measured for each source, and whether a short reading fails the lane ("strict") or only warns.
# Strict: parsed from pages or files whose layout Headwind does not control. Warn only: sizes that move on
# their own (a 60-day window of rules, countries WFP has published for).
DRIFT = {
    "fx": ("ecb-eurofxref", "currencies", True),
    "energy": ("eia-spot", "series", True),
    "fao": ("fao-ffpi", "indices", True),
    "fao_release_dates": ("fao-ffpi", "release dates on FAO's page", False),
    "wfp": ("wfp-food-prices-hdx", "countries", False),
    "baseline": ("worldbank-wdi", "countries", True),
    "fomc": ("release-calendars", "FOMC dates", True),
    "ecb": ("release-calendars", "ECB dates", True),
    "controls": ("us-federal-register", "rules in the window", False),
    "minerals": ("usgs-mcs", "commodities", True),
    # Warn only: the lane has written its index by the time this runs, and it has its own guard against a short file.
    "screening": ("trade-gov-csl", "entries", False),
}


def sizes(lane: str, result: dict) -> dict[str, int]:
    """The sizes the drift check keeps for a lane's fresh result."""
    if lane == "fx":
        return {"fx": len(result.get("fx") or [])}
    if lane == "energy":
        return {"energy": len(result.get("energy") or [])}
    if lane == "fao":
        return {"fao": len(result.get("fao") or []), "fao_release_dates": len(result.get("fao_release_dates") or [])}
    if lane == "wfp":
        return {"wfp": len(result.get("local_food") or [])}
    if lane == "baseline":
        return {"baseline": len(result.get("baseline") or {})}
    if lane == "calendar":
        return {"fomc": len(result.get("fomc_dates") or []), "ecb": len(result.get("ecb_dates") or [])}
    if lane == "controls":
        return {"controls": len(result.get("controls") or [])}
    if lane == "minerals":
        return {"minerals": len((result.get("minerals") or {}).get("reliance") or [])}
    if lane == "screening":
        return {"screening": sum(l.get("total") or 0 for l in result.get("screening_lists") or [])}
    return {}


def drift(lane: str, now_sizes: dict[str, int], history: dict[str, list[int]]) -> tuple[list[str], list[tuple]]:
    """(failures, warnings) for a lane's fresh sizes against the kept history. A failure is text for the lane's
    error; a warning is (health key, text)."""
    fails, warns = [], []
    for key, n in now_sizes.items():
        past = (history or {}).get(key) or []
        if len(past) < MIN_HISTORY:
            continue
        usual = statistics.median(past)
        if usual <= 0:
            continue
        source_key, what, strict = DRIFT[key]
        text = f"{n} {what} against a usual {usual:g} (median of the last {len(past)} readings)"
        if n < usual * FAIL_SHARE and strict:
            fails.append(text + "; the source's layout may have changed, so the last good copy is kept")
        elif n < usual * WARN_SHARE:
            warns.append((source_key, text))
    return fails, warns


def remember(history: dict, now_sizes: dict[str, int]) -> dict:
    out = {k: list(v) for k, v in (history or {}).items()}
    for key, n in now_sizes.items():
        out[key] = (out.get(key) or [])[-(HISTORY_N - 1):] + [n]
    return out


# --- health ----------------------------------------------------------------------------------------------

def _judge(key: str, newest: date | None, today: date) -> str:
    win = WINDOWS.get(key)
    if not win or newest is None:
        return "up"
    age = (today - newest).days
    return "fresh" if age <= win[0] else "late" if age <= win[1] else "stale"


def _entry(key: str, *, ok: bool, now: str, prev: dict, newest: date | None, today: date, detail: str,
           error: str | None = None, warnings: list[str] | None = None) -> dict:
    p = prev.get(key) or {}
    e = {
        "state": _judge(key, newest, today) if ok else "failing",
        "last_ok": now if ok else p.get("last_ok"),
        "last_error": p.get("last_error") if ok else now,
        "failures": 0 if ok else int(p.get("failures") or 0) + 1,
        "checked_at": now,
        "detail": detail,
        "lane": LANE_OF[key],
        "data_as_of": newest.isoformat() if newest else None,
    }
    if not ok and error:
        e["error"] = error[:300]
    if warnings:
        e["warnings"] = warnings
    return e


def _newest(dates) -> date | None:
    ds = [d for d in (_day(x) for x in dates) if d]
    return max(ds) if ds else None


def build(snap: dict, prev_health: dict | None, today: date) -> dict:
    """The health record for this run, from the finished snapshot (lanes, data, drift notes)."""
    now = snap["generated_at"]
    lanes = snap.get("lanes") or {}
    prev = prev_health or {}
    notes = snap.get("drift_warnings") or {}
    out: dict[str, dict] = {}

    def lane_ok(lane):
        return (lanes.get(lane) or {}).get("status") == "ok"

    def err(lane):
        return (lanes.get(lane) or {}).get("error")

    def add(key, lane, newest, detail):
        ok = lane_ok(lane)
        out[key] = _entry(key, ok=ok, now=now, prev=prev, newest=newest, today=today, detail=detail,
                          error=err(lane), warnings=notes.get(key))

    fx = snap.get("fx") or []
    add("ecb-eurofxref", "fx", _newest(f.get("date") for f in fx), f"{len(fx)} currencies")
    en = snap.get("energy") or []
    add("eia-spot", "energy", _newest(e.get("date") for e in en), f"{len(en)} series")
    fao = snap.get("fao") or []
    periods = [m["period"] for m in fao if m.get("period")]
    add("fao-ffpi", "fao", min(_month_end(max(periods)), today) if periods else None,
        f"{len(fao)} indices, newest {max(periods) if periods else 'none'}")
    lf = snap.get("local_food") or []
    wp = [w["period"] for w in lf if w.get("period")]
    stale = sum(1 for w in lf if w.get("stale"))
    # A month still under way (WFP publishes part-month prices) is dated today, never in the future.
    add("wfp-food-prices-hdx", "wfp", min(_month_end(max(wp)), today) if wp else None,
        f"{len(lf)} countries ({stale} with old data), {len(snap.get('local_food_missing') or [])} without data")
    add("worldbank-wdi", "baseline", None, f"{len(snap.get('baseline') or {})} countries")
    add("release-calendars", "calendar", None,
        f"{len(snap.get('fomc_dates') or [])} FOMC and {len(snap.get('ecb_dates') or [])} ECB dates")
    sl = snap.get("screening_lists") or []
    add("trade-gov-csl", "screening", None, f"{len(sl)} lists, {sum(l.get('total') or 0 for l in sl)} entries")
    add("us-federal-register", "controls", None,
        f"{len(snap.get('controls') or [])} BIS, OFAC and USTR rules and USTR notices in the last 60 days, "
        f"{len(snap.get('scheduled_dates') or [])} scheduled dates from the last 800 days")
    pi = snap.get("inspection") or []
    days = snap.get("inspection_issues") or []
    unread = sum(1 for r in pi if r.get("text_error"))
    add("fr-public-inspection", "inspection", _newest(r.get("issue") for r in pi) if pi else None,
        f"{len(pi)} BIS, OFAC and USTR filings in the last 30 days ({sum(1 for r in pi if r.get('counted_only'))} "
        f"counted only), {sum(1 for d in days if d.get('total'))} of {len(days)} days with an issue"
        + (f"; {unread} filing texts could not be read" if unread else ""))
    add("usgs-mcs", "minerals", None,
        f"{len((snap.get('minerals') or {}).get('reliance') or [])} commodities with net import reliance")
    watch = minerals.watch_notes(snap.get("minerals") or {})
    if watch:
        out["usgs-mcs"]["warnings"] = list(out["usgs-mcs"].get("warnings") or []) + watch

    # Each sanctions list stands alone: a list that failed shows "failing" while the others are read.
    lane = lanes.get("sanctions") or {}
    for st in snap.get("sanctions_lists") or []:
        key = LIST_KEY.get(st["id"], st["id"])
        ok = lane.get("status") == "ok" and not st.get("error")
        warns = list(notes.get(key) or []) + quiet_notes(key, st, today)
        out[key] = _entry(key, ok=ok, now=now, prev=prev, newest=None, today=today,
                          detail=f"{st.get('total')} entries" + (f", publisher dated {st['source_generated'][:10]}"
                                                                  if st.get("source_generated") else ""),
                          error=st.get("error") or lane.get("error"), warnings=warns)
        out[key]["lane"] = "sanctions"
    # A list that has never been read on this snapshot (no status row) is still owed an entry when the lane failed.
    if lane.get("status") == "failed":
        for key in ("ofac-sdn", "un-sc-consolidated", "eu-fsf", "uk-sanctions-list"):
            out.setdefault(key, _entry(key, ok=False, now=now, prev=prev, newest=None, today=today,
                                       detail="not read", error=lane.get("error")))
    return dict(sorted(out.items()))


def quiet_notes(key: str, status: dict, today: date) -> list[str]:
    """A note when a list's own date, or the last change Headwind saw on it, has not moved for a long time."""
    out = []
    if key in QUIET_DAYS and status.get("source_generated"):
        d = _day(status["source_generated"])
        if d and (today - d).days > QUIET_DAYS[key]:
            out.append(f"the publisher's file is dated {d.isoformat()}, {(today - d).days} days ago")
    if key in QUIET_SEEN_DAYS:
        seen = _day(status.get("last_change_at") or status.get("baseline_set_at"))
        if seen and (today - seen).days > QUIET_SEEN_DAYS[key]:
            what = "no change seen since" if status.get("last_change_at") else "no change seen since the baseline of"
            out.append(f"{what} {seen.isoformat()}, {(today - seen).days} days ago")
    return out


def summary(health: dict) -> dict[str, int]:
    """Counts by state, for the CLI and the page."""
    c: dict[str, int] = {}
    for v in health.values():
        c[v["state"]] = c.get(v["state"], 0) + 1
    return dict(sorted(c.items()))


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
