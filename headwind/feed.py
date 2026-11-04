"""Build Headwind's contract-v2 feed (tic-feed/2, GeoJSON) from normalized sanctions, export-control, and commodity snapshot."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, confidence, likelihood  # noqa: E402

SITE = "https://headwind.theintelligence.company"
METHOD = "headwind-1.0"
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

SRC_IGC = {
    "id": "igc-goi",
    "publisher": "International Grains Council",
    "title": "Grains and Oilseeds Index (GOI)",
    "url": "https://igc.int/en/public-site/markets/marketinfo-goi.aspx",
    "licence": "IGC public market terms",
    "grade": "A2",
    "independence_group": "igc",
    "source_type": "official or market data",
    "descriptor": "Daily export price index for wheat, maize, soybeans, rice, and barley.",
}


def _plus_hours(iso_utc: str, hours: int) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return (dt + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def build_feed(snapshot: dict) -> dict:
    """Build a contract-v2 GeoJSON FeatureCollection from Headwind's normalized snapshot."""
    generated = snapshot["generated_at"]
    valid_until = _plus_hours(generated, 24)
    sanctions = snapshot.get("sanctions", [])
    controls = snapshot.get("controls", [])
    commodities = snapshot.get("commodities", [])

    features = []

    # 1. OFAC SDN entity & shadow-fleet vessel designations (HW-WP-1)
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

    # 2. Export-control & tariff rule deadlines (HW-IND-2)
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
                "change_reason": f"New OFAC SDN batch adding {s['entities_added']} entities and {s['vessels_added']} shadow-fleet vessels.",
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

    # 3. Commodity & food price benchmarks (HW-PIR-3)
    for c in commodities:
        is_anom = abs(c["mom_pct"]) >= 2.0
        props = {
            "contract": CONTRACT,
            "id": f"headwind:commodity:{c['id']}:{c['period']}",
            "program": "headwind",
            "title": f"{c['name']} ({c['period']}): {c['current_value']} ({c['mom_pct']:+.2f}% vs prior)",
            "summary": c["summary"],
            "kind": "observation",
            "tier": "anomaly" if is_anom else "routine",
            "status": "actual",
            "msg_type": "new",
            "human_review": "none",
            "us_person_data": "none",
            "status_class": "reported",
            "product_category": "current",
            "data_as_of": generated,
            "published_at": generated,
            "valid_until": valid_until,
            "countries": [],
            "pmesii_pt": ["economic"],
            "ascope": ["events"],
            "ie_aspect": ["informational"],
            "ncf": ["provide_food_products", "provide_agricultural_products", "maintain_supply_chains"],
            "requirement_ids": ["HW-PIR-3"],
            "method_version": METHOD,
            "coverage_fraction": 0.95,
            "precision_class": "none",
            "measures": {"index_value": c["current_value"], "mom_pct": c["mom_pct"]},
            "visual": {"type": "page", "url": c["url"]},
            "sources": [
                {**SRC_FAO, "accessed_at": generated},
                {**SRC_IGC, "accessed_at": generated},
            ],
        }
        if is_anom:
            props.update({
                "baseline_ref": "prior-month-benchmark-value",
                "indicator_id": "HW-IND-3",
                "hypothesis_id": "HW-H-1B",
                "direction": "supports",
                "indicator_state": "present",
            })
        features.append({"type": "Feature", "geometry": None, "properties": props})

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "headwind",
        "generated_at": generated,
        "licence": "US public domain (OFAC, Federal Register); CC BY-NC-SA 3.0 IGO (FAO); Headwind code MIT",
        "attribution": "Headwind, The Intelligence Company (OFAC, Federal Register, FAO, IGC)",
        "language_key": LANGUAGE_KEY,
        "features": features,
    }
