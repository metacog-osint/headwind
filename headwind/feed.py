"""Build Headwind's contract-v2 feed (tic-feed/2, GeoJSON) from the collected snapshot.

Every item from the live lanes (exchange rates, energy, FAO indices, local food prices) is a
measurement: kind "observation", tier "routine" or "anomaly". Headwind states no probability.
The sanctions and export-control blocks are kept for when those lanes get live collectors; a
live snapshot carries empty lists for them.
"""
from __future__ import annotations

import calendar
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, confidence, geo, likelihood  # noqa: E402

from . import food, markets, stats  # noqa: E402

SITE = "https://headwind.theintelligence.company"
METHOD = "headwind-1.1"
LANGUAGE_KEY = "https://github.com/metacog-osint/tic-doctrine/blob/main/docs/language-key.md"

SRC_OFAC = {
    "id": "ofac-sdn",
    "publisher": "US Department of the Treasury (OFAC)",
    "title": "Specially Designated Nationals (SDN) & Consolidated Sanctions List",
    "url": "https://ofac.treasury.gov/specially-designated-nationals-and-blocked-persons-list-sdn-human-readable-lists",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-treasury-ofac",
    "source_type": "official or market data",
    "descriptor": "Official OFAC SDN entity and vessel (IMO/MMSI) sanctions designations.",
}

SRC_FR = {
    "id": "us-federal-register",
    "publisher": "US Federal Register (BIS / USTR)",
    "title": "Federal Register Documents & Public Inspection Filings",
    "url": "https://www.federalregister.gov/api/v1/documents.json",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-federal-register",
    "source_type": "official or market data",
    "descriptor": "BIS and USTR export-control rule stays, suspensions, and effective-date notices.",
}

SRC_FAO = {
    "id": "fao-ffpi",
    "publisher": "FAO",
    "title": "FAO Food Price Index (FFPI)",
    "url": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
    "licence": "CC BY-NC-SA 3.0 IGO",
    "grade": "A1",
    "independence_group": "fao",
    "source_type": "official or market data",
    "descriptor": "Monthly global food commodity price index across cereals, vegetable oils, dairy, meat, and sugar.",
}

SRC_ECB = {
    "id": "ecb-eurofxref",
    "publisher": "European Central Bank",
    "title": "Euro foreign exchange reference rates",
    "url": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
    "licence": "ECB statistics: free reuse with the source credited",
    "grade": "A1",
    "independence_group": "ecb",
    "source_type": "official or market data",
    "descriptor": "Daily reference rates for about 30 currencies against the euro, set on TARGET business days.",
}

SRC_EIA = {
    "id": "eia-spot-fred",
    "publisher": "US Energy Information Administration, retrieved from FRED (Federal Reserve Bank of St. Louis)",
    "title": "Crude oil and natural gas daily spot prices",
    "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
    "licence": "US public domain (EIA); citation requested",
    "grade": "A1",
    "independence_group": "us-eia",
    "source_type": "official or market data",
    "descriptor": "Brent, WTI and Henry Hub daily spot prices as published by EIA.",
}

SRC_WFP = {
    "id": "wfp-food-prices-hdx",
    "publisher": "World Food Programme, via the Humanitarian Data Exchange (OCHA)",
    "title": "WFP food prices by market",
    "url": "https://data.humdata.org/organization/wfp",
    "licence": "CC BY-IGO",
    "grade": "B2",
    "independence_group": "wfp",
    "source_type": "official or market data",
    "descriptor": "Monthly retail and wholesale food prices collected by WFP and partners in local markets.",
}


