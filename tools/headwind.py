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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import (baseline, commodities, controls, feed, fetch, food, markets, minerals, releases,  # noqa: E402,F401
                      sanctions, screening)
from tic_doctrine import contract, geo, registers  # noqa: E402

LANE_FIELDS = {
    "fx": ["fx"],
    "energy": ["energy"],
    "fao": ["fao", "fao_release_dates"],
    "wfp": ["local_food", "local_food_missing"],
    "baseline": ["baseline"],
    "calendar": ["fomc_dates", "ecb_dates"],
    "sanctions": ["sanctions", "sanctions_lists"],
    "screening": ["screening", "screening_lists"],
    "controls": ["controls"],
    "minerals": ["minerals"],
}
EMPTY = {"fx": [], "energy": [], "fao": [], "fao_release_dates": [], "local_food": [], "local_food_missing": [],
         "baseline": {}, "fomc_dates": [], "ecb_dates": [], "sanctions": [], "sanctions_lists": [], "screening": [],
         "screening_lists": [], "controls": [], "minerals": {}}


def _lane_fx(raw_dir, prev, getter):
    body, rec = fetch.fetch("ecb-eurofxref", markets.ECB_HIST_ZIP, raw_dir, "zip", getter=getter)
    return {"fx": markets.measure_fx(markets.parse_ecb_zip(body))}, [rec]


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


def _lane_fao(raw_dir, prev, getter):
    page, rec1 = fetch.fetch("fao-ffpi-page", food.FAO_PAGE, raw_dir, "html", getter=getter)
    html = page.decode("utf-8", errors="replace")
    body, rec2 = fetch.fetch("fao-ffpi", food.fao_csv_url(html), raw_dir, "csv", getter=getter)
    series = food.parse_fao_csv(body.decode("utf-8-sig"))
    return {"fao": food.measure_fao(series), "fao_release_dates": food.fao_release_dates(html)}, [rec1, rec2]


def _lane_wfp(raw_dir, prev, getter):
    wanted = json.loads((ROOT / "config" / "wfp_countries.json").read_text(encoding="utf-8"))["countries"]
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
        if cached and cached.get("hdx_last_modified") == res["last_modified"]:
            m = {k: cached[k] for k in cached if k not in ("country", "iso3", "dataset", "hdx_last_modified")}
            m["months_old"] = ((int(today_period[:4]) - int(m["period"][:4])) * 12
                               + int(today_period[5:7]) - int(m["period"][5:7]))
            m["stale"] = m["months_old"] > food.WFP_STALE_MONTHS
            m["anomaly"] = bool(m["anomaly"] and not m["stale"])
        else:
            try:
                csv_body, r = fetch.fetch(f"wfp-prices-{iso3.lower()}", res["url"], raw_dir, "csv", timeout=120,
                                          getter=getter)
            except Exception as exc:  # one country failing must not lose the others
                missing.append({"country": cc, "reason": f"fetch failed: {type(exc).__name__}"})
                continue
            recs.append(r)
            m = food.measure_wfp(csv_body.decode("utf-8-sig", errors="replace"), today_period)
            if not m:
                missing.append({"country": cc, "reason": "too few price series"})
                continue
        out.append({"country": cc, "iso3": iso3, "dataset": res["dataset"],
                    "hdx_last_modified": res["last_modified"], **m})
    return {"local_food": out, "local_food_missing": missing}, recs


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


