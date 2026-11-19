"""Headwind CLI: collect, build, and check.

    python tools/headwind.py collect     # fetch every live lane, write data/snapshot.json
    python tools/headwind.py build       # build site/ from data/snapshot.json
    python tools/headwind.py check       # validate the registers and lint the feed

collect never falls back to made-up data. A lane that fails keeps its last good copy (marked
from_previous) or stays empty, and the snapshot's "lanes" block says which.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import (baseline, batches, commodities, controls, feed, fetch, food, health, inspection,  # noqa: E402,F401
                      markets, minerals, names, pinksheet, releases, sanctions, scotus, screening, tariffs, trade,
                      uksc, unpress)
from tic_doctrine import contract, geo, registers  # noqa: E402

LANE_FIELDS = {
    "fx": ["fx"],
    "gem": ["fx_official", "fx_official_missing", "fx_official_updated"],
    "energy": ["energy"],
    "fao": ["fao", "fao_release_dates"],
    "pinksheet": ["pinksheet", "pinksheet_updated"],
    "wfp": ["local_food", "local_food_missing", "market_fx"],
    "baseline": ["baseline"],
    "calendar": ["fomc_dates", "ecb_dates"],
    "sanctions": ["sanctions", "sanctions_lists", "vessel_crosslist", "vessel_table"],
    "screening": ["screening", "screening_lists"],
    "controls": ["controls", "scheduled_dates", "tariff_pace"],
    "inspection": ["inspection", "inspection_issues"],
    "minerals": ["minerals"],
    "trade": ["mineral_trade"],
    "tariffs": ["hts_releases", "hts_pace", "signed_actions", "signed_error"],
    "unpress": ["un_committee_releases", "un_press"],
    "scotus": ["scotus_opinions", "scotus_tracked", "scotus_errors"],
    "uksc": ["uksc_judgments", "uksc_read", "uksc_errors", "uksc_sitemap"],
}
EMPTY = {"fx": [], "fx_official": [], "fx_official_missing": [], "fx_official_updated": None, "market_fx": [],
         "energy": [], "fao": [], "fao_release_dates": [], "pinksheet": [], "pinksheet_updated": None,
         "local_food": [], "local_food_missing": [],
         "baseline": {}, "fomc_dates": [], "ecb_dates": [], "sanctions": [], "sanctions_lists": [], "vessel_crosslist": {}, "vessel_table": [], "screening": [],
         "screening_lists": [], "controls": [], "scheduled_dates": [], "inspection": [], "inspection_issues": [],
         "minerals": {}, "mineral_trade": {}, "tariff_pace": {}, "hts_releases": {}, "hts_pace": {},
         "signed_actions": [], "signed_error": None, "un_committee_releases": [], "un_press": {},
         "scotus_opinions": [], "scotus_tracked": [], "scotus_errors": [],
         "uksc_judgments": [], "uksc_read": {}, "uksc_errors": [], "uksc_sitemap": {}}


def _lane_fx(raw_dir, prev, getter):
    body, rec = fetch.fetch("ecb-eurofxref", markets.ECB_HIST_ZIP, raw_dir, "zip", getter=getter)
    return {"fx": markets.measure_fx(markets.parse_ecb_zip(body))}, [rec]


def _watched() -> dict[str, str]:
    return json.loads((ROOT / "config" / "wfp_countries.json").read_text(encoding="utf-8"))["countries"]


def _lane_gem(raw_dir, prev, getter):
    """Official monthly exchange rates for the watched countries (World Bank Global Economic Monitor)."""
    wanted = _watched()
    body, rec = fetch.fetch("worldbank-gem", markets.gem_url(wanted.values()), raw_dir, "json", timeout=60,
                            getter=getter)
    series, updated = markets.parse_gem(body)
    rows = markets.measure_gem(series, {v: k for k, v in wanted.items()}, date.today().strftime("%Y-%m"))
    have = {r["country"] for r in rows}
    missing = [{"country": cc, "reason": "no official monthly rate in the World Bank's Global Economic Monitor"}
               for cc in sorted(wanted) if cc not in have]
    return {"fx_official": rows, "fx_official_missing": missing, "fx_official_updated": updated}, [rec]


def eia_key_file() -> Path:
    return Path(os.environ.get("HEADWIND_EIA_KEY_FILE") or Path.home() / ".headwind" / "eia_api_key.txt")


def _eia_key() -> str:
    """The EIA API key, from EIA_API_KEY or a one-line file outside the repository. Never logged."""
    key = (os.environ.get("EIA_API_KEY") or "").strip()
    if not key and eia_key_file().is_file():
        key = eia_key_file().read_text(encoding="utf-8-sig").strip()
    if not key:
        raise RuntimeError(f"no EIA API key: set EIA_API_KEY or put the key in {eia_key_file()}")
    return key


def _lane_energy(raw_dir, prev, getter):
    key = _eia_key()
    base = getter or fetch.get

    def keyed(url, timeout=60):
        # EIA accepts the key only in the URL. Add it here so the recorded URL stays keyless,
        # and keep it out of any error text.
        try:
            return base(url + "&api_key=" + key, timeout)
        except Exception as exc:
            raise OSError(f"{type(exc).__name__}: {exc}".replace(key, "[key]")) from None

    start = (date.today() - timedelta(days=800)).isoformat()
    series, recs = {}, []
    for route, ids in markets.eia_routes().items():
        body, rec = fetch.fetch("eia-spot", markets.eia_url(route, ids, start), raw_dir, "json", getter=keyed)
        series.update(markets.parse_eia_json(body, ids))
        recs.append(rec)
    return {"energy": markets.measure_energy(series)}, recs


def census_key_file() -> Path:
    return Path(os.environ.get("HEADWIND_CENSUS_KEY_FILE") or Path.home() / ".headwind" / "census_api_key.txt")


def _census_key() -> str:
    """The Census Bureau API key, from CENSUS_API_KEY or a one-line file outside the repository. Never logged."""
    key = (os.environ.get("CENSUS_API_KEY") or "").strip()
    if not key and census_key_file().is_file():
        key = census_key_file().read_text(encoding="utf-8-sig").strip()
    if not key:
        raise RuntimeError(f"no Census API key: set CENSUS_API_KEY or put the key in {census_key_file()}")
    return key


def _lane_trade(raw_dir, prev, getter):
    """US imports of critical minerals by source country (Census Bureau). Monthly; context, not feed items. One
    request per HS code; a code that fails is named and the others go on."""
    key = _census_key()
    base = getter or fetch.get

    def keyed(url, timeout=60):
        # The key goes only into the request as sent, so the recorded URL stays keyless; it is kept out of errors too.
        try:
            return base(url + "&key=" + urllib.parse.quote(key), timeout)
        except Exception as exc:
            raise OSError(f"{type(exc).__name__}: {exc}".replace(key, "[key]")) from None

    today = date.today()
    y, m = today.year, today.month - trade.MONTHS
    while m < 1:
        y, m = y - 1, m + 12
    start = f"{y:04d}-{m:02d}"
    parsed, errors, recs = {}, [], []
    for code in trade.CODES:
        try:
            body, rec = fetch.fetch("census-trade", trade.url(code, start), raw_dir, "json", getter=keyed)
            parsed[code] = trade.parse(body)
            recs.append(rec)
        except Exception as exc:  # noqa: BLE001 - one code's failure is reported on the lane
            errors.append(f"{code}: {type(exc).__name__}: {exc}"[:200])
    end = max((max(p["months"]) for p in parsed.values() if p["months"]), default=None)
    records = [trade.summarize(code, p, end, start) for code, p in parsed.items()]
    if not records:
        raise RuntimeError("no Census trade code could be read: " + "; ".join(errors[:3]))
    return {"mineral_trade": trade.build(records, errors)}, recs


def _lane_fao(raw_dir, prev, getter):
    page, rec1 = fetch.fetch("fao-ffpi-page", food.FAO_PAGE, raw_dir, "html", getter=getter)
    html = page.decode("utf-8", errors="replace")
    body, rec2 = fetch.fetch("fao-ffpi", food.fao_csv_url(html), raw_dir, "csv", getter=getter)
    series = food.parse_fao_csv(body.decode("utf-8-sig"))
    return {"fao": food.measure_fao(series), "fao_release_dates": food.fao_release_dates(html)}, [rec1, rec2]


def _lane_pinksheet(raw_dir, prev, getter):
    """World Bank Commodity Price Data (the Pink Sheet), monthly: fertilizers and critical-list metals. The file
    moves to a new address each year, so the address is read from the Commodity Markets page first."""
    page, rec1 = fetch.fetch("worldbank-pinksheet-page", pinksheet.PAGE, raw_dir, "html", getter=getter)
    url = pinksheet.file_url(page.decode("utf-8", errors="replace"))
    body, rec2 = fetch.fetch("worldbank-pinksheet", url, raw_dir, "xlsx", timeout=120, getter=getter)
    parsed = pinksheet.parse(body)
    return {"pinksheet": pinksheet.measure(parsed), "pinksheet_updated": parsed["updated"]}, [rec1, rec2]


def _lane_wfp(raw_dir, prev, getter):
    wanted = _watched()
    body, rec = fetch.fetch("hdx-wfp-index", food.HDX_SEARCH, raw_dir, "json", getter=getter)
    resources = food.hdx_resources(json.loads(body))
    old = {w["country"]: w for w in (prev.get("local_food") or [])}
    today_period = date.today().strftime("%Y-%m")
    out, missing, recs = [], [], [rec]
    for cc, iso3 in sorted(wanted.items()):
        res = resources.get(iso3)
        if not res:
            missing.append({"country": cc, "reason": "no WFP price file on HDX"})
            continue
        cached = old.get(cc)
        # A record kept from before headwind-1.6 has no market_fx, one from before the month-by-month split
        # test (15 Nov 2026) has no split_months, and one from before headwind-1.10 has no rank and run rules
        # (Sudan's file, unchanged on HDX since 15 Nov, kept its old reading on the live feed until 18 Nov): read
        # the file again once.
        fresh_fx = "market_fx" in cached and (not cached["market_fx"] or "split_months" in cached["market_fx"]) \
            if cached else False
        fresh_rules = bool(cached) and "rules" in cached
        if cached and cached.get("hdx_last_modified") == res["last_modified"] and fresh_fx and fresh_rules:
            m = {k: cached[k] for k in cached if k not in ("country", "iso3", "dataset", "hdx_last_modified")}
            for part in (m, m.get("market_fx")):
                if not part:
                    continue
                part["months_old"] = ((int(today_period[:4]) - int(part["period"][:4])) * 12
                                      + int(today_period[5:7]) - int(part["period"][5:7]))
                part["stale"] = part["months_old"] > food.WFP_STALE_MONTHS
                part["anomaly"] = bool(part["anomaly"] and not part["stale"])
        else:
            try:
                csv_body, r = fetch.fetch(f"wfp-prices-{iso3.lower()}", res["url"], raw_dir, "csv", timeout=120,
                                          getter=getter)
            except Exception as exc:  # one country failing must not lose the others
                missing.append({"country": cc, "reason": f"fetch failed: {type(exc).__name__}"})
                continue
            recs.append(r)
            csv_text = csv_body.decode("utf-8-sig", errors="replace")
            m = food.measure_wfp(csv_text, today_period)
            if not m:
                missing.append({"country": cc, "reason": "too few price series"})
                continue
            m["market_fx"] = food.measure_wfp_fx(csv_text, today_period)
        out.append({"country": cc, "iso3": iso3, "dataset": res["dataset"],
                    "hdx_last_modified": res["last_modified"], **m})
    market = [{"country": w["country"], "iso3": w["iso3"], "dataset": w["dataset"], **w["market_fx"]}
              for w in out if w.get("market_fx")]
    return {"local_food": out, "local_food_missing": missing, "market_fx": market}, recs


def _lane_baseline(raw_dir, prev, getter):
    known = {c["cc"] for c in json.loads(
        (ROOT / "doctrine" / "kit" / "geo" / "countries.json").read_text(encoding="utf-8"))["countries"]}
    per, recs = {}, []
    for ind in baseline.INDICATORS:
        body, rec = fetch.fetch("worldbank-wdi", baseline.WB_URL.format(ind=ind), raw_dir, "json", timeout=45,
                                getter=getter)
        per[ind] = baseline.parse_wb(body, known)
        recs.append(rec)
    return {"baseline": baseline.merge(per)}, recs


def _lane_calendar(raw_dir, prev, getter):
    f, rec1 = fetch.fetch("fed-fomc-calendar", releases.FOMC_PAGE, raw_dir, "html", getter=getter)
    e, rec2 = fetch.fetch("ecb-calendar", releases.ECB_PAGE, raw_dir, "html", getter=getter)
    fomc = releases.fomc_dates(f.decode("utf-8", errors="replace"))
    ecb = releases.ecb_dates(e.decode("utf-8", errors="replace"))
    if not fomc or not ecb:
        raise ValueError(f"calendar pages parsed to {len(fomc)} FOMC and {len(ecb)} ECB dates")
    return {"fomc_dates": fomc, "ecb_dates": ecb}, [rec1, rec2]


_CA_NAMES: dict = {}       # Canada's name hashes from the last read, for its renumbering guard (private state only)


LIST_CHANGE_KEYS = ("id", "list", "list_name", "publisher", "url", "detected_at", "prior_checked_at", "us_person_data",
                    "added", "removed", "changed", "named_added", "named_changed", "named_removed", "unnamed_removed",
                    "vessels_added", "vessels_removed", "vessels_rekeyed", "vessels_changed")


def list_changes(snap: dict) -> dict:
    """Every named entry of the list changes kept in the snapshot (30 days): data/list-changes.json."""
    def slim(d, kind):
        return {"kind": kind, **{k: d[k] for k in LIST_CHANGE_KEYS if k in d}}
    return {"generated_at": snap["generated_at"], "method_version": snap.get("method_version"),
            "note": ("People, organizations and ships added, changed and removed on official sanctions and US screening "
                     "lists, as the publishers print their names, between two of Headwind's readings; kept 30 days. "
                     "A removed entry is no longer on the list. The UN Security Council's list is counted only (its "
                     "terms bar redistribution). Birth dates, identity documents, street addresses and reasons are "
                     "not carried. Corrections and take-down requests for names no longer listed: "
                     "support@theintelligence.company."),
            "changes": [slim(d, "sanctions") for d in snap.get("sanctions") or []]
            + [slim(d, "screening") for d in snap.get("screening") or []]}


def _read_list(list_id, raw_dir, getter):
    """Fetch and parse one sanctions list: (index, the publisher's generation date, fetch record, designation dates).
    OFAC's file has no designation dates (None)."""
    dates: dict = {}
    if list_id == "ofac-sdn":
        body, rec = fetch.fetch("ofac-sdn", sanctions.OFAC_SDN_CSV, raw_dir, "csv", timeout=180, getter=getter)
        addresses = None
        try:
            # The address file gives each entry's countries, which set us_person_data on a change. Without it the
            # list is still read; its people and organizations then carry no country.
            abody, _ = fetch.fetch("ofac-sdn-add", sanctions.OFAC_ADD_CSV, raw_dir, "csv", timeout=180, getter=getter)
            addresses = sanctions.parse_add_csv(abody.decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 - the list itself was read
            print(f"  sanctions: ofac-sdn: address file not read ({exc}); no countries this run", file=sys.stderr)
        return sanctions.parse_sdn_csv(body.decode("utf-8", errors="replace"), addresses), None, rec, None
    if list_id == "un-consolidated":
        body, rec = fetch.fetch("un-sc-consolidated", sanctions.UN_XML, raw_dir, "xml", timeout=120, getter=getter)
        generated, index = sanctions.parse_un_xml(body, dates)
        return index, generated, rec, dates
    if list_id == "eu-fsf":
        body, rec = fetch.fetch("eu-fsf", sanctions.EU_XML, raw_dir, "xml", timeout=300, getter=getter, gz=True)
        generated, index = sanctions.parse_eu_xml(body, dates)
        return index, generated, rec, dates
    if list_id == "uk-sanctions":
        body, rec = fetch.fetch("uk-sanctions-list", sanctions.UK_XML, raw_dir, "xml", timeout=180, getter=getter, gz=True)
        generated, index = sanctions.parse_uk_xml(body, dates)
        return index, generated, rec, dates
    if list_id == "france-gels":
        # No designation dates in the file: the batch rule uses Headwind's own readings, as for OFAC.
        body, rec = fetch.fetch("dgtresor-gels", sanctions.FR_JSON, raw_dir, "json", timeout=180, getter=getter, gz=True)
        generated, index = sanctions.parse_fr_json(body)
        return index, generated, rec, None
    if list_id == "canada-sema":
        body, rec = fetch.fetch("gac-sema", sanctions.CA_XML, raw_dir, "xml", timeout=120, getter=getter)
        _CA_NAMES.clear()
        generated, index = sanctions.parse_canada_xml(body, dates, _CA_NAMES)
        return index, generated, rec, dates
    if list_id == "australia-dfat":
        # No designation dates: DFAT's Control Date is the date an entry last changed, so the batch rule uses
        # Headwind's own readings, as for OFAC and France.
        body, rec = fetch.fetch("dfat-consolidated", sanctions.AU_XLSX, raw_dir, "xlsx", timeout=120, getter=getter)
        generated, index = sanctions.parse_au_xlsx(body)
        return index, generated, rec, None
    if list_id == "japan-mof":
        # The file names carry a date, so the links come from the list page. The ship file is part of the list: if
        # it cannot be read the list fails and keeps its reading before (its ships are never reported as removed).
        page, _ = fetch.fetch("mof-jp-sanctions-page", sanctions.JP_PAGE, raw_dir, "html", timeout=60, getter=getter)
        csv_url, ship_url, generated = sanctions.jp_files(page.decode("utf-8", errors="replace"))
        body, rec = fetch.fetch("mof-jp-sanctions", csv_url, raw_dir, "csv", timeout=120, getter=getter, gz=True)
        ships, _ = fetch.fetch("mof-jp-vessels", ship_url, raw_dir, "csv", timeout=60, getter=getter)
        index = sanctions.parse_jp_csv(body, ships, dates)
        return index, generated, rec, dates
    raise ValueError(f"unknown list {list_id}")


def _lane_sanctions(raw_dir, prev, getter):
    """Compare each list with the index kept from the last run. A list's first reading only sets its baseline.

    Each list stands alone: a list that cannot be read or parsed keeps its index from the run before and
    is shown with the error, and the others go on. The lane fails only when no list can be read."""
    state_path = (Path(raw_dir).parent / "state" / "sanctions_index.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    prev_status = {l["id"]: l for l in (prev.get("sanctions_lists") or [])}
    now = fetch.now_utc()
    new_state, deltas, lists, recs, errors = {}, [], [], [], []
    for list_id in sanctions.LISTS:
        old = state.get(list_id) or {}
        try:
            index, source_generated, rec, dates = _read_list(list_id, raw_dir, getter)
            sanctions.check_size(list_id, index, old.get("index"))
        except Exception as exc:  # noqa: BLE001 - one list's failure is reported on that list
            errors.append(f"{list_id}: {exc}")
            if old:
                new_state[list_id] = old
            if list_id in prev_status:
                lists.append({**prev_status[list_id], "error": str(exc)[:300], "failed_at": now})
            continue
        recs.append(rec)
        last_change = old.get("last_change_at")
        history = old.get("added_history") or []
        form = sanctions.VESSEL_FORMAT.get(list_id, 1)
        ca_names = dict(_CA_NAMES) if list_id == "canada-sema" else None
        renumbered = []
        if old.get("index") and ca_names is not None:
            renumbered = sanctions.canada_renumbered(old["index"], index, old.get("names"), ca_names)
            if renumbered:
                old = {**old, "index": sanctions.apply_renumbering(old["index"], renumbered)}
        if old.get("index"):
            same_form = old.get("vessel_format", 1) == form
            if not same_form:
                print(f"  sanctions: {list_id}: vessel details were kept in an older form; not compared this run",
                      file=sys.stderr)
            same_names = old.get("name_format") == names.NAME_FORMAT
            if not same_names and list_id in sanctions.NAMED_LISTS:
                print(f"  sanctions: {list_id}: the reading before kept no names in this form; removals are counted, "
                      f"not named, and names are not compared this run", file=sys.stderr)
            d = sanctions.delta(list_id, old["index"], index, now, old.get("checked_at"), compare_vessels=same_form,
                                dates=dates, added_history=history, compare_names=same_names)
            if d and renumbered:
                d["renumbered"] = len(renumbered)
            if d:
                deltas.append(d)
                last_change = now
                # France: only national freezes are scored, so only they enter the list's baseline.
                history = batches.remember(history, (d.get("national") or d)["added"])
        baseline_set = old.get("baseline_set_at") or now
        new_state[list_id] = {"checked_at": now, "baseline_set_at": baseline_set, "last_change_at": last_change,
                              "vessel_format": form, "name_format": names.NAME_FORMAT, "added_history": history,
                              "index": index}
        if ca_names is not None:
            new_state[list_id]["names"] = ca_names
        lists.append(sanctions.status(list_id, index, now, baseline_set, source_generated, last_change))
    if not recs:
        raise RuntimeError("no sanctions list could be read: " + "; ".join(errors))
    for e in errors:
        print(f"  sanctions: {e}", file=sys.stderr)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    failed = tuple(e.split(":", 1)[0] for e in errors)
    cross, table = sanctions.vessel_crosslist({k: v.get("index") or {} for k, v in new_state.items()},
                                              stale=tuple(l for l in failed if l in new_state))
    cross["checked_at"] = now
    for d in deltas:
        sanctions.mark_also_on(d, table)
    return {"sanctions": sanctions.roll(prev.get("sanctions") or [], deltas, now), "sanctions_lists": lists,
            "vessel_crosslist": cross, "vessel_table": table}, recs


def _lane_screening(raw_dir, prev, getter):
    """trade.gov Consolidated Screening List, every list but the SDN list. The first run only sets the baseline."""
    state_path = (Path(raw_dir).parent / "state" / "screening_index.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = fetch.now_utc()
    body, rec = fetch.fetch("trade-gov-csl", screening.CSL_URL, raw_dir, "json", timeout=300, getter=getter, gz=True)
    deltas, lists, new_state = screening.compare(screening.parse(body), state, now)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return {"screening": sanctions.roll(prev.get("screening") or [], deltas, now), "screening_lists": lists}, [rec]


def _lane_controls(raw_dir, prev, getter):
    """BIS, OFAC and USTR rules and USTR's notices of the last 60 days (the page and the feed), and the register of
    dates the same agencies' documents of the last 800 days scheduled (what a public-inspection filing is matched
    against)."""
    today = date.today()
    body, rec = fetch.fetch("us-federal-register", controls.fr_url(today), raw_dir, "json", getter=getter)
    rules = controls.parse_fr(body)
    if not rules:
        raise ValueError("Federal Register returned no BIS, OFAC or USTR rules for the window")
    body, rec2 = fetch.fetch("us-federal-register", controls.ustr_url(today), raw_dir, "json", getter=getter)
    notices = controls.parse_fr(body)
    docs, recs = [], [rec, rec2]
    for url in controls.register_urls(today).values():
        b, r = fetch.fetch("us-federal-register", url, raw_dir, "json", timeout=90, getter=getter)
        docs += controls.parse_fr(b)
        recs.append(r)
    # Tariff actions: presidential documents whose title is a tariff action, and BIS's and ITA's Section 232
    # notices, both over the register's 800 days. Those of the lookback window are shown with the rules; all of
    # them go into the register, and the presidential ones give the pace.
    body, r = fetch.fetch("us-federal-register", controls.presidential_url(today), raw_dir, "json", timeout=90,
                          getter=getter)
    pres = controls.parse_presidential(body)
    recs.append(r)
    body, r = fetch.fetch("us-federal-register", controls.section232_url(today), raw_dir, "json", timeout=90,
                          getter=getter)
    s232 = controls.parse_section232(body)
    recs.append(r)
    window = (today - timedelta(days=controls.LOOKBACK_DAYS)).isoformat()
    _presidential_dates([p for p in pres if p["published_date"] >= window], prev, raw_dir, getter, recs)
    docs = list({d["id"]: d for d in docs + rules + notices + pres + s232}.values())
    shown = sorted({d["id"]: d for d in rules + notices + [d for d in pres + s232 if d["published_date"] >= window]
                    }.values(), key=lambda x: (x["published_date"], x["id"]), reverse=True)
    return {"controls": shown, "scheduled_dates": controls.scheduled(docs, today),
            "tariff_pace": controls.pace(pres, today)}, recs


def _presidential_dates(pres, prev, raw_dir, getter, recs):
    """Dates a tariff action's text sets (controls.text_dates), read once per document: a document read on an
    earlier run keeps what was found then. A text that cannot be read is noted on the document."""
    kept = {c["id"]: c for c in prev.get("controls") or [] if c.get("agency") == "President"}
    for p in pres:
        old = kept.get(p["id"])
        if old and old.get("text_read"):
            p.update({k: old.get(k) for k in ("named_dates", "computed_dates", "text_read")})
            continue
        if not p.get("raw_text_url"):
            continue
        try:
            body, rec = fetch.fetch("fr-presidential-text", p["raw_text_url"], raw_dir, "txt", getter=getter)
            p["named_dates"], p["computed_dates"] = controls.text_dates(body.decode("utf-8", "replace"),
                                                                       p["published_date"], p.get("signing_date"))
            p["text_read"] = True
            recs.append(rec)
        except Exception as exc:  # noqa: BLE001 - one document's text is noted on that document
            p["text_error"] = f"{type(exc).__name__}: {exc}"[:200]


def _lane_tariffs(raw_dir, prev, getter):
    """USITC's HTS revisions (the release list) and the White House's presidential actions (RSS): revisions and
    their pace, and tariff actions signed but not yet in the Federal Register (marked in finish_snapshot). The
    White House feed is noted, not failed, when it cannot be read: the revisions still count."""
    today = date.today()
    body, rec = fetch.fetch("usitc-hts", tariffs.HTS_RELEASES, raw_dir, "json", getter=getter)
    releases = tariffs.parse_releases(body)
    recs = [rec]
    out = {"hts_releases": {"revisions": releases[:tariffs.HTS_SHOWN], "by_year": tariffs.year_counts(releases),
                            "total": len(releases)},
           "hts_pace": tariffs.hts_pace(releases, today), "signed_actions": [], "signed_error": None}
    try:
        body, rec = fetch.fetch("whitehouse-actions", tariffs.WH_FEED, raw_dir, "xml", getter=getter)
        out["signed_actions"] = tariffs.parse_signed(body, today)
        recs.append(rec)
    except Exception as exc:  # noqa: BLE001
        out["signed_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out, recs


def _lane_unpress(raw_dir, prev, getter):
    """UN Security Council sanctions committee press releases from the UN's press feed: document number, date and
    link, kept 60 days. The feed holds the 10 newest releases of every UN body, so each reading also says whether
    it reached back to the reading before (`may_have_missed`)."""
    now = fetch.now_utc()
    body, rec = fetch.fetch("un-press", unpress.FEED, raw_dir, "xml", getter=getter)
    items = unpress.parse(body)
    found = [r for r in (unpress.committee_release(i) for i in items) if r]
    last = (prev.get("un_press") or {}).get("checked_at")
    return {"un_committee_releases": unpress.merge(prev.get("un_committee_releases") or [], found, now),
            "un_press": unpress.coverage(items, last, now)}, [rec]


SCOTUS_DOCKETS_PER_RUN = 100   # dockets read for decision dates in one run (the first run reads about 75)


def _lane_scotus(raw_dir, prev, getter):
    """The Supreme Court's opinions of this term and the last (slip opinion feeds), each case's decision date from
    its docket (read once), and the tariff-authority dockets, read every run. A docket that cannot be read is noted
    in `scotus_errors`; the opinion stays listed with its posting date. The lane fails only when no feed is read."""
    now = fetch.now_utc()
    found, recs, errors = [], [], []
    for yy in scotus.term_years(date.today()):
        try:
            body, rec = fetch.fetch("supremecourt-gov", scotus.FEED.format(yy=yy), raw_dir, "xml", getter=getter)
            found += scotus.parse_feed(body, yy)
            recs.append(rec)
        except Exception as exc:  # noqa: BLE001 - one term's feed failing is noted
            errors.append(f"term {yy:02d} feed: {type(exc).__name__}: {exc}"[:200])
    if not recs:
        raise RuntimeError("no Supreme Court feed could be read: " + "; ".join(errors))
    known = {o["docket"]: o for o in prev.get("scotus_opinions") or []}

    def docket(d):
        body, rec = fetch.fetch("supremecourt-gov-docket", scotus.DOCKET_JSON.format(docket=d), raw_dir, "json",
                                getter=getter)
        recs.append(rec)
        return scotus.parse_docket(body)

    dockets = {}
    for d in [f["docket"] for f in found if not known.get(f["docket"], {}).get("decided")][:SCOTUS_DOCKETS_PER_RUN]:
        try:
            dockets[d] = docket(d)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"docket {d}: {type(exc).__name__}: {exc}"[:200])
    tracked, todo, seen = [], list(scotus.TARIFF_DOCKETS), set()
    while todo:
        d = todo.pop(0)
        if d in seen:
            continue
        seen.add(d)
        try:
            t = dockets.get(d) or docket(d)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tracked docket {d}: {type(exc).__name__}: {exc}"[:200])
            t = next((x for x in prev.get("scotus_tracked") or [] if x["docket"] == d), None)
            if t:
                tracked.append({**t, "error": errors[-1]})
            continue
        tracked.append({**t, "url": scotus.DOCKET_PAGE.format(docket=d), "checked_at": now})
        todo += [r for r in t.get("related") or [] if r not in seen]
    return {"scotus_opinions": scotus.merge(prev.get("scotus_opinions") or [], found, dockets, now),
            "scotus_tracked": tracked, "scotus_errors": errors}, recs


# Case pages read in one run, and the time they may take (the workflow job has 15 minutes). The first reading, 108
# pages on 18 Nov 2026, took 1 min 35 s for the whole lane; pages left over are read on the next run, newest first.
UKSC_PAGES_PER_RUN = 120
UKSC_SECONDS_PER_RUN = 120


def _lane_uksc(raw_dir, prev, getter):
    """UK Supreme Court judgments of this calendar year and the last: the sitemap's judgment pages and the
    latest-judgments page (both every run), and each judgment's case page, read once (again when its judgment page
    changes). A case page that cannot be read is noted in `uksc_errors` and tried again on the next run. The lane
    fails only when the sitemap cannot be read or lists far too few judgment pages."""
    now, today = fetch.now_utc(), date.today()
    body, rec = fetch.fetch("supremecourt-uk", uksc.SITEMAP, raw_dir, "xml", getter=getter, gz=True)
    sm = uksc.parse_sitemap(body)
    recs, errors, latest = [rec], [], []
    try:
        body, rec = fetch.fetch("supremecourt-uk", uksc.LATEST, raw_dir, "html", getter=getter)
        latest = uksc.parse_latest(body)
        recs.append(rec)
    except Exception as exc:  # noqa: BLE001 - the cross-check failing is noted
        errors.append(f"latest judgments page: {type(exc).__name__}: {exc}"[:200])
    start = uksc.window_start(today)
    read = {s: lm for s, lm in (prev.get("uksc_read") or {}).items() if lm[:10] >= start}
    cases, began = [], time.monotonic()
    for slug in uksc.to_read(sm["judgment_pages"], read, latest, today, UKSC_PAGES_PER_RUN):
        if time.monotonic() - began > UKSC_SECONDS_PER_RUN:
            break
        try:
            body, rec = fetch.fetch("supremecourt-uk-case", uksc.CASE_PAGE.format(slug=slug), raw_dir, "html",
                                    timeout=30, getter=getter, gz=True)
            recs.append(rec)
            cases.append(uksc.parse_case(body, slug))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"case page {slug}: {type(exc).__name__}: {exc}"[:200])
            continue
        # A case named on the latest-judgments page that the sitemap does not list yet is marked with the time it
        # was read, so it is read once more when the sitemap lists its judgment page.
        read[slug] = sm["judgment_pages"].get(slug) or now
    pending = len(uksc.to_read(sm["judgment_pages"], read, latest, today, 10 ** 6))
    return {"uksc_judgments": uksc.merge(prev.get("uksc_judgments") or [], cases, today, now), "uksc_read": read,
            "uksc_errors": errors,
            "uksc_sitemap": {"checked_at": now, "generated": sm["generated"], "judgment_pages": len(sm["judgment_pages"]),
                             "read_this_run": len(cases), "pending": pending, "latest": latest}}, recs


def _lane_inspection(raw_dir, prev, getter):
    """Filings on public inspection by BIS, OFAC and USTR: the issues of the last few days, kept 30 days, and the
    text of each rule, proposed rule and USTR notice (read once per PDF). A text that cannot be read is noted on
    the filing; the lane still passes."""
    today = date.today()
    read, issues, recs = [], [], []
    last_ok = ((prev.get("lanes") or {}).get("inspection") or {}).get("fetched_at")
    for back in range(inspection.days_to_read(today, last_ok)):
        day = (today - timedelta(days=back)).isoformat()
        body, rec = fetch.fetch("fr-public-inspection", inspection.pi_url(day), raw_dir, "json", getter=getter)
        recs.append(rec)
        got = inspection.parse_issue(body, day)
        issues.append({"day": day, "total": json.loads(body).get("count") or 0, "filings": len(got)})
        read += got
    kept = inspection.merge(prev.get("inspection") or [], read, fetch.now_utc(), today)
    for r in kept:
        if r.get("text") or not inspection.wants_text(r):
            continue
        try:
            body, rec = fetch.fetch("fr-public-inspection-text", r["raw_text_url"], raw_dir, "txt", getter=getter)
            r["text"] = inspection.read_text(body)
            r.pop("text_error", None)
            recs.append(rec)
        except Exception as exc:  # noqa: BLE001 - one filing's text is noted on that filing
            r["text_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return {"inspection": kept, "inspection_issues": issues}, recs


def _lane_minerals(raw_dir, prev, getter):
    """USGS Mineral Commodity Summaries: net import reliance and import sources. Annual; context, not feed items."""
    item, rec0 = fetch.fetch("usgs-mcs-item", minerals.ITEM_URL.format(item=minerals.ITEM_ID), raw_dir, "json",
                             getter=getter)
    found = minerals.find_files(item)
    bodies, recs = {}, [rec0]
    for key, f in found["files"].items():
        body, rec = fetch.fetch(f"usgs-mcs-{key}", f["url"], raw_dir, "csv", getter=getter)
        minerals.check_md5(body, f["md5"], f["name"])
        bodies[key] = body.decode("utf-8-sig")
        recs.append(rec)
    by_name = {c["name"]: c["cc"] for c in json.loads(
        (ROOT / "doctrine" / "kit" / "geo" / "countries.json").read_text(encoding="utf-8"))["countries"]}
    cc_of = lambda name: minerals.NAME_CC.get(name) or by_name.get(name)  # noqa: E731
    doc = minerals.build(found, minerals.parse_reliance(bodies["reliance"]), minerals.parse_sources(bodies["sources"]),
                         cc_of)
    doc["watch"] = _minerals_watch(raw_dir, getter, recs)
    return {"minerals": doc}, recs


def _minerals_watch(raw_dir, getter, recs) -> dict:
    """Has USGS published the next Summaries, or Interior a newer critical minerals list? Both keyless. A check
    that fails is noted on the health entry; the lane still passes."""
    watch = {"checked_at": fetch.now_utc(), "edition_year": minerals.EDITION_YEAR,
             "list_document": minerals.CRITICAL_LIST["document"], "newer_editions": [], "newer_lists": [],
             "errors": []}
    checks = (("usgs-mcs-search", minerals.SB_SEARCH_URL.format(year=minerals.EDITION_YEAR + 1), "newer_editions",
               minerals.newer_editions, "a newer USGS edition"),
              ("fr-critical-minerals", minerals.FR_LISTS_URL.format(since=minerals.CRITICAL_LIST["published"]),
               "newer_lists", minerals.newer_lists, "a newer critical minerals list"))
    for source_id, url, key, parse, what in checks:
        try:
            body, rec = fetch.fetch(source_id, url, raw_dir, "json", getter=getter)
            watch[key] = parse(body)
            recs.append(rec)
        except Exception as exc:  # noqa: BLE001
            watch["errors"].append(f"{what}: {type(exc).__name__}: {exc}"[:200])
    return watch


LANES = {"fx": _lane_fx, "gem": _lane_gem, "energy": _lane_energy, "fao": _lane_fao, "pinksheet": _lane_pinksheet,
         "wfp": _lane_wfp, "baseline": _lane_baseline,
         "calendar": _lane_calendar, "sanctions": _lane_sanctions, "screening": _lane_screening,
         "controls": _lane_controls, "inspection": _lane_inspection, "minerals": _lane_minerals,
         "trade": _lane_trade, "tariffs": _lane_tariffs, "unpress": _lane_unpress,
         "scotus": _lane_scotus, "uksc": _lane_uksc}


def finish_snapshot(snap: dict, today: date) -> dict:
    """Add the derived parts: Verdict events and question drafts."""
    fao = snap.get("fao") or []
    ffpi = next((m for m in fao if m["id"] == "ffpi"), None)
    fao_dates = snap.get("fao_release_dates") or []
    next_release = next((d for d in fao_dates if d >= today.isoformat()), None)
    inspection.match(snap.get("inspection") or [], snap.get("scheduled_dates") or [])
    tariffs.mark_published(snap.get("signed_actions") or [], snap.get("controls") or [])
    events = controls.build_events(snap.get("controls") or [], today)
    events += releases.build_events(today, snap.get("fomc_dates") or [], snap.get("ecb_dates") or [], fao_dates,
                                    food.next_period(ffpi["period"]) if ffpi else None)
    snap["events"] = {"source": "headwind", "events": sorted(events, key=lambda e: (e["date"], e["id"]))}
    snap["question_drafts"] = releases.question_drafts(fao, next_release)
    snap["country_view"] = feed.country_view(snap)
    return snap


def collect(root: Path = ROOT, getter=None, only: list[str] | None = None) -> dict:
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    snap_path = data_dir / "snapshot.json"
    prev = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    now = fetch.now_utc()
    snap = {"generated_at": now, "method_version": feed.METHOD, "lanes": {}}
    drift_history = dict(prev.get("drift_history") or {})
    drift_warnings: dict[str, list[str]] = {}
    for lane, fn in LANES.items():
        fields = LANE_FIELDS[lane]
        prev_lane = (prev.get("lanes") or {}).get(lane) or {}
        if only and lane not in only:
            for k in fields:
                snap[k] = prev.get(k, EMPTY[k])
            snap["lanes"][lane] = {**prev_lane, "from_previous": True} if prev_lane else {"status": "not run"}
            continue
        try:
            result, recs = fn(raw_dir, prev, getter)
            sizes = health.sizes(lane, result)
            fails, warns = health.drift(lane, sizes, drift_history)
            if fails:
                raise ValueError("; ".join(fails))
            drift_history = health.remember(drift_history, sizes)
            for source_key, text in warns:
                drift_warnings.setdefault(source_key, []).append(text)
            snap.update(result)
            snap["lanes"][lane] = {"status": "ok", "fetched_at": now, "from_previous": False,
                                   "fetches": [{k: r[k] for k in ("url", "sha256", "bytes")} for r in recs]}
        except Exception as exc:
            had = bool(prev_lane.get("fetched_at"))
            for k in fields:
                snap[k] = prev.get(k, EMPTY[k]) if had else EMPTY[k]
            snap["lanes"][lane] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300],
                                   "failed_at": now, "from_previous": had,
                                   "fetched_at": prev_lane.get("fetched_at")}
    snap["drift_history"] = drift_history
    snap["drift_warnings"] = drift_warnings
    finish_snapshot(snap, datetime.now(timezone.utc).date())
    snap["health"] = health.build(snap, prev.get("health"), datetime.now(timezone.utc).date())
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


# What a run needs from the run before: the working snapshot (last good copies, FAO vintages, the WFP cache
# markers) and the two list indexes. A scheduled run has no disk of its own, so the build publishes these under
# site/data/state/ and the next run reads them back with `restore`.
STATE_FILES = {"snapshot.json": "data/state/snapshot.json",
               "state/sanctions_index.json": "data/state/sanctions_index.json",
               "state/screening_index.json": "data/state/screening_index.json"}


def restore(root: Path = ROOT, base_url: str = "", getter=None) -> dict[str, str]:
    """Fetch the last run's state from a published site into data/. A file already on disk is left
    alone. A file the site does not have (a 404, or a page in place of JSON, which is how Cloudflare
    Pages answers for a missing path) is "not restored", and that lane starts from a first reading.
    A site that could not be reached is "failed": the state may well be there, and going on would
    reset the list baselines and publish over them, so the caller should stop."""
    out = {}
    for local, published in STATE_FILES.items():
        dest = root / "data" / local
        if dest.exists():
            out[local] = "kept the copy on disk"
            continue
        body = None
        for attempt in (1, 2):
            try:
                body = (getter or fetch.get)(base_url.rstrip("/") + "/" + published, 120)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    out[local] = "not restored (the site has no such file)"
                    break
                out[local] = f"failed (HTTP {exc.code})"
            except Exception as exc:
                out[local] = f"failed ({type(exc).__name__})"
        if body is None:
            continue
        try:
            json.loads(body)
        except ValueError:
            out[local] = "not restored (the site has no such file)"
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        out[local] = f"restored, {len(body)} bytes"
    return out


def build_site(root: Path = ROOT, snapshot: dict | None = None, publish_state: bool = False) -> dict[str, str]:
    snap_path = root / "data" / "snapshot.json"
    if snapshot is None:
        if not snap_path.exists():
            raise SystemExit("No data/snapshot.json. Run `python tools/headwind.py collect` first; "
                             "Headwind does not build from made-up data.")
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    snap = snapshot
    feed_doc = feed.build_feed(snap)
    names = {c: geo.name(c) for c in {w["country"] for w in snap.get("local_food") or []}
             | {f["country"] for f in snap.get("fx") or [] if f.get("country")}
             | {m["country"] for m in snap.get("local_food_missing") or []}}
    names.update({c: geo.name(c) for c in feed.WATCHED})
    page = {k: snap.get(k) for k in ("generated_at", "method_version", "lanes", "health", "fx", "fx_official",
                                     "fx_official_missing", "fx_official_updated", "market_fx", "country_view",
                                     "energy", "fao", "pinksheet", "pinksheet_updated",
                                     "local_food", "local_food_missing", "sanctions", "sanctions_lists", "screening",
                                     "screening_lists", "controls", "inspection", "inspection_issues", "minerals",
                                     "question_drafts", "vessel_crosslist", "mineral_trade", "tariff_pace",
                                     "hts_releases", "hts_pace", "signed_actions", "signed_error",
                                     "un_committee_releases", "un_press", "scotus_opinions", "scotus_tracked",
                                     "scotus_errors", "uksc_judgments", "uksc_errors", "uksc_sitemap")}
    page["events"] = snap["events"]["events"]
    page["country_names"] = names
    # Counted-only filings as they may be published, whatever snapshot this is built from (a failed inspection
    # lane keeps a copy that may predate public_form).
    page["inspection"] = [inspection.public_form(r) for r in page.get("inspection") or []]

    def dump(obj) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    files = {
        "data/snapshot.json": dump(page),
        "data/feed.geojson": dump(feed_doc),
        "data/events.json": dump(snap["events"]),
        "data/baseline.json": dump({
            "generated_at": snap["generated_at"],
            "source": "World Bank, World Development Indicators (CC BY 4.0)",
            "lane": (snap.get("lanes") or {}).get("baseline"),
            "indicators": {v[0]: v[1] for v in baseline.INDICATORS.values()},
            "countries": snap.get("baseline") or {},
        }),
        "data/minerals.json": dump({"generated_at": snap["generated_at"],
                                    "lane": (snap.get("lanes") or {}).get("minerals"), **(snap.get("minerals") or {}),
                                    "trade": {"lane": (snap.get("lanes") or {}).get("trade"),
                                              **(snap.get("mineral_trade") or {})}}),
        "data/vessels.json": dump({
            "generated_at": snap["generated_at"],
            "note": ("Ships on the OFAC SDN list, the UK Sanctions List, France's asset-freeze register and Canada's "
                     "consolidated list, matched by IMO "
                     "number. Each list's own "
                     "entry ids, name and flag. Owners are not given. Ships without an IMO number are counted only."),
            "sources": {l: {"name": sanctions.LISTS[l]["name"], "url": sanctions.LISTS[l]["url"]}
                        for l in sanctions.VESSEL_LISTS},
            "summary": snap.get("vessel_crosslist") or {},
            "vessels": snap.get("vessel_table") or []}),
        "data/list-changes.json": dump(list_changes(snap)),
        "data/question_drafts.json": dump({"note": "Drafts only. Nothing here is registered in Verdict.",
                                           "drafts": snap.get("question_drafts") or []}),
    }
    if publish_state:
        for local, published in STATE_FILES.items():
            p = root / "data" / local
            if p.exists():
                files[published] = p.read_text(encoding="utf-8")
    src_dir = root / "site_src"
    if src_dir.exists():
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                files[p.relative_to(src_dir).as_posix()] = p.read_text(encoding="utf-8")

    out_dir = root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
    return files


def check_all(root: Path = ROOT) -> list[str]:
    errs = registers.check(root / "doctrine")
    regs = registers.ids(root / "doctrine")
    feed_path = root / "site" / "data" / "feed.geojson"
    if not feed_path.exists():
        return errs + ["site/data/feed.geojson is missing: run collect and build first"]
    feed_doc = json.loads(feed_path.read_text(encoding="utf-8"))
    for feat in feed_doc.get("features", []):
        fid = (feat.get("properties") or {}).get("id", "?")
        for std, sev, msg in contract.check(feat, regs):
            if sev == "error":
                errs.append(f"{fid}: {std}: {msg}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headwind: economic stress, sanctions and export-control monitor.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*", choices=sorted(LANES), help="run only these lanes; keep the rest as they were")
    b = sub.add_parser("build")
    b.add_argument("--publish-state", action="store_true",
                   help="also write data/state/ into site/, for a scheduled run to restore from")
    r = sub.add_parser("restore")
    r.add_argument("--from", dest="base_url", required=True, help="the published site to read the last state from")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect(only=args.only)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:9s} {st.get('status')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        gh = bool(os.environ.get("GITHUB_ACTIONS"))
        for key, h in (snap.get("health") or {}).items():
            for w in h.get("warnings") or []:
                print(f"::warning::{key}: {w}" if gh else f"  warning {key}: {w}")
            if h["state"] in ("late", "stale"):
                line = f"{key}: data of {h.get('data_as_of')} is {h['state']}"
                print(f"::warning::{line}" if gh else f"  warning {line}")
        print("  health: " + ", ".join(f"{n} {s}" for s, n in health.summary(snap.get("health") or {}).items()))
        anomalies = sum(1 for k in ("fx", "fx_official", "market_fx", "energy", "fao", "pinksheet", "local_food", "sanctions",
                                    "screening")
                        for x in snap.get(k) or [] if x.get("anomaly"))
        print(f"Collected {len(snap['fx'])} currencies, {len(snap['energy'])} energy series, {len(snap['fao'])} FAO "
              f"indices, {len(snap.get('pinksheet') or [])} Pink Sheet prices, "
              f"{len(snap['local_food'])} countries' local food prices, {len(snap['baseline'])} country "
              f"baselines, {len(snap['events']['events'])} events; {anomalies} anomalies. Sanctions lists: "
              f"{len(snap['sanctions_lists'])} read, {len(snap['sanctions'])} changes kept; screening lists: "
              f"{len(snap['screening_lists'])} read, {len(snap['screening'])} changes kept; "
              f"{len(snap['controls'])} Federal Register rules and USTR notices, "
              f"{len(snap.get('scheduled_dates') or [])} scheduled dates, "
              f"{len(snap.get('inspection') or [])} public-inspection filings; "
              f"{len((snap.get('minerals') or {}).get('reliance') or [])} mineral commodities.")
        return 0 if any(s.get("status") == "ok" for s in snap["lanes"].values()) else 1
    if args.cmd == "build":
        files = build_site(ROOT, publish_state=args.publish_state)
        print(f"Built site/ ({len(files)} files).")
        return 0
    if args.cmd == "restore":
        got = restore(ROOT, args.base_url)
        for name, what in got.items():
            print(f"  {name}: {what}")
        if any(v.startswith("failed") for v in got.values()):
            print("The published site could not be read. Stopping, so this run does not start the list "
                  "baselines over and publish that in place of the last run's state.")
            return 1
        return 0
    if args.cmd == "check":
        errs = check_all(ROOT)
        for e in errs:
            print("  -", e)
        print(f"Headwind check: {'PASS' if not errs else f'FAIL ({len(errs)} problems)'}")
        return 1 if errs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