def _plus_hours(iso_utc: str, hours: int) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return (dt + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _month_end(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}T00:00:00Z"


def _conf(ind_lines: int, cov: float, alt_rej: int) -> dict:
    return confidence.fields(confidence.Evidence(
        independent_lines=max(1, ind_lines),
        contradicted=False,
        coverage_fraction=cov,
        grades=["A1", "A2"],
        alternatives_rejected=alt_rej,
        method_scored=False,
        assumption_status="holds",
        ease_of_faking="low",
        horizon_days=0.0,
    ))


def _z_text(z) -> str:
    return "no baseline yet" if z is None else f"z {z:+.1f}"


def _observation(item_id: str, title: str, summary: str, *, anomaly: bool, data_as_of: str, generated: str,
                 valid_until: str, countries: list[str], ncf: list[str], requirement_ids: list[str],
                 measures: dict, anchor: str, source: dict, indicator_id: str, baseline_ref: str,
                 coverage: float, lane_accessed: str | None, ascope: list[str]) -> dict:
    props = {
        "contract": CONTRACT,
        "id": item_id,
        "program": "headwind",
        "title": title,
        "summary": summary,
        "kind": "observation",
        "tier": "anomaly" if anomaly else "routine",
        "status": "actual",
        "msg_type": "new",
        "human_review": "none",
        "us_person_data": "none",
        "status_class": "reported",
        "product_category": "current",
        "data_as_of": data_as_of,
        "published_at": generated,
        "valid_until": valid_until,
        "countries": countries,
        "pmesii_pt": ["economic"],
        "ascope": ascope,
        "ie_aspect": ["informational"],
        "ncf": ncf,
        "requirement_ids": requirement_ids,
        "method_version": METHOD,
        "coverage_fraction": coverage,
        "precision_class": "country" if countries else "none",
        "measures": measures,
        "visual": {"type": "page", "url": f"{SITE}/#{anchor}"},
        "sources": [{**source, "accessed_at": lane_accessed or generated}],
    }
    if anomaly:
        # No indicator_id: the contract ties an indicator to a hypothesis, and Headwind has no warning
        # problem for economic stress yet. HW-IND-4 to HW-IND-6 are registered for when one is written.
        props["baseline_ref"] = baseline_ref
    geom = None
    if len(countries) == 1:
        pt = geo.point(countries[0])
        if pt:
            geom = {"type": "Point", "coordinates": [pt[1], pt[0]]}
    if geom is None:
        props["precision_class"] = "none" if not countries else "country"
    return {"type": "Feature", "geometry": geom, "properties": props}


def live_features(snapshot: dict) -> list[dict]:
    generated = snapshot["generated_at"]
    valid_until = _plus_hours(generated, 48)
    lanes = snapshot.get("lanes") or {}
    feats = []

    def accessed(lane: str) -> str | None:
        return (lanes.get(lane) or {}).get("fetched_at")

    for f in snapshot.get("fx") or []:
        cc = f.get("country")
        name = (geo.name(cc) if cc else None) or ("Euro area" if f["currency"] == "EUR" else f["currency"])
        feats.append(_observation(
            f"headwind:fx:{f['currency']}:{f['date']}",
            f"{name} ({f['currency']}): {abs(f['change_pct']):.1f}% {f['direction']} against the US dollar "
            f"in {markets.FX_HORIZON} business days ({_z_text(f['z'])})",
            f"{f['per_usd']:g} {f['currency']} per US dollar on {f['date']}, against {f['prior_per_usd']:g} on "
            f"{f['prior_date']}. Measured against the currency's own {f['baseline_n']} earlier "
            f"{markets.FX_HORIZON}-day changes. ECB reference rate, restated per US dollar.",
            anomaly=f["anomaly"], data_as_of=f"{f['date']}T00:00:00Z", generated=generated, valid_until=valid_until,
            countries=[cc] if cc else [], ncf=["provide_funding_liquidity", "provide_capital_markets"],
            requirement_ids=["HW-PIR-4"],
            measures={"per_usd": f["per_usd"], "change_pct": f["change_pct"], "z": f["z"],
                      "baseline_n": f["baseline_n"], "flag_rate": f.get("flag_rate")},
            anchor="fx", source=SRC_ECB, indicator_id="HW-IND-4",
            baseline_ref=f"rolling: the series' own {markets.FX_WINDOW} prior {markets.FX_HORIZON}-day changes; "
                         f"anomaly at |z| >= {stats.Z_ANOMALY:g} and a move of at least {markets.FX_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("fx"), ascope=["events"]))

    for e in snapshot.get("energy") or []:
        feats.append(_observation(
            f"headwind:energy:{e['id']}:{e['date']}",
            f"{e['name']}: {e['change_pct']:+.1f}% in {markets.EN_HORIZON} trading days ({_z_text(e['z'])})",
            f"{e['price']:g} {e['unit']} on {e['date']}, against {e['prior_price']:g} on {e['prior_date']}. "
            f"Measured against the series' own {e['baseline_n']} earlier {markets.EN_HORIZON}-day changes.",
            anomaly=e["anomaly"], data_as_of=f"{e['date']}T00:00:00Z", generated=generated, valid_until=valid_until,
            countries=[], ncf=["store_fuel_maintain_reserves", "transport_by_pipeline"],
            requirement_ids=["HW-PIR-4"],
            measures={"price": e["price"], "change_pct": e["change_pct"], "z": e["z"], "baseline_n": e["baseline_n"], "flag_rate": e.get("flag_rate")},
            anchor="energy", source=SRC_EIA, indicator_id="HW-IND-5",
            baseline_ref=f"rolling: the series' own {markets.EN_WINDOW} prior {markets.EN_HORIZON}-day changes; "
                         f"anomaly at |z| >= {stats.Z_ANOMALY:g} and a move of at least {markets.EN_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("energy"), ascope=["events"]))

    for c in snapshot.get("fao") or []:
        feats.append(_observation(
            f"headwind:food:{c['id']}:{c['period']}",
            f"{c['name']} ({c['period']}): {c['value']:g}, {c['change_pct']:+.1f}% on the month ({_z_text(c['z'])})",
            f"{c['value']:g} for {c['period']}, against {c['prior_value']:g} for {c['prior_period']} "
            f"(2014-2016 = 100). FAO revises earlier months; these are the values as published today.",
            anomaly=c["anomaly"], data_as_of=_month_end(c["period"]), generated=generated, valid_until=valid_until,
            countries=[], ncf=["provide_food_products", "provide_agricultural_products", "maintain_supply_chains"],
            requirement_ids=["HW-PIR-3"],
            measures={"index_value": c["value"], "change_pct": c["change_pct"], "z": c["z"],
                      "baseline_n": c["baseline_n"], "flag_rate": c.get("flag_rate")},
            anchor="food", source=SRC_FAO, indicator_id="HW-IND-3",
            baseline_ref=f"rolling: the index's own {food.FAO_WINDOW} prior monthly changes; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a move of at least {food.FAO_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("fao"), ascope=["events"]))

    for w in snapshot.get("local_food") or []:
        if w.get("stale"):
            continue        # too old to describe current conditions; the page lists it as no recent data
        cc = w["country"]
        name = geo.name(cc) or cc
        feats.append(_observation(
            f"headwind:localfood:{cc}:{w['period']}",
            f"{name}: local food prices {w['median_change_pct']:+.0f}% in {food.WFP_HORIZON} months, median of "
            f"{w['series']} price series ({_z_text(w['z'])})",
            f"Median {food.WFP_HORIZON}-month change to {w['period']} across {w['series']} market-and-commodity "
            f"series in {w['markets']} markets; {round(w['share_rising'] * 100)}% of series rose. Nominal prices in "
            f"local currency, judged against the country's own {w['baseline_n']} earlier medians.",
            anomaly=w["anomaly"], data_as_of=_month_end(w["period"]), generated=generated, valid_until=valid_until,
            countries=[cc], ncf=["provide_food_products", "provide_agricultural_products"],
            requirement_ids=["HW-PIR-5"],
            measures={"median_change_pct": w["median_change_pct"], "series": w["series"], "markets": w["markets"],
                      "share_rising": w["share_rising"], "z": w["z"], "baseline_n": w["baseline_n"], "flag_rate": w.get("flag_rate")},
            anchor="local-food", source={**SRC_WFP, "url": w.get("dataset") or SRC_WFP["url"]},
            indicator_id="HW-IND-6",
            baseline_ref=f"rolling: the country's own {food.WFP_WINDOW} prior monthly medians; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a median move of at least {food.WFP_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("wfp"), ascope=["events", "people"]))
    return feats


def build_feed(snapshot: dict) -> dict:
    """Build a contract-v2 GeoJSON FeatureCollection from Headwind's normalized snapshot."""
    generated = snapshot["generated_at"]
    valid_until = _plus_hours(generated, 24)
    sanctions = snapshot.get("sanctions", [])
    controls = snapshot.get("controls", [])

    features = []

    # 1. OFAC SDN entity & shadow-fleet vessel designations (HW-WP-1). No live collector yet.
    for s in sanctions:
        is_warn = s["vessels_added"] >= 2 or s["dual_use_network"]
        conf = _conf(2, 0.90, 1)
        prob = 0.85
        props = {
            "contract": CONTRACT,
            "id": f"headwind:ofac:{s['id']}",
            "program": "headwind",
            "title": f"OFAC SDN delta: {s['title']} ({s['entities_added']} entities, {s['vessels_added']} vessels)",
            "summary": s["summary"],
            "kind": "assessment" if is_warn else "observation",
            "tier": "warning" if is_warn else "routine",
            "status": "actual",
            "msg_type": "new",
            "human_review": "sampled",
            "us_person_data": "none",
            "status_class": "assessed" if is_warn else "reported",
            "product_category": "warning" if is_warn else "current",
            "data_as_of": f"{s['date']}T00:00:00Z",
            "published_at": generated,
            "valid_until": valid_until,
            "countries": s["countries"],
            "pmesii_pt": ["economic", "political"],
            "ascope": ["organizations", "capabilities"],
            "ie_aspect": ["informational", "physical"],
            "ncf": ["transport_by_vessel", "maintain_supply_chains", "store_fuel_maintain_reserves"],
            "requirement_ids": ["HW-PIR-1", "HW-EEI-1"],
            "method_version": METHOD,
            "coverage_fraction": 0.90,
            "precision_class": "country",
            "measures": {
                "entities_added": s["entities_added"],
                "vessels_added": s["vessels_added"],
            },
            "visual": {"type": "table", "url": f"{SITE}/#{s['id']}"},
            "sources": [{**SRC_OFAC, "accessed_at": generated}],
        }
        if is_warn:
            props.update({
                "change_from_prior": "new",
                "change_reason": f"New OFAC SDN batch adding {s['entities_added']} entities and {s['vessels_added']} shadow-fleet vessels.",
                "warning_problem_id": "HW-WP-1",
                "indicator_id": "HW-IND-1",
                "hypothesis_id": "HW-H-1A",
                "direction": "supports",
                "indicator_state": "present",
                "probability": prob,
                "likelihood_term": likelihood.term_for(prob)["id"],
                **conf,
                "alternatives": [
                    {
                        "hypothesis": "Targeted enforcement campaign to force shadow-fleet flag/club de-registration and port denial",
                        "tell_apart": "Subsequent AIS flag-hopping or loitering outside Indian/Chinese terminals in Wake.",
                    },
                    {
                        "hypothesis": "Routine administrative maintenance of existing sanctions evasion aliases",
                        "tell_apart": "No active operational vessels or active transshipment hubs in the batch.",
                    },
                ],
            })
        geom = {"type": "Point", "coordinates": [s["lon"], s["lat"]]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 2. Export-control & tariff rule deadlines (HW-IND-2). No live collector yet.
    for r in controls:
        is_warn = r["days_to_deadline"] <= 14
        conf = _conf(2, 0.90, 1)
        prob = 0.85
        props = {
            "contract": CONTRACT,
            "id": f"headwind:control:{r['id']}",
            "program": "headwind",
            "title": f"{r['agency']} deadline ({r['deadline_date']}): {r['title']}",
            "summary": r["summary"],
            "kind": "assessment" if is_warn else "observation",
            "tier": "warning" if is_warn else "routine",
            "status": "actual",
            "msg_type": "new",
            "human_review": "sampled",
            "us_person_data": "none",
            "status_class": "assessed" if is_warn else "reported",
            "product_category": "warning" if is_warn else "current",
            "data_as_of": f"{r['published_date']}T00:00:00Z",
            "published_at": generated,
            "valid_until": f"{r['deadline_date']}T23:59:59Z",
            "countries": r["countries"],
            "pmesii_pt": ["economic", "political"],
            "ascope": ["organizations"],
            "ie_aspect": ["informational"],
            "ncf": ["manufacture_equipment", "maintain_supply_chains", "provide_it_products"],
            "requirement_ids": ["HW-PIR-2", "HW-EEI-2"],
            "method_version": METHOD,
            "coverage_fraction": 0.90,
            "precision_class": "country",
            "measures": {"days_to_deadline": r["days_to_deadline"]},
            "visual": {"type": "page", "url": r["url"]},
            "sources": [{**SRC_FR, "accessed_at": generated}],
        }
        if is_warn:
            props.update({
                "change_from_prior": "new",
                "change_reason": f"{r['agency']} deadline on {r['deadline_date']} is {r['days_to_deadline']} days away.",
                "warning_problem_id": "HW-WP-1",
                "indicator_id": "HW-IND-2",
                "hypothesis_id": "HW-H-1B",
                "direction": "supports",
                "indicator_state": "present",
                "probability": prob,
                "likelihood_term": likelihood.term_for(prob)["id"],
                **conf,
                "alternatives": [
                    {
                        "hypothesis": "Synchronized BIS/USTR administrative stay extending the US-China trade truce",
                        "tell_apart": "Public Inspection filing of a stay document on or before the deadline date.",
                    },
                    {
                        "hypothesis": "Automatic rule reimposition on the deadline date",
                        "tell_apart": "Absence of a BIS stay filing on Federal Register Public Inspection.",
                    },
                ],
            })
        geom = {"type": "Point", "coordinates": [r["lon"], r["lat"]]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 3. Live lanes: exchange rates, energy, FAO indices, local food prices. Measurements only.
    features.extend(live_features(snapshot))

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "headwind",
        "generated_at": generated,
        "licence": ("Headwind code MIT; ECB reference rates free to reuse with credit; EIA data US public domain; "
                    "FAO CC BY-NC-SA 3.0 IGO; WFP food prices CC BY-IGO"),
        "attribution": ("Headwind, The Intelligence Company. Data: European Central Bank; US Energy Information "
                        "Administration via FRED; FAO; World Food Programme via the Humanitarian Data Exchange."),
        "language_key": LANGUAGE_KEY,
        "features": features,
    }
