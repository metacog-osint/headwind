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
# GEM is monthly too; the World Bank updated it on 8 Sep 2026 with August's rates, so it runs further behind.
WINDOWS = {"ecb-eurofxref": (4, 8), "eia-spot": (7, 14), "fao-ffpi": (40, 70), "wfp-food-prices-hdx": (75, 135),
           "worldbank-gem": (100, 160),
           # The Pink Sheet is updated on the second business day of the month with the month before.
           "worldbank-pinksheet": (40, 70),
           # The Census Bureau publishes a month's trade about five weeks after it ends.
           "census-trade": (70, 100),
           # The EU's Financial Sanctions File carries its own generation date and is regenerated as the EU adopts
           # listings. Judged like data since 18 Nov 2026, when it had not moved since 23 Oct while France restated
           # 151 EU entries (windows provisional: the EU's usual rhythm is not measured yet).
           "eu-fsf": (14, 45)}

# A publisher date that has not moved for this many days is noted (not a failure: an unchanged list is still a
# reading). The UN regenerates its file every day, so two quiet days is already unusual.
# France publishes its register as measures are taken (6 Nov 2026 was the latest on 15 Nov).
# Australia's file carries the time DFAT saved it; it changed four times in the first half of Nov 2026.
# Japan's file is named by the list's date; MOF posted files dated 2, 9 and 14 Oct and 20 Nov 2026.
QUIET_DAYS = {"un-sc-consolidated": 3, "eu-fsf": 14, "uk-sanctions-list": 30, "dgtresor-gels": 30,
              "dfat-consolidated": 30, "mof-jp-sanctions": 45}
# OFAC's file carries no date of its own, so its note uses the last change Headwind itself saw.
# Canada's file carries no date either; it changes every few weeks (Last-Modified 10 Nov 2026 on 16 Nov).
QUIET_SEEN_DAYS = {"ofac-sdn": 21, "gac-sema": 45}

LANE_OF = {"ecb-eurofxref": "fx", "worldbank-gem": "gem", "eia-spot": "energy", "fao-ffpi": "fao", "wfp-food-prices-hdx": "wfp",
           "worldbank-pinksheet": "pinksheet",
           "worldbank-wdi": "baseline", "release-calendars": "calendar", "ofac-sdn": "sanctions",
           "un-sc-consolidated": "sanctions", "eu-fsf": "sanctions", "uk-sanctions-list": "sanctions",
           "dgtresor-gels": "sanctions", "gac-sema": "sanctions", "dfat-consolidated": "sanctions",
           "mof-jp-sanctions": "sanctions", "un-press": "unpress",
           "supremecourt-gov": "scotus", "supremecourt-uk": "uksc",
           "trade-gov-csl": "screening", "us-federal-register": "controls", "fr-public-inspection": "inspection",
           "usgs-mcs": "minerals", "census-trade": "trade", "usitc-hts": "tariffs", "whitehouse-actions": "tariffs"}
LIST_KEY = {"ofac-sdn": "ofac-sdn", "un-consolidated": "un-sc-consolidated", "eu-fsf": "eu-fsf",
            "uk-sanctions": "uk-sanctions-list", "france-gels": "dgtresor-gels", "canada-sema": "gac-sema",
            "australia-dfat": "dfat-consolidated", "japan-mof": "mof-jp-sanctions"}


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
    "gem": ("worldbank-gem", "watched countries with an official monthly rate", False),
    "energy": ("eia-spot", "series", True),
    "fao": ("fao-ffpi", "indices", True),
    "fao_release_dates": ("fao-ffpi", "release dates on FAO's page", False),
    "pinksheet": ("worldbank-pinksheet", "series", True),
    "wfp": ("wfp-food-prices-hdx", "countries", False),
    "baseline": ("worldbank-wdi", "countries", True),
    "fomc": ("release-calendars", "FOMC dates", True),
    "ecb": ("release-calendars", "ECB dates", True),
    "controls": ("us-federal-register", "rules in the window", False),
    "minerals": ("usgs-mcs", "commodities", True),
    "trade": ("census-trade", "HS codes with imports", True),
    # Warn only: the release list only grows; a short list already fails in tariffs.parse_releases.
    "tariffs": ("usitc-hts", "HTS revisions listed", False),
    # Warn only: the lane has written its index by the time this runs, and it has its own guard against a short file.
    "screening": ("trade-gov-csl", "entries", False),
    # Warn only: the feed always holds about ten items; fewer than three already fails in unpress.parse.
    "unpress": ("un-press", "items in the UN press feed", False),
    # Warn only: a new term's feed starts empty in October.
    "scotus": ("supremecourt-gov", "opinions in the two terms' feeds", False),
    # Strict: the sitemap's judgment pages only grow (159 on 18 Nov 2026); a short list means the sitemap changed.
    "uksc": ("supremecourt-uk", "judgment pages in the sitemap", True),
}