def _lane_sanctions(raw_dir, prev, getter):
    """Compare each list with the index kept from the last run. The first run only sets the baseline."""
    state_path = (Path(raw_dir).parent / "state" / "sanctions_index.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = fetch.now_utc()
    b1, rec1 = fetch.fetch("ofac-sdn", sanctions.OFAC_SDN_CSV, raw_dir, "csv", timeout=180, getter=getter)
    b2, rec2 = fetch.fetch("un-sc-consolidated", sanctions.UN_XML, raw_dir, "xml", timeout=120, getter=getter)
    un_generated, un_index = sanctions.parse_un_xml(b2)
    readings = {"ofac-sdn": (sanctions.parse_sdn_csv(b1.decode("utf-8", errors="replace")), None),
                "un-consolidated": (un_index, un_generated)}
    new_state, deltas, lists = {}, [], []
    for list_id, (index, source_generated) in readings.items():
        old = state.get(list_id) or {}
        sanctions.check_size(list_id, index, old.get("index"))
        if old.get("index"):
            d = sanctions.delta(list_id, old["index"], index, now, old.get("checked_at"))
            if d:
                deltas.append(d)
        baseline_set = old.get("baseline_set_at") or now
        new_state[list_id] = {"checked_at": now, "baseline_set_at": baseline_set, "index": index}
        lists.append(sanctions.status(list_id, index, now, baseline_set, source_generated))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return {"sanctions": sanctions.roll(prev.get("sanctions") or [], deltas, now), "sanctions_lists": lists}, [rec1, rec2]


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
    body, rec = fetch.fetch("us-federal-register", controls.fr_url(date.today()), raw_dir, "json", getter=getter)
    rules = controls.parse_fr(body)
    if not rules:
        raise ValueError("Federal Register returned no BIS or OFAC rules for the window")
    return {"controls": rules}, [rec]


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
    return {"minerals": minerals.build(found, minerals.parse_reliance(bodies["reliance"]),
                                       minerals.parse_sources(bodies["sources"]), cc_of)}, recs


LANES = {"fx": _lane_fx, "energy": _lane_energy, "fao": _lane_fao, "wfp": _lane_wfp, "baseline": _lane_baseline,
         "calendar": _lane_calendar, "sanctions": _lane_sanctions, "screening": _lane_screening,
         "controls": _lane_controls, "minerals": _lane_minerals}


def finish_snapshot(snap: dict, today: date) -> dict:
    """Add the derived parts: Verdict events and question drafts."""
    fao = snap.get("fao") or []
    ffpi = next((m for m in fao if m["id"] == "ffpi"), None)
    fao_dates = snap.get("fao_release_dates") or []
    next_release = next((d for d in fao_dates if d >= today.isoformat()), None)
    events = controls.build_events(snap.get("controls") or [], today)
    events += releases.build_events(today, snap.get("fomc_dates") or [], snap.get("ecb_dates") or [], fao_dates,
                                    food.next_period(ffpi["period"]) if ffpi else None)
    snap["events"] = {"source": "headwind", "events": sorted(events, key=lambda e: (e["date"], e["id"]))}
    snap["question_drafts"] = releases.question_drafts(fao, next_release)
    return snap


def collect(root: Path = ROOT, getter=None, only: list[str] | None = None) -> dict:
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    snap_path = data_dir / "snapshot.json"
    prev = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    now = fetch.now_utc()
    snap = {"generated_at": now, "method_version": feed.METHOD, "lanes": {}}
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
    finish_snapshot(snap, datetime.now(timezone.utc).date())
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return snap


def build_site(root: Path = ROOT, snapshot: dict | None = None) -> dict[str, str]:
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
    page = {k: snap.get(k) for k in ("generated_at", "method_version", "lanes", "fx", "energy", "fao", "local_food",
                                     "local_food_missing", "sanctions", "sanctions_lists", "screening",
                                     "screening_lists", "controls", "minerals", "question_drafts")}
    page["events"] = snap["events"]["events"]
    page["country_names"] = names

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
                                    "lane": (snap.get("lanes") or {}).get("minerals"), **(snap.get("minerals") or {})}),
        "data/question_drafts.json": dump({"note": "Drafts only. Nothing here is registered in Verdict.",
                                           "drafts": snap.get("question_drafts") or []}),
    }
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
    sub.add_parser("build")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect(only=args.only)
        for lane, st in snap["lanes"].items():
            extra = f" ({st.get('error')})" if st.get("status") == "failed" else ""
            print(f"  {lane:9s} {st.get('status')}{' [last good copy]' if st.get('from_previous') else ''}{extra}")
        anomalies = sum(1 for k in ("fx", "energy", "fao", "local_food") for x in snap.get(k) or [] if x.get("anomaly"))
        print(f"Collected {len(snap['fx'])} currencies, {len(snap['energy'])} energy series, {len(snap['fao'])} FAO "
              f"indices, {len(snap['local_food'])} countries' local food prices, {len(snap['baseline'])} country "
              f"baselines, {len(snap['events']['events'])} events; {anomalies} anomalies. Sanctions lists: "
              f"{len(snap['sanctions_lists'])} read, {len(snap['sanctions'])} changes kept; screening lists: "
              f"{len(snap['screening_lists'])} read, {len(snap['screening'])} changes kept; "
              f"{len(snap['controls'])} Federal Register rules; "
              f"{len((snap.get('minerals') or {}).get('reliance') or [])} mineral commodities.")
        return 0 if any(s.get("status") == "ok" for s in snap["lanes"].values()) else 1
    if args.cmd == "build":
        files = build_site(ROOT)
        print(f"Built site/ ({len(files)} files).")
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