def sizes(lane: str, result: dict) -> dict[str, int]:
    """The sizes the drift check keeps for a lane's fresh result."""
    if lane == "fx":
        return {"fx": len(result.get("fx") or [])}
    if lane == "gem":
        return {"gem": len(result.get("fx_official") or [])}
    if lane == "energy":
        return {"energy": len(result.get("energy") or [])}
    if lane == "fao":
        return {"fao": len(result.get("fao") or []), "fao_release_dates": len(result.get("fao_release_dates") or [])}
    if lane == "pinksheet":
        return {"pinksheet": len(result.get("pinksheet") or [])}
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
    if lane == "trade":
        return {"trade": sum(1 for c in (result.get("mineral_trade") or {}).get("codes") or [] if c.get("newest_month"))}
    if lane == "tariffs":
        return {"tariffs": (result.get("hts_releases") or {}).get("total") or 0}
    if lane == "scotus":
        return {"scotus": len(result.get("scotus_opinions") or [])}
    if lane == "uksc":
        return {"uksc": (result.get("uksc_sitemap") or {}).get("judgment_pages") or 0}
    if lane == "unpress":
        return {"unpress": (result.get("un_press") or {}).get("items") or 0}
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
    off = snap.get("fx_official") or []
    op = [o["period"] for o in off if o.get("period")]
    add("worldbank-gem", "gem", min(_month_end(max(op)), today) if op else None,
        f"{len(off)} watched countries with an official monthly rate ({sum(1 for o in off if o.get('stale'))} with "
        f"old data), {len(snap.get('fx_official_missing') or [])} without; the World Bank updated it "
        f"{snap.get('fx_official_updated') or 'on a date not given'}")
    en = snap.get("energy") or []
    add("eia-spot", "energy", _newest(e.get("date") for e in en), f"{len(en)} series")
    fao = snap.get("fao") or []
    periods = [m["period"] for m in fao if m.get("period")]
    add("fao-ffpi", "fao", min(_month_end(max(periods)), today) if periods else None,
        f"{len(fao)} indices, newest {max(periods) if periods else 'none'}")
    ps = snap.get("pinksheet") or []
    pp = [m["period"] for m in ps if m.get("period")]
    add("worldbank-pinksheet", "pinksheet", min(_month_end(max(pp)), today) if pp else None,
        f"{len(ps)} series, newest {max(pp) if pp else 'none'}; the World Bank updated the file "
        f"{snap.get('pinksheet_updated') or 'on a date it does not give'}")
    lf = snap.get("local_food") or []
    wp = [w["period"] for w in lf if w.get("period")]
    stale = sum(1 for w in lf if w.get("stale"))
    # A month still under way (WFP publishes part-month prices) is dated today, never in the future.
    add("wfp-food-prices-hdx", "wfp", min(_month_end(max(wp)), today) if wp else None,
        f"{len(lf)} countries ({stale} with old data), {len(snap.get('local_food_missing') or [])} without data; "
        f"{len(snap.get('market_fx') or [])} with market exchange rates")
    add("worldbank-wdi", "baseline", None, f"{len(snap.get('baseline') or {})} countries")
    add("release-calendars", "calendar", None,
        f"{len(snap.get('fomc_dates') or [])} FOMC and {len(snap.get('ecb_dates') or [])} ECB dates")
    sl = snap.get("screening_lists") or []
    add("trade-gov-csl", "screening", None, f"{len(sl)} lists, {sum(l.get('total') or 0 for l in sl)} entries")
    add("us-federal-register", "controls", None,
        f"{len(snap.get('controls') or [])} BIS, OFAC and USTR rules, USTR notices, Section 232 notices and "
        f"presidential tariff actions in the last 60 days, "
        f"{len(snap.get('scheduled_dates') or [])} scheduled dates from the last 800 days")
    pi = snap.get("inspection") or []
    days = snap.get("inspection_issues") or []
    unread = sum(1 for r in pi if r.get("text_error"))
    add("fr-public-inspection", "inspection", _newest(r.get("issue") for r in pi) if pi else None,
        f"{len(pi)} BIS, OFAC and USTR filings in the last 30 days"
        + (f" ({sum(1 for r in pi if r.get('counted_only'))} kept from before titles were published, counted only)"
           if any(r.get("counted_only") for r in pi) else "")
        + f", {sum(1 for d in days if d.get('total'))} of {len(days)} days with an issue"
        + (f"; {unread} filing texts could not be read" if unread else ""))
    add("usgs-mcs", "minerals", None,
        f"{len((snap.get('minerals') or {}).get('reliance') or [])} commodities with net import reliance")
    tr = snap.get("mineral_trade") or {}
    codes = tr.get("codes") or []
    add("census-trade", "trade", min(_month_end(tr["newest_month"]), today) if tr.get("newest_month") else None,
        f"{sum(1 for c in codes if c.get('newest_month'))} of {len(codes)} HS codes with imports, newest month "
        f"{tr.get('newest_month') or 'none'}")
    notes_tr = ([f"HS {c} no longer carries the expected word in the Census description" for c in
                 tr.get("description_mismatch") or []] + [f"not read: {e}" for e in tr.get("errors") or []])
    if notes_tr:
        out["census-trade"]["warnings"] = list(out["census-trade"].get("warnings") or []) + notes_tr
    hts = snap.get("hts_releases") or {}
    revs = hts.get("revisions") or []
    add("usitc-hts", "tariffs", None,
        f"{hts.get('total') or 0} HTS revisions listed, newest {revs[0]['title'] + ' posted ' + revs[0]['posted'] if revs else 'none'}")
    signed = snap.get("signed_actions") or []
    wh_ok = lane_ok("tariffs") and not snap.get("signed_error")
    out["whitehouse-actions"] = _entry(
        "whitehouse-actions", ok=wh_ok, now=now, prev=prev, newest=None, today=today,
        detail=f"{len(signed)} tariff actions in the last 30 days, {sum(1 for s in signed if not s.get('fr_document'))} "
               f"not yet in the Federal Register",
        error=snap.get("signed_error") or err("tariffs"), warnings=notes.get("whitehouse-actions"))
    up = snap.get("un_press") or {}
    rel = snap.get("un_committee_releases") or []
    if up or lanes.get("unpress"):
        gap = ([f"the feed's {up.get('items')} items reached back only to {up.get('oldest')}, after the reading of "
                f"{up.get('previous_read')}: a committee release in between may be missed"] if up.get("may_have_missed") else [])
        out["un-press"] = _entry("un-press", ok=lane_ok("unpress"), now=now, prev=prev,
                                 newest=_day(up.get("newest")), today=today,
                                 detail=f"{up.get('items') or 0} items in the feed, {len(rel)} sanctions committee "
                                        f"releases kept from the last 60 days",
                                 error=err("unpress"), warnings=(notes.get("un-press") or []) + gap or None)
    ops = snap.get("scotus_opinions") or []
    if ops or lanes.get("scotus"):
        decided = [o.get("decided") for o in ops if o.get("decided")]
        errs = snap.get("scotus_errors") or []
        out["supremecourt-gov"] = _entry(
            "supremecourt-gov", ok=lane_ok("scotus"), now=now, prev=prev, newest=_newest(decided), today=today,
            detail=f"{len(ops)} opinions in the two terms read, newest decided {max(decided) if decided else 'none'}; "
                   f"{len(snap.get('scotus_tracked') or [])} tariff-authority dockets tracked",
            error=err("scotus"), warnings=(notes.get("supremecourt-gov") or []) + [f"not read: {e}" for e in errs] or None)
    uj = snap.get("uksc_judgments") or []
    if uj or lanes.get("uksc"):
        us = snap.get("uksc_sitemap") or {}
        newest = uj[0] if uj else None
        left = [f"{us['pending']} case pages left to read on the next run"] if us.get("pending") else []
        out["supremecourt-uk"] = _entry(
            "supremecourt-uk", ok=lane_ok("uksc"), now=now, prev=prev,
            newest=_newest([j.get("judgment_date") for j in uj]), today=today,
            detail=f"{len(uj)} judgments this year and last, newest {newest['citation'] + ' on ' + newest['judgment_date'] if newest else 'none'}; "
                   f"{us.get('judgment_pages') or 0} judgment pages in the sitemap",
            error=err("uksc"),
            warnings=(notes.get("supremecourt-uk") or []) + left + [f"not read: {e}" for e in snap.get("uksc_errors") or []] or None)
    watch = minerals.watch_notes(snap.get("minerals") or {})
    if watch:
        out["usgs-mcs"]["warnings"] = list(out["usgs-mcs"].get("warnings") or []) + watch

    # Each sanctions list stands alone: a list that failed shows "failing" while the others are read.
    lane = lanes.get("sanctions") or {}
    for st in snap.get("sanctions_lists") or []:
        key = LIST_KEY.get(st["id"], st["id"])
        ok = lane.get("status") == "ok" and not st.get("error")
        warns = (list(notes.get(key) or []) + quiet_notes(key, st, today)
                 + (eu_behind(st, snap.get("sanctions") or []) if key == "eu-fsf" else []))
        newest = _day(st.get("source_generated")) if key in WINDOWS else None
        out[key] = _entry(key, ok=ok, now=now, prev=prev, newest=newest, today=today,
                          detail=f"{st.get('total')} entries" + (f", publisher dated {st['source_generated'][:10]}"
                                                                  if st.get("source_generated") else ""),
                          error=st.get("error") or lane.get("error"), warnings=warns)
        out[key]["lane"] = "sanctions"
    # A list that has never been read on this snapshot (no status row) is still owed an entry when the lane failed.
    if lane.get("status") == "failed":
        for key in ("ofac-sdn", "un-sc-consolidated", "eu-fsf", "uk-sanctions-list", "dgtresor-gels", "gac-sema",
                    "dfat-consolidated", "mof-jp-sanctions"):
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


def eu_behind(status: dict, changes: list[dict]) -> list[str]:
    """France restates EU listings in its own register. Entries France added under an EU program ("UE ...") on a day
    after the EU file's own date are listings the EU file is older than: a note, counted from the names kept."""
    d = _day(status.get("source_generated"))
    if not d:
        return []
    n, days = 0, set()
    for c in changes:
        seen = _day(c.get("detected_at"))
        if c.get("list") != "france-gels" or not seen or seen <= d:
            continue
        k = sum(1 for e in c.get("named_added") or [] if any(p.startswith("UE ") for p in e.get("programs") or []))
        if k:
            n, days = n + k, days | {seen.isoformat()}
    if not n:
        return []
    return [f"France's register added {n} entries under EU programs on {', '.join(sorted(days))}, after "
            f"{d.isoformat()}, the date of the EU file"]


def summary(health: dict) -> dict[str, int]:
    """Counts by state, for the CLI and the page."""
    c: dict[str, int] = {}
    for v in health.values():
        c[v["state"]] = c.get(v["state"], 0) + 1
    return dict(sorted(c.items()))


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
