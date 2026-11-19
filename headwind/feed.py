"""Build Headwind's contract-v2 feed (tic-feed/2, GeoJSON) from the collected snapshot.

Every item from the live lanes (exchange rates, energy, FAO indices, local food prices) is a
measurement: kind "observation", tier "routine" or "anomaly". Headwind states no probability.
Sanctions-list changes and Federal Register rules are also measurements: counts of what changed on
an official list, and what an agency published. No item carries a judgment.
"""
from __future__ import annotations

import calendar
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, geo  # noqa: E402

from . import batches, controls, food, inspection, markets, pinksheet, scotus, stats, tariffs, uksc, unpress  # noqa: E402

SITE = "https://headwind.theintelligence.company"
METHOD = "headwind-1.10"
DELTA_DAYS = 7       # a list change stays in the feed this long after Headwind saw it
RULE_DAYS = 14       # a Federal Register document stays in the feed this long after publication
LANGUAGE_KEY = "https://github.com/metacog-osint/tic-doctrine/blob/main/docs/language-key.md"
# HW-WP-2 (doctrine/indicators.json) is about the countries in config/wfp_countries.json.
WATCHED = frozenset(json.loads((ROOT / "config" / "wfp_countries.json").read_text(encoding="utf-8"))["countries"])

SRC_OFAC = {
    "id": "ofac-sdn",
    "publisher": "US Department of the Treasury (OFAC)",
    "title": "Specially Designated Nationals and Blocked Persons List (SDN)",
    "url": "https://ofac.treasury.gov/recent-actions",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-treasury-ofac",
    "source_type": "official or market data",
    "descriptor": "The official list of persons, entities, vessels and aircraft blocked by the US Treasury.",
}

SRC_UN = {
    "id": "un-sc-consolidated",
    "publisher": "United Nations Security Council",
    "title": "United Nations Security Council Consolidated List",
    "url": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
    "licence": "UN website terms of use (personal, non-commercial use; no redistribution). Headwind publishes counts only",
    "grade": "A1",
    "independence_group": "un-security-council",
    "source_type": "official or market data",
    "descriptor": "Individuals and entities under sanctions measures imposed by the Security Council.",
}

SRC_EU = {
    "id": "eu-fsf",
    "publisher": "European Commission (Financial Sanctions Files)",
    "title": "Consolidated list of persons, groups and entities subject to EU financial sanctions",
    "url": "https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions",
    "licence": "European Commission reuse notice (Decision 2011/833/EU), reuse with acknowledgement",
    "grade": "A1",
    "independence_group": "eu-commission-fsf",
    "source_type": "official or market data",
    "descriptor": "Persons, groups and entities under EU financial sanctions, as the Commission consolidates them.",
}

SRC_UK = {
    "id": "uk-sanctions-list",
    "publisher": "UK Foreign, Commonwealth and Development Office",
    "title": "UK Sanctions List",
    "url": "https://www.gov.uk/government/publications/the-uk-sanctions-list",
    "licence": "Open Government Licence v3.0",
    "grade": "A1",
    "independence_group": "uk-fcdo-sanctions",
    "source_type": "official or market data",
    "descriptor": "Every person, entity and ship designated under UK sanctions regulations.",
}

SRC_FRANCE = {
    "id": "dgtresor-gels",
    "publisher": "French Treasury (Direction générale du Trésor)",
    "title": "Registre national des gels (France's national asset-freeze register)",
    "url": "https://gels-avoirs.dgtresor.gouv.fr/",
    "licence": "Licence Ouverte / Open Licence 2.0",
    "grade": "A1",
    "independence_group": "fr-dgtresor-gels",
    "source_type": "official or market data",
    "descriptor": ("Every person, entity and ship whose assets are frozen in France: France's own national freezes and "
                   "the EU and UN measures it applies."),
}

SRC_CANADA = {
    "id": "gac-sema",
    "publisher": "Global Affairs Canada",
    "title": "Consolidated Canadian Autonomous Sanctions List",
    "url": ("https://www.international.gc.ca/world-monde/international_relations-relations_internationales/"
            "sanctions/consolidated-consolide.aspx?lang=eng"),
    "licence": "Canada.ca terms: reproduction allowed for non-commercial purposes",
    "grade": "A1",
    "independence_group": "ca-gac-sanctions",
    "source_type": "official or market data",
    "descriptor": "Every person, entity and ship listed under Canada's autonomous sanctions regulations.",
}

SRC_AUSTRALIA = {
    "id": "dfat-consolidated",
    "publisher": "Australian Department of Foreign Affairs and Trade (Australian Sanctions Office)",
    "title": "Australian Sanctions Consolidated List",
    "url": "https://www.dfat.gov.au/international-relations/security/sanctions/consolidated-list",
    "licence": ("Creative Commons Attribution 4.0 International (DFAT's copyright page, read 19 Nov 2026). Source: "
                "Department of Foreign Affairs and Trade website – www.dfat.gov.au"),
    "grade": "A1",
    "independence_group": "au-dfat-sanctions",
    "source_type": "official or market data",
    "descriptor": ("Every person, entity and ship under Australian sanctions laws: Australia's own designations and "
                   "the UN Security Council listings it applies."),
}

SRC_UNPRESS = {
    "id": "un-press",
    "publisher": "United Nations (Meetings Coverage and Press Releases)",
    "title": "UN Meetings Coverage and Press Releases",
    "url": "https://press.un.org/en",
    "licence": "UN website terms of use (personal, non-commercial use; no redistribution). Headwind gives the "
               "document number, date and link only",
    "grade": "A1",
    "independence_group": "un-security-council",
    "source_type": "official or market data",
    "descriptor": "The UN's own press releases, among them those of the Security Council's sanctions committees.",
}

SRC_SCOTUS = {
    "id": "supremecourt-gov",
    "publisher": "Supreme Court of the United States",
    "title": "Opinions of the Court (slip opinions) and docket",
    "url": "https://www.supremecourt.gov/opinions/opinions.aspx",
    "licence": "US government work (17 USC 105, stated from memory; the Court's site gives no reuse statement)",
    "grade": "A1",
    "independence_group": "us-supreme-court",
    "source_type": "official or market data",
    "descriptor": "The Court's own opinions and dockets, as it publishes them.",
}

OGL = "Contains public sector information licensed under the Open Government Licence v3.0."

SRC_UKSC = {
    "id": "supremecourt-uk",
    "publisher": "The Supreme Court of the United Kingdom",
    "title": "Decided cases: case pages and judgments",
    "url": uksc.CASES_PAGE,
    "licence": "Crown copyright, Open Government Licence v3.0 (the Court's terms and conditions, read 18 Nov 2026: "
               "reuse \"provided it is reproduced accurately and not in a misleading context\"). " + OGL,
    "grade": "A1",
    "independence_group": "uk-supreme-court",
    "source_type": "official or market data",
    "descriptor": "The Court's own case pages and judgments, as it publishes them.",
}

LIST_SOURCE = {"ofac-sdn": SRC_OFAC, "un-consolidated": SRC_UN, "eu-fsf": SRC_EU, "uk-sanctions": SRC_UK,
               "france-gels": SRC_FRANCE, "canada-sema": SRC_CANADA, "australia-dfat": SRC_AUSTRALIA}

SRC_CSL = {
    "id": "trade-gov-csl",
    "publisher": "US International Trade Administration (trade.gov)",
    "title": "Consolidated Screening List",
    "url": "https://www.trade.gov/consolidated-screening-list",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-trade-gov-csl",
    "source_type": "official or market data",
    "descriptor": "The export-control and sanctions lists of the US Commerce, State and Treasury departments in one file.",
}

SRC_FR = {
    "id": "us-federal-register",
    "publisher": "US Federal Register (BIS, OFAC, USTR, ITA, presidential documents)",
    "title": "Federal Register documents",
    "url": "https://www.federalregister.gov/api/v1/documents.json",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-federal-register",
    "source_type": "official or market data",
    "descriptor": "Rules, proposed rules, notices and presidential documents as published in the official journal.",
}

SRC_USITC = {
    "id": "usitc-hts",
    "publisher": "US International Trade Commission",
    "title": "Harmonized Tariff Schedule release list",
    "url": tariffs.HTS_PAGE,
    "licence": "US government work (public domain under 17 USC 105, stated from memory; USITC's legal notice could not be read on 15 Nov 2026)",
    "grade": "A1",
    "independence_group": "usitc",
    "source_type": "official or market data",
    "descriptor": "Each revision of the US tariff schedule: when it was posted and when it took effect.",
}

SRC_PI = {
    "id": "fr-public-inspection",
    "publisher": "Office of the Federal Register (public inspection)",
    "title": "Federal Register public inspection",
    "url": inspection.PI_PAGE,
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-federal-register",
    "source_type": "official or market data",
    "descriptor": "Documents filed with the Office of the Federal Register and open to the public before they are published.",
}

SRC_FAO = {
    "id": "fao-ffpi",
    "publisher": "FAO",
    "title": "FAO Food Price Index (FFPI)",
    "url": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
    "licence": "CC BY 4.0 (FAO database terms of use)",
    "grade": "A1",
    "independence_group": "fao",
    "source_type": "official or market data",
    "descriptor": "Monthly global food commodity price index across cereals, vegetable oils, dairy, meat, and sugar.",
}

SRC_PINKSHEET = {
    "id": "worldbank-pinksheet",
    "publisher": "World Bank (Commodity Price Data, the Pink Sheet)",
    "title": "World Bank Commodity Price Data (The Pink Sheet), monthly prices in nominal US dollars",
    "url": "https://www.worldbank.org/en/research/commodity-markets",
    "licence": "CC BY 4.0 (World Bank data catalog, dataset 0038238)",
    "grade": "A2",
    "independence_group": "world-bank",
    "source_type": "official or market data",
    "descriptor": "Monthly average prices of fertilizers and metals compiled by the World Bank from exchanges and "
                  "market reporters.",
}

PINK_NCF = {"fertilizer": ["provide_agricultural_products", "produce_chemicals"],
            "metal": ["provide_metals_materials", "maintain_supply_chains"]}

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

SRC_GEM = {
    "id": "worldbank-gem",
    "publisher": "World Bank (Global Economic Monitor)",
    "title": "Official exchange rate, local currency per US dollar, monthly average (DPANUSSPB)",
    "url": "https://databank.worldbank.org/source/global-economic-monitor-(gem)",
    "licence": "CC BY 4.0",
    "grade": "A2",
    "independence_group": "world-bank",
    "source_type": "official or market data",
    "descriptor": "Monthly average official exchange rates compiled by the World Bank from national sources.",
}

SRC_EIA = {
    "id": "eia-spot",
    "publisher": "US Energy Information Administration",
    "title": "Crude oil and natural gas daily spot prices",
    "url": "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm",
    "licence": "US public domain (EIA); EIA asks to be credited as the source",
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


FOOD_RULES = {"z": "|z| >= 3.5", "rank": "a rise in the top 5% of its own history",
              "run": "risen six or more months in a row"}


def _rules_text(x: dict) -> str:
    """" Flagged by ..." for a food reading, naming the rules that fired (headwind-1.10), else ""."""
    rules = [FOOD_RULES[r] for r in x.get("rules") or [] if r in FOOD_RULES]
    if not rules:
        return ""
    run = f" ({x['rise_run']} rises in a row)" if "run" in (x.get("rules") or []) else ""
    return f" Flagged by {' and '.join(rules)}{run}."


def _month_end_by(period: str, generated: str, published: str | None = None) -> str:
    """The month's end. For a month still under way, the publisher's last update (`published`, such as HDX's
    last_modified, read as UTC) when it falls in that month and before this run, so the reading's date does not move
    from run to run (18 Nov 2026: it was the collection time, and each run logged a change); else the collection
    time. Never dated in the future."""
    end = _month_end(period)
    if end <= generated:
        return end
    p = f"{published[:19]}Z" if published and len(published) >= 19 else None
    if p and p[:7] >= period[:7] and p <= generated:
        return p
    return generated


def _z_text(z) -> str:
    return "no baseline yet" if z is None else f"z {z:+.1f}"


def _observation(item_id: str, title: str, summary: str, *, anomaly: bool, data_as_of: str, generated: str,
                 valid_until: str, countries: list[str], ncf: list[str], requirement_ids: list[str],
                 measures: dict, anchor: str, source: dict, indicator_id: str, baseline_ref: str,
                 coverage: float, lane_accessed: str | None, ascope: list[str],
                 hypothesis_id: str | None = None) -> dict:
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
        # The kit's form (feed-contract-v2: id, window, type, version). The id names the lane's own rule, from
        # the item id ("headwind:fxmarket:SD" -> "headwind-fxmarket"); every series rule is rolling.
        props["baseline_ref"] = {"id": f"headwind-{item_id.split(':')[1]}", "type": "rolling", "version": METHOD,
                                 "window": baseline_ref.removeprefix("rolling: ")}
        if hypothesis_id:
            # HW-WP-2: an anomaly for a watched country (or an energy benchmark) is its indicator present. The
            # direction is the register's: each indicator is emerging under the hypothesis named here.
            # HW-IND-6 (local food) is emerging under HW-H-2A and HW-H-2B alike, so it tells neither apart: it is
            # present but neutral. Which hypothesis holds is an analyst's reading of the indicators together.
            props.update({"indicator_id": indicator_id, "hypothesis_id": hypothesis_id,
                          "direction": "neutral" if indicator_id in NON_DIAGNOSTIC else "supports",
                          "indicator_state": "present"})
    geom = None
    if len(countries) == 1:
        pt = geo.point(countries[0])
        if pt:
            geom = {"type": "Point", "coordinates": [pt[1], pt[0]]}
    if geom is None:
        props["precision_class"] = "none" if not countries else "country"
    return {"type": "Feature", "geometry": geom, "properties": props}


def _counts(d: dict, limit: int = 6) -> str:
    items = list(d.items())
    text = ", ".join(f"{k} {v}" for k, v in items[:limit])
    return text + (f", and {len(items) - limit} more" if len(items) > limit else "")


def _point(countries: list[str]):
    if len(countries) == 1:
        pt = geo.point(countries[0])
        if pt:
            return {"type": "Point", "coordinates": [pt[1], pt[0]]}
    return None


def _official(item_id: str, title: str, summary: str, *, data_as_of: str, generated: str, valid_until: str,
              countries: list[str], pmesii: list[str], ascope: list[str], ncf: list[str], requirement_ids: list[str],
              measures: dict, visual: dict, source: dict, accessed: str | None, extra: dict | None = None,
              anomaly_ref: dict | None = None) -> dict:
    geom = _point(countries)
    tier = {"tier": "anomaly", "baseline_ref": anomaly_ref} if anomaly_ref else {}
    return {"type": "Feature", "geometry": geom, "properties": {**(extra or {}),
        "contract": CONTRACT, "id": item_id, "program": "headwind", "title": title, "summary": summary,
        "kind": "observation", "tier": "routine", "status": "actual", "msg_type": "new", "human_review": "none",
        "us_person_data": "none", "status_class": "reported", "product_category": "current",
        "data_as_of": data_as_of, "published_at": generated, "valid_until": valid_until, "countries": countries,
        "pmesii_pt": pmesii, "ascope": ascope, "ie_aspect": ["informational"], "ncf": ncf,
        "requirement_ids": requirement_ids, "method_version": METHOD, "coverage_fraction": 1.0,
        "precision_class": "country" if geom else "none", "measures": measures, "visual": visual,
        "sources": [{**source, "accessed_at": accessed or generated}], **tier,
    }}


def _batch_measures(s: dict) -> dict:
    """The largest batch, the highest z, and that batch's flag_rate (how often the list's own earlier batches
    would have tripped the same rule)."""
    b = s.get("batches") or []
    scored = [x for x in b if x.get("z") is not None]
    top = max(scored, key=lambda x: x["z"], default=None)
    return {"batch_size_max": max((x["size"] for x in b), default=0), "batch_z_max": top["z"] if top else None,
            "flag_rate": top.get("flag_rate") if top else None}


def _batch_ref(s: dict) -> dict | None:
    """A list change is an anomaly only when one of its designation batches is (headwind/batches.py)."""
    if not s.get("anomaly"):
        return None
    basis = {x["basis"] for x in s.get("batches") or [] if x.get("anomaly")}
    dated = "designation date" in basis
    what = ("the list's own " + str(batches.BATCH_WINDOW) + " earlier designation dates, by size" if dated else
            "the earlier changes Headwind saw on the list, up to " + str(batches.BATCH_WINDOW) + ", by size")
    return {"id": "headwind-designation-batch" if dated else "headwind-observed-additions", "type": "rolling",
            "version": METHOD,
            "window": f"{what}; anomaly at z >= {stats.Z_ANOMALY:g} on the logarithm of the batch size and at least "
                      f"{batches.BATCH_FLOOR} entries"}


VESSELS_IN_TEXT = 25
ALSO_ON = {"ofac-sdn": "the OFAC SDN list", "uk-sanctions": "the UK Sanctions List",
           "france-gels": "France's asset-freeze register", "canada-sema": "Canada's consolidated list",
           "australia-dfat": "Australia's consolidated list"}


def _vessel_text(word: str, vessels: list[dict]) -> str:
    """Vessels as the list gives them (OFAC, UK): name, IMO number and flag. Vessels are not persons."""
    if not vessels:
        return ""
    def one(v):
        bits = ["alias" if v.get("name_is_alias") else "",
                f"IMO {v['imo']}" if v.get("imo") else "no IMO number given", f"flag {v['flag']}" if v.get("flag") else "",
                "also on " + " and ".join(ALSO_ON.get(l, l) for l in v["also_on"]) if v.get("also_on") else ""]
        return f"{v.get('name') or 'unnamed'} ({', '.join(b for b in bits if b)})"
    more = len(vessels) - VESSELS_IN_TEXT
    tail = f"; and {more} more on the page" if more > 0 else ""
    return f" Vessels {word}: {'; '.join(one(v) for v in vessels[:VESSELS_IN_TEXT])}{tail}."


def _rekeyed_text(vessels: list[dict]) -> str:
    """Vessels that went and came back under a new entry id with the same IMO number: one entry, still listed."""
    if not vessels:
        return ""
    rows = [f"{v.get('name') or 'unnamed'} (IMO {v['imo']}, {v['old_id']} to {v['list_id']})"
            for v in vessels[:VESSELS_IN_TEXT]]
    more = len(vessels) - VESSELS_IN_TEXT
    tail = f"; and {more} more on the page" if more > 0 else ""
    return (f" Vessels removed and listed again under a new entry id with the same IMO number, counted as the same "
            f"entry and not as removed and added ({len(vessels)}): {'; '.join(rows)}{tail}.")


# HW-IND-1 and HW-IND-7 (doctrine/indicators.json, register 1.4, Tom's yes 18 Nov 2026), measured on each list change.
IND1_SHIPS = 3          # an OFAC change that adds this many ships with IMO numbers meets HW-IND-1
IND7_SHARE = 0.5        # renamed, re-keyed or renumbered entries above this share of a change meet HW-IND-7


def list_indicator(s: dict) -> tuple[dict, dict]:
    """(measures, indicator properties) for one sanctions or screening list change. A rename is a person or
    organization whose name changed, or a vessel whose name changed; a re-keyed entry came back under a new id
    (same IMO number, or same name and type); a renumbered one only moved on Canada's list. OFAC changes always
    carry HW-IND-1 (present, or absent and neutral); any other change carries HW-IND-7 only when it is met."""
    renamed = (s.get("renamed") or 0) + sum(1 for v in s.get("vessels_changed") or [] if "name" in (v.get("changed") or {}))
    moved_ids = (s.get("rekeyed") or 0) + (s.get("renumbered") or 0)
    vessel_only = s.get("vessel_details_only", len(s.get("vessels_changed") or []))
    touched = s.get("added", 0) + s.get("removed", 0) + s.get("changed", 0) + vessel_only + moved_ids
    share = round((renamed + moved_ids) / touched, 3) if touched else 0.0
    measures = {"renamed_or_rekeyed": renamed + moved_ids, "rename_share": share}
    ofac = s.get("list") == "ofac-sdn"
    if ofac:
        ships = sum(1 for v in s.get("vessels_added") or [] if v.get("imo"))
        measures["vessels_added_with_imo"] = ships
        if ships >= IND1_SHIPS:
            return measures, {"indicator_id": "HW-IND-1", "hypothesis_id": "HW-H-1A", "direction": "supports",
                              "indicator_state": "present"}
    if share > IND7_SHARE:
        return measures, {"indicator_id": "HW-IND-7", "hypothesis_id": "HW-H-1C", "direction": "supports",
                          "indicator_state": "present"}
    if ofac:
        return measures, {"indicator_id": "HW-IND-1", "hypothesis_id": "HW-H-1A", "direction": "neutral",
                          "indicator_state": "absent"}
    return measures, {}


def _tag_list_change(props: dict, s: dict) -> None:
    measures, tags = list_indicator(s)
    props["measures"].update(measures)
    props.update(tags)


def _changed_title(s: dict) -> str:
    return (f", {s['changed']} changed" if s.get("changed") else "") + \
        (f", {s['rekeyed']} under a new id" if s.get("rekeyed") else "")


def _edit_text(s: dict) -> str:
    """Entries that stayed on the list and changed: counts, and the programs gained and lost across them."""
    if not s.get("changed"):
        return ""
    bits = [f"Changed {s['changed']} that stayed on the list"]
    if s.get("changed_by_type"):
        bits.append(f"by type, {_counts(s['changed_by_type'])}")
    if s.get("programs_gained"):
        bits.append(f"programs gained, {_counts(s['programs_gained'])}")
    if s.get("programs_lost"):
        bits.append(f"programs lost, {_counts(s['programs_lost'])}")
    if s.get("retyped"):
        bits.append(f"type changed, {_counts(s['retyped'])}")
    return "; ".join(bits) + "."


# Lists split into the publisher's own measures and its restatements (sanctions.OWN_ENTRY): the word for the own
# ones, the measures restated, and the lists Headwind reads them on.
SPLIT_WORDS = {
    "france-gels": ("national", "national freezes", "EU and UN measures", "the EU's and the UN Security Council's own lists"),
    "australia-dfat": ("Australian", "Australian designations", "UN Security Council listings",
                       "the UN Security Council's own list"),
}


def _restated_text(rest: dict, list_id: str = "france-gels") -> str:
    """The entries that restate measures Headwind reads on other lists (France's EU and UN entries, Australia's UN
    entries): one count line, never scored."""
    _, _, what, where = SPLIT_WORDS[list_id]
    if not (rest["added"] or rest["removed"] or rest["changed"]):
        return f"No change among the entries that restate {what}."
    # Australia's UN entries carry no name (the UN's terms); France's restated entries are named as France prints them.
    named = ", never named" if list_id == "australia-dfat" else ""
    return (f"Entries restating {what}, which Headwind also reads on {where}, so they are counted here but not "
            f"scored{named} and place no country: {rest['added']} added, {rest['removed']} removed, "
            f"{rest['changed']} changed.")


def _renamed_text(vessels: list[dict], limit: int = 25) -> str:
    """Vessels that stayed listed and changed a public detail (name, IMO, MMSI, flag or type): before and after."""
    if not vessels:
        return ""
    rows = []
    for v in vessels[:limit]:
        moves = ", ".join(f"{f} {a or 'none'} to {b or 'none'}" for f, (a, b) in v["changed"].items())
        rows.append(f"{v.get('name') or 'unnamed'}" + (f" (IMO {v['imo']})" if v.get("imo") else "") + f": {moves}")
    more = f" and {len(vessels) - limit} more" if len(vessels) > limit else ""
    return f" Vessels still listed whose details changed ({len(vessels)}): {'; '.join(rows)}{more}."


NAMES_IN_TEXT = 25
NAMES_NOTE = ("Names as the publisher prints them, with type, programs and the countries of the entry's addresses and "
              "nationality; birth dates, identity documents, street addresses and reasons are not carried. To report an "
              "error, or to ask that the name of someone no longer listed be taken down: support@theintelligence.company.")


def _who(r: dict) -> str:
    bits = [r.get("type") or "", "; ".join(r.get("programs") or [])]
    return f"{r['name']} ({', '.join(b for b in bits if b)})"


def _names_text(s: dict, un: bool = False) -> str:
    """People and organizations a change names (headwind-1.9): those added and those that changed, then
    organizations removed, up to NAMES_IN_TEXT; the rest are on the page and in data/list-changes.json. Individuals
    removed are counted here and named on the page only, which keeps them for 30 days: the feed's text goes into
    the history log for good, and a person no longer listed should not stay named there."""
    if un:
        return (" People and organizations on the UN list are counts only (the UN's terms of use bar redistributing "
                "its content); their names are on the UN's list.")
    added, changed = s.get("named_added") or [], s.get("named_changed") or []
    removed = s.get("named_removed") or []
    orgs_removed = [r for r in removed if r.get("type") != "individual"]
    people_removed = len(removed) - len(orgs_removed)
    rows: list[tuple[str, str]] = []
    rows += [("Added", _who(r) + (f", listed {r['listed']}" if r.get("listed") else "")) for r in added]
    for r in changed:
        what = []
        if r.get("name_before"):
            what.append(f"was {r['name_before']}")
        if r.get("type_before"):
            what.append(f"was a{'n' if r['type_before'][:1] in 'aeiou' else ''} {r['type_before']}")
        if r.get("gained"):
            what.append("programs gained " + ", ".join(r["gained"]))
        if r.get("lost"):
            what.append("programs lost " + ", ".join(r["lost"]))
        if r.get("countries_before") is not None:
            what.append("address countries were " + (", ".join(r["countries_before"]) or "none"))
        rows.append(("Changed", f"{r['name']} ({r.get('type')}; {'; '.join(what) or 'details changed'})"))
    rows += [("Removed, no longer on the list", _who(r)) for r in orgs_removed]
    out, last = [], None
    for word, text in rows[:NAMES_IN_TEXT]:
        out.append(("; " if word == last else (". " if out else " ") + f"{word}: ") + text)
        last = word
    more = len(rows) - NAMES_IN_TEXT
    text = ("".join(out) + "." if out else "") + (f" And {more} more named on the page." if more > 0 else "")
    if people_removed:
        text += (f" {people_removed} individual{'s' if people_removed != 1 else ''} removed, no longer on the list: "
                 f"named on the page for 30 days, not here.")
    if s.get("unnamed_removed"):
        text += (f" {s['unnamed_removed']} removed from a reading kept before names were carried: counted only.")
    return text + " " + NAMES_NOTE


def _named_count(s: dict) -> int:
    return len(s.get("named_added") or []) + len(s.get("named_changed") or []) + len(s.get("named_removed") or [])


def list_features(snapshot: dict) -> list[dict]:
    """Sanctions-list changes and Federal Register rules. Counts and published facts; tier routine."""
    generated = snapshot["generated_at"]
    valid_until = _plus_hours(generated, 48)
    lanes = snapshot.get("lanes") or {}
    feats = []

    cutoff = _plus_hours(generated, -24 * DELTA_DAYS)
    for s in snapshot.get("sanctions") or []:
        if s["detected_at"] < cutoff:
            continue
        nat, rest = s.get("national"), s.get("restated")
        base = nat if nat is not None else s
        own, own_plural, restated_what, _ = SPLIT_WORDS.get(s["list"], ("national", "national freezes", "", ""))
        parts = []
        if base["added"]:
            parts.append(f"Added {base['added']}{' ' + own if nat is not None else ''}: by type, "
                         f"{_counts(base['added_by_type'])}; by program, {_counts(base['added_by_program'])}.")
        if base["removed"]:
            parts.append(f"Removed {base['removed']}{' ' + own if nat is not None else ''}: by type, "
                         f"{_counts(base['removed_by_type'])}; by program, {_counts(base['removed_by_program'])}.")
        parts.append(_edit_text(base))
        if s.get("renumbered"):
            parts.append(f"{s['renumbered']} entries only changed their item number on the list and are counted as "
                         f"the same entries, not as removed and added.")
        if nat is not None:
            parts.append(_restated_text(rest, s["list"]))
        since = f" since Headwind's reading of {s['prior_checked_at'][:10]}" if s.get("prior_checked_at") else ""
        title = (f"{s['list_name']}: {s['added']} added, {s['removed']} removed{_changed_title(s)}" if nat is None else
                 f"{s['list_name']}: {nat['added']} {own_plural} added, {nat['removed']} removed"
                 f"{', ' + str(nat['changed']) + ' changed' if nat.get('changed') else ''}; {rest['added']} added and "
                 f"{rest['removed']} removed restating {restated_what}")
        feats.append(_official(
            f"headwind:sanctions:{s['id']}",
            title,
            f"{' '.join(x for x in parts if x)} The list now holds {s['total']} entries. This is the difference between two of "
            f"Headwind's readings{since}, seen on {s['detected_at'][:10]}; the dates of the designations are in "
            f"the publisher's own notices.{_vessel_text('added', s.get('vessels_added') or [])}"
            f"{_vessel_text('removed', s.get('vessels_removed') or [])}{_rekeyed_text(s.get('vessels_rekeyed') or [])}"
            f"{_renamed_text(s.get('vessels_changed') or [])}{batches.text(s.get('batches') or [])}"
            f"{_names_text(s, s['list'] == 'un-consolidated')}",
            data_as_of=s["detected_at"], generated=generated, valid_until=valid_until, countries=s["countries"],
            pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "provide_funding_liquidity"], requirement_ids=["HW-PIR-1"],
            measures={"added": s["added"], "removed": s["removed"], "total": s["total"],
                      "changed": s.get("changed", 0), "vessels_added": s["added_by_type"].get("vessel", 0),
                      "vessels_changed": len(s.get("vessels_changed") or []), "rekeyed": s.get("rekeyed", 0),
                      **({"national_added": nat["added"], "national_removed": nat["removed"],
                          "restated_added": rest["added"], "restated_removed": rest["removed"]} if nat is not None else {}),
                      "named": _named_count(s), **_batch_measures(s)},
            visual={"type": "page", "url": f"{SITE}/#sanctions"},
            source=LIST_SOURCE[s["list"]],
            accessed=(lanes.get("sanctions") or {}).get("fetched_at"), anomaly_ref=_batch_ref(s)))
        feats[-1]["properties"]["us_person_data"] = s.get("us_person_data") or "none"
        _tag_list_change(feats[-1]["properties"], s)

    for s in snapshot.get("screening") or []:
        if s["detected_at"] < cutoff:
            continue
        parts = []
        for word, key in (("Added", "added"), ("Removed", "removed")):
            if s[key]:
                by_prog = s[key + "_by_program"]
                prog = f"; by program, {_counts(by_prog)}" if by_prog else ""
                parts.append(f"{word} {s[key]}: by address country, {_counts(s[key + '_by_country'])}{prog}.")
        parts.append(_edit_text(s))
        if s.get("rekeyed"):
            parts.append(f"{s['rekeyed']} {'entry' if s['rekeyed'] == 1 else 'entries'} came back under a new id with "
                         f"the same name and type, counted as the same entry and not as removed and added.")
        since = f" since Headwind's reading of {s['prior_checked_at'][:10]}" if s.get("prior_checked_at") else ""
        feats.append(_official(
            f"headwind:screening:{s['id']}",
            f"{s['list_name']} ({s['publisher']}): {s['added']} added, {s['removed']} removed{_changed_title(s)}",
            f"{' '.join(x for x in parts if x)} The list now holds {s['total']} entries. This is the difference between two of "
            f"Headwind's readings of the Consolidated Screening List{since}, seen on {s['detected_at'][:10]}; the "
            f"dates of the listings are in the publisher's own notices.{batches.text(s.get('batches') or [])}"
            f"{_names_text(s)}",
            data_as_of=s["detected_at"], generated=generated, valid_until=valid_until, countries=s["countries"],
            pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "manufacture_equipment"], requirement_ids=["HW-PIR-1"],
            measures={"added": s["added"], "removed": s["removed"], "total": s["total"],
                      "changed": s.get("changed", 0), "rekeyed": s.get("rekeyed", 0), "named": _named_count(s),
                      **_batch_measures(s)},
            visual={"type": "page", "url": f"{SITE}/#screening"},
            source={**SRC_CSL, "url": s.get("url") or SRC_CSL["url"]},
            accessed=(lanes.get("screening") or {}).get("fetched_at"), anomaly_ref=_batch_ref(s)))
        feats[-1]["properties"]["us_person_data"] = s.get("us_person_data") or "none"
        _tag_list_change(feats[-1]["properties"], s)

    for r in controls.recent(snapshot.get("controls") or [], generated, RULE_DAYS):
        if r["agency"] == "President":
            feats.append(_presidential_feature(r, generated, valid_until, (lanes.get("controls") or {}).get("fetched_at")))
            continue
        dates = []
        if r.get("effective_on"):
            dates.append(f"Effective {r['effective_on']}.")
        if r.get("comments_close_on"):
            dates.append(f"Comments close {r['comments_close_on']}.")
        if r.get("named_dates"):
            dates.append(f"Later dates named in its DATES paragraph: {', '.join(r['named_dates'])}.")
        kind = _doc_kind(r["type"])
        feats.append(_official(
            f"headwind:control:{r['id']}",
            f"{r['agency']} {kind} ({r['published_date']}): {r['title']}",
            " ".join(x for x in [f"Action: {r['action']}" if r.get("action") else "", r.get("abstract") or "",
                                 *dates, f"Federal Register document {r['id']}."] if x),
            data_as_of=f"{r['published_date']}T00:00:00Z", generated=generated, valid_until=valid_until,
            countries=r.get("countries") or [], pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "manufacture_equipment"], requirement_ids=["HW-PIR-2"],
            measures={"named_dates": len(r.get("named_dates") or [])},
            visual={"type": "page", "url": r["url"]}, source={**SRC_FR, "url": r["url"]},
            accessed=(lanes.get("controls") or {}).get("fetched_at")))

    feats += inspection_features(snapshot, generated, valid_until, (lanes.get("inspection") or {}).get("fetched_at"))
    feats += tariff_features(snapshot, generated, valid_until)
    feats += unpress_features(snapshot, generated, valid_until)
    feats += scotus_features(snapshot, generated, valid_until)
    feats += uksc_features(snapshot, generated, valid_until)
    return feats


def _presidential_feature(r: dict, generated: str, valid_until: str, accessed: str | None) -> dict:
    """A tariff action in the Federal Register's presidential documents: its own title, subtype, number, signing
    date and the dates its text sets. Published facts; tier routine."""
    kind = (r.get("action") or "presidential document").lower()
    parts = [f"{r.get('action') or 'Presidential document'}" + (f" {r['number']}" if r.get("number") else "")
             + (f", signed {r['signing_date']}" if r.get("signing_date") else "")
             + f", published in the Federal Register {r['published_date']}."]
    if r.get("abstract"):
        parts.append(r["abstract"])
    if r.get("named_dates"):
        parts.append(f"Dates its text sets (12:01 a.m. on): {', '.join(r['named_dates'])}.")
    if r.get("computed_dates"):
        parts.append(f"Counted from its signing date (\"within N days of the date of this proclamation\"): "
                     f"{', '.join(r['computed_dates'])}.")
    if r.get("text_error"):
        parts.append("Its text could not be read this run, so the dates it sets are not listed.")
    parts.append(f"Federal Register document {r['id']}.")
    return _official(
        f"headwind:control:{r['id']}", f"President, {kind} ({r['published_date']}): {r['title']}", " ".join(parts),
        data_as_of=f"{r['published_date']}T00:00:00Z", generated=generated, valid_until=valid_until,
        countries=r.get("countries") or [], pmesii=["economic", "political"], ascope=["organizations"],
        ncf=["maintain_supply_chains", "manufacture_equipment"], requirement_ids=["HW-PIR-2"],
        measures={"named_dates": len(r.get("named_dates") or []), "computed_dates": len(r.get("computed_dates") or [])},
        visual={"type": "page", "url": r["url"]}, source={**SRC_FR, "url": r["url"]}, accessed=accessed)


def _pace_ref(p: dict, what: str) -> dict | None:
    if not p.get("anomaly"):
        return None
    return {"id": f"headwind-{what}-pace", "type": "rolling", "version": METHOD,
            "window": f"{p['window_days']}-day count against the {p['baseline_windows']} {p['window_days']}-day "
                      f"windows before it, |z| >= {stats.Z_ANOMALY} and at least {what_floor(what)}"}


def what_floor(what: str) -> str:
    return {"tariff": f"{controls.PACE_FLOOR} documents", "hts": f"{tariffs.HTS_FLOOR} revisions"}[what]


def _pace_text(p: dict, noun: str) -> str:
    z = f"z {p['z']:+.1f}" if p.get("z") is not None else "no baseline yet"
    return (f"{p['count']} {noun} from {p['from']} to {p['to']}; the median of the {p['baseline_windows']} "
            f"{p['window_days']}-day windows before was {p.get('median')}, {z}"
            + (f", flag rate {p['flag_rate']}" if p.get("flag_rate") is not None else "") + ".")


def scotus_features(snapshot: dict, generated: str, valid_until: str) -> list[dict]:
    """Supreme Court opinions decided in the last two weeks, and new entries on the tariff-authority dockets. The
    Court's own case title and docket number (Tom, 15 Nov 2026); us_person_data from scotus.us_person_data. Nothing
    is summarized: the opinion and the docket are at the links."""
    lanes = snapshot.get("lanes") or {}
    accessed = (lanes.get("scotus") or {}).get("fetched_at")
    cutoff = _plus_hours(generated, -24 * scotus.FEED_DAYS)[:10]
    feats = []
    for o in snapshot.get("scotus_opinions") or []:
        day = o.get("decided") or (o.get("posted") or "")[:10]
        if not day or day < cutoff:
            continue
        who = (f"an opinion of the Court delivered by {o['author']}" if o["kind"] == "signed" and o.get("author")
               else "a per curiam opinion")
        when = f"on {day}" if o.get("decided") else f"(posted {day}; the decision date was not read from the docket)"
        f = _official(
            f"headwind:scotus:{o['docket']}",
            f"Supreme Court of the United States: {o['title']}, No. {o['docket']} ({day})",
            f"The Supreme Court of the United States issued {who} in {o['title']}, No. {o['docket']}, {when}. The "
            f"opinion and the docket are at the links; Headwind does not summarize or characterize them. The case "
            f"title is the Court's own.",
            data_as_of=f"{day}T00:00:00Z", generated=generated, valid_until=valid_until, countries=["US"],
            pmesii=["political"], ascope=["organizations"], ncf=["operate_government"], requirement_ids=["HW-REQ-2"],
            measures={}, visual={"type": "page", "url": o["link"]},
            source={**SRC_SCOTUS, "url": o["link"]}, accessed=accessed)
        f["properties"]["us_person_data"] = o.get("us_person_data") or scotus.us_person_data(o["title"])
        f["properties"]["docket_url"] = o.get("docket_url")
        feats.append(f)
    for t in snapshot.get("scotus_tracked") or []:
        last = t.get("last_entry") or {}
        if not last.get("date") or last["date"] < cutoff:
            continue
        title = f"{t.get('petitioner')} v. {t.get('respondent')}"
        f = _official(
            f"headwind:scotusdocket:{t['docket']}:{last['date']}",
            f"Supreme Court docket No. {t['docket']} (tariff authority): new entry {last['date']}",
            f"A new entry on the Supreme Court's docket No. {t['docket']}, {title}, dated {last['date']}: "
            f"\"{last.get('text', '')[:300]}\" (the Court's docket text). Headwind tracks this docket because the "
            f"case concerns the authority for US tariffs.",
            data_as_of=f"{last['date']}T00:00:00Z", generated=generated, valid_until=valid_until, countries=["US"],
            pmesii=["political", "economic"], ascope=["organizations"], ncf=["operate_government"],
            requirement_ids=["HW-PIR-2"], measures={}, visual={"type": "page", "url": t.get("url")},
            source={**SRC_SCOTUS, "url": t.get("url")}, accessed=accessed)
        f["properties"]["us_person_data"] = "individuals"      # docket text and titles can name people
        feats.append(f)
    return feats


def uksc_features(snapshot: dict, generated: str, valid_until: str) -> list[dict]:
    """UK Supreme Court judgments handed down in the last two weeks: the Court's own case titles, case ids and neutral
    citation (Tom, 15 Nov 2026), the judgment date and the links. One item per judgment; joined appeals decided in
    one judgment are listed together. No judgment text; us_person_data from uksc.us_person_data."""
    lanes = snapshot.get("lanes") or {}
    accessed = (lanes.get("uksc") or {}).get("fetched_at")
    cutoff = _plus_hours(generated, -24 * uksc.FEED_DAYS)[:10]
    feats = []
    for j in snapshot.get("uksc_judgments") or []:
        cases = j.get("cases") or []
        if not cases or (j.get("judgment_date") or "") < cutoff:
            continue
        day, first = j["judgment_date"], cases[0]
        more = f" and {len(cases) - 1} joined case{'s' if len(cases) > 2 else ''}" if len(cases) > 1 else ""
        listed = "; ".join(f"{c['title']} ({c['case_id']})" for c in cases)
        f = _official(
            f"headwind:uksc:{j['year']}-{j['number']}",
            f"UK Supreme Court: {first['title']}{more}, {j['citation']} ({day})",
            f"The Supreme Court of the United Kingdom handed down judgment {j['citation']} on {day} in "
            f"{'the case' if len(cases) == 1 else 'the cases'} {listed}. The judgment and the case "
            f"page{'s are' if len(cases) > 1 else ' is'} at the links; Headwind does not summarize or characterize "
            f"them. The case titles, case ids and neutral citation are the Court's own. {OGL}",
            data_as_of=f"{day}T00:00:00Z", generated=generated, valid_until=valid_until, countries=["GB"],
            pmesii=["political"], ascope=["organizations"], ncf=["operate_government"], requirement_ids=["HW-REQ-2"],
            measures={}, visual={"type": "page", "url": first["url"]},
            source={**SRC_UKSC, "url": j.get("judgment_pdf") or first["url"]}, accessed=accessed)
        f["properties"]["us_person_data"] = j.get("us_person_data") or "individuals"
        f["properties"]["neutral_citation"] = j["citation"]
        f["properties"]["case_urls"] = [c["url"] for c in cases]
        feats.append(f)
    return feats


def unpress_features(snapshot: dict, generated: str, valid_until: str) -> list[dict]:
    """UN Security Council sanctions committee press releases of the last two weeks: document number, date and
    link only (UN terms of use). The release's own words are at the link."""
    lanes = snapshot.get("lanes") or {}
    cutoff = _plus_hours(generated, -24 * unpress.FEED_DAYS)
    feats = []
    for r in snapshot.get("un_committee_releases") or []:
        if r["published"] < cutoff:
            continue
        num = r["id"].split("/", 1)[1].lower()
        feats.append(_official(
            f"headwind:unpress:sc{num}",
            f"UN Security Council sanctions committee press release {r['id']} ({r['published'][:10]})",
            f"The UN published press release {r['id']} on {r['published'][:10]}, from one of the Security Council's "
            f"sanctions committees. Headwind gives the document number, date and link only, under the UN's terms of "
            f"use; the release's own words are at the link. Changes to the UN list itself are reported from the list.",
            data_as_of=r["published"], generated=generated, valid_until=valid_until, countries=[],
            pmesii=["political", "economic"], ascope=["organizations"], ncf=["provide_funding_liquidity"],
            requirement_ids=["HW-PIR-1"], measures={},
            visual={"type": "page", "url": r["url"]}, source={**SRC_UNPRESS, "url": r["url"]},
            accessed=(lanes.get("unpress") or {}).get("fetched_at")))
    return feats


def tariff_features(snapshot: dict, generated: str, valid_until: str) -> list[dict]:
    """The pace of tariff actions and of HTS revisions (counts against their own history), and each HTS revision
    posted in the last two weeks. Counts and published facts."""
    lanes = snapshot.get("lanes") or {}
    feats = []
    tp = snapshot.get("tariff_pace") or {}
    if tp.get("count") is not None:
        feats.append(_official(
            "headwind:tariffpace:presidential",
            f"Tariff actions in the Federal Register's presidential documents: {tp['count']} in {tp['window_days']} days"
            + (" (unusual)" if tp.get("anomaly") else ""),
            _pace_text(tp, "proclamations, executive orders and memoranda whose title is a tariff action, by "
                           "Federal Register publication date,")
            + (f" Documents: {', '.join(tp['ids'])}." if tp.get("ids") else ""),
            data_as_of=f"{tp['to']}T00:00:00Z", generated=generated, valid_until=valid_until, countries=[],
            pmesii=["economic", "political"], ascope=["organizations"], ncf=["maintain_supply_chains"],
            requirement_ids=["HW-PIR-2"],
            measures={"count": tp["count"], "z": tp.get("z"), "baseline_n": tp.get("baseline_n"),
                      "flag_rate": tp.get("flag_rate"), "median": tp.get("median")},
            visual={"type": "page", "url": f"{SITE}/#rules"}, source=SRC_FR,
            accessed=(lanes.get("controls") or {}).get("fetched_at"), anomaly_ref=_pace_ref(tp, "tariff")))
    hp = snapshot.get("hts_pace") or {}
    accessed = (lanes.get("tariffs") or {}).get("fetched_at")
    if hp.get("count") is not None:
        feats.append(_official(
            "headwind:tariffpace:hts",
            f"Harmonized Tariff Schedule revisions: {hp['count']} in {hp['window_days']} days"
            + (" (unusual)" if hp.get("anomaly") else ""),
            _pace_text(hp, "revisions posted by the US International Trade Commission"),
            data_as_of=f"{hp['to']}T00:00:00Z", generated=generated, valid_until=valid_until, countries=["US"],
            pmesii=["economic"], ascope=["organizations"], ncf=["maintain_supply_chains"], requirement_ids=["HW-PIR-2"],
            measures={"count": hp["count"], "z": hp.get("z"), "baseline_n": hp.get("baseline_n"),
                      "flag_rate": hp.get("flag_rate"), "median": hp.get("median")},
            visual={"type": "page", "url": f"{SITE}/#rules"}, source=SRC_USITC, accessed=accessed,
            anomaly_ref=_pace_ref(hp, "hts")))
    for r in tariffs.recent((snapshot.get("hts_releases") or {}).get("revisions") or [], generated):
        feats.append(_official(
            f"headwind:hts:{r['name']}", f"USITC posted {r['title']} of the Harmonized Tariff Schedule ({r['posted']})",
            f"Posted {r['posted']}" + (f", in effect from {r['in_effect_from']}" if r.get("in_effect_from") else "")
            + (f" to {r['in_effect_to']}" if r.get("in_effect_to") else "") + ". The release list gives no summary of "
            "what changed; the change record is on the USITC's HTS site.",
            data_as_of=f"{r['posted']}T00:00:00Z", generated=generated, valid_until=valid_until, countries=["US"],
            pmesii=["economic"], ascope=["organizations"], ncf=["maintain_supply_chains"], requirement_ids=["HW-PIR-2"],
            measures={}, visual={"type": "page", "url": tariffs.HTS_PAGE}, source=SRC_USITC, accessed=accessed))
    return feats


def _doc_kind(doc_type: str | None) -> str:
    t = (doc_type or "").lower()
    return "proposed rule" if t.startswith("proposed") else "notice" if t == "notice" else "rule"


KIND_WORDS = {"stay_or_extension": "a stay, suspension or extension", "entity_list": "an Entity List change"}
STATE_TEXT = {
    "present": ("HW-IND-2's condition is met: {kind} by {agency}, filed {days} before a date that {basis_doc}."),
    "absent": "HW-IND-2's condition is not met: {why}.",
    "no_data": "HW-IND-2 could not be measured: the filing's text could not be read and nothing else matched it.",
}


def _match_text(m: dict) -> str:
    when = "the day it was filed" if m["days"] == 0 else f"{m['days']} day{'s' if m['days'] != 1 else ''} after the filing"
    if m.get("sentence"):
        return f"{m['date']} ({when}; the filing says: \"{m['sentence']}\")"
    return f"{m['date']} ({when}; {m['basis']}: {m['what']} in document {m['doc']}, published {m['doc_published']})"


def inspection_features(snapshot: dict, generated: str, valid_until: str, accessed: str | None) -> list[dict]:
    """Filings on public inspection by BIS, OFAC and USTR, from the day filed for FEED_DAYS. Published facts and the
    dates they line up with; HW-IND-2's state on BIS and USTR filings. Filings kept from before headwind-1.9 as
    counted only (no title) are not items."""
    cutoff = _plus_hours(generated, -24 * inspection.FEED_DAYS)[:10]
    out = []
    for r in snapshot.get("inspection") or []:
        if r.get("counted_only") or (r.get("filed_on") or r.get("issue")) < cutoff:
            continue
        text = r.get("text") or {}
        kind = _doc_kind(r["type"])
        filed = (r.get("filed_at_utc") or "")
        filed_text = (f"on {filed[:10]} at {filed[11:16]} UTC" if filed else f"in the issue of {r['issue']}")
        parts = [f"Filed for public inspection at the Office of the Federal Register {filed_text}"
                 + (f", to be published {r['publication_date']}" if r.get("publication_date") else
                    ", with no publication date set") + "."]
        if text.get("action") and text["action"].lower() != "notice":
            parts.append(f"Action: {text['action']}.")
        if text.get("summary_first"):
            parts.append(f"The filing's summary begins: \"{text['summary_first']}\"")
        ids = [f"RIN {', '.join(text['rins'])}" if text.get("rins") else "",
               f"docket {', '.join(sorted(set(r.get('dockets') or []) | set(text.get('dockets') or [])))}"
               if (r.get("dockets") or text.get("dockets")) else ""]
        if any(ids):
            line = "; ".join(x for x in ids if x)
            parts.append(line[:1].upper() + line[1:] + ".")
        matches = r.get("matches") or []
        if matches:
            parts.append(f"Scheduled dates within {inspection.WINDOW_DAYS} days after the filing: "
                         + "; ".join(_match_text(m) for m in matches[:5]) + ".")
        extra = None
        state = r.get("indicator_state")
        if state:
            first = matches[0] if matches else None
            if state == "present":
                basis_doc = (f"the filing itself says was scheduled" if first.get("sentence") else
                             f"document {first['doc']} ({first['basis']}) set")
                parts.append(STATE_TEXT["present"].format(
                    kind=KIND_WORDS[r["kind"]], agency=r["agency"],
                    days="the same day as" if first["days"] == 0 else f"{first['days']} days",
                    basis_doc=basis_doc).replace("filed the same day as before", "filed on the day of"))
            elif state == "absent":
                why = ("it is not a stay, suspension, extension or Entity List filing" if r.get("kind") == "other"
                       else f"no date of the same rule, docket or investigation falls within {inspection.WINDOW_DAYS} "
                            f"days after it, and the filing names none as scheduled")
                parts.append(STATE_TEXT["absent"].format(why=why))
            else:
                parts.append(STATE_TEXT["no_data"])
            extra = {"indicator_id": "HW-IND-2", "hypothesis_id": "HW-H-1B",
                     "direction": "supports" if state == "present" else "neutral", "indicator_state": state}
        if r.get("withdrawn"):
            parts.append(f"Editorial note: {r['note']}")
        parts.append(f"Federal Register document {r['id']}.")
        countries = controls.countries_in(r.get("title") or "")
        out.append(_official(
            f"headwind:inspection:{r['id']}",
            f"{r['agency']} {kind} filed for public inspection ({r['filed_on']}){' (withdrawn)' if r.get('withdrawn') else ''}: "
            f"{r['title']}",
            " ".join(parts),
            data_as_of=filed or f"{r['issue']}T00:00:00Z", generated=generated, valid_until=valid_until,
            countries=countries, pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "manufacture_equipment"], requirement_ids=["HW-EEI-2", "HW-PIR-2"],
            measures={"days_to_deadline": r.get("days_to_deadline"), "scheduled_dates_matched": len(matches),
                      "pages": r.get("pages")},
            visual={"type": "page", "url": r["url"]}, source={**SRC_PI, "url": r["url"]},
            accessed=accessed, extra=extra))
        out[-1]["properties"]["us_person_data"] = inspection.person_label(r)
    return out



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
            f"headwind:fx:{f['currency']}",
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
            coverage=1.0, lane_accessed=accessed("fx"), ascope=["events"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))

    for o in snapshot.get("fx_official") or []:
        if o.get("stale"):
            continue        # the page lists it with its newest month
        cc = o["country"]
        name = geo.name(cc) or cc
        feats.append(_observation(
            f"headwind:fxofficial:{cc}",
            f"{name}: official exchange rate {abs(o['change_pct']):.1f}% {o['direction']} against the US dollar "
            f"in {o['period']} ({_z_text(o['z'])})",
            f"Monthly average official rate {o['per_usd']:g} per US dollar in {o['period']}, against "
            f"{o['prior_per_usd']:g} in {o['prior_period']}. Measured against the country's own {o['baseline_n']} "
            f"earlier monthly changes. World Bank Global Economic Monitor.",
            anomaly=o["anomaly"], data_as_of=_month_end_by(o["period"], generated), generated=generated,
            valid_until=valid_until, countries=[cc], ncf=["provide_funding_liquidity", "provide_capital_markets"],
            requirement_ids=["HW-PIR-4"],
            measures={"per_usd": o["per_usd"], "change_pct": o["change_pct"], "z": o["z"],
                      "baseline_n": o["baseline_n"], "flag_rate": o.get("flag_rate")},
            anchor="countries", source=SRC_GEM, indicator_id="HW-IND-4",
            baseline_ref=f"rolling: the country's own {markets.GEM_WINDOW} prior monthly changes; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a move of at least {markets.GEM_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("gem"), ascope=["events"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))

    hdx_modified = {w["country"]: w.get("hdx_last_modified") for w in snapshot.get("local_food") or []}
    for w in snapshot.get("market_fx") or []:
        if w.get("stale"):
            continue
        cc = w["country"]
        name = geo.name(cc) or cc
        kind = "unofficial market" if w.get("unofficial") else "market"
        level = (f"rates from {w['per_usd_low']:g} to {w['per_usd_high']:g} per US dollar, too far apart to be one "
                 f"market" if w.get("split") else f"median rate {w['per_usd_median']:g} per US dollar")
        feats.append(_observation(
            f"headwind:fxmarket:{cc}",
            f"{name}: {kind} exchange rate {abs(w['median_change_pct']):.1f}% {w['direction']} against the US dollar "
            f"in {w['period']}, median of {w['markets']} market{'s' if w['markets'] != 1 else ''} "
            f"({_z_text(w['z'])})",
            f"Median one-month change to {w['period']} across {w['markets']} markets' exchange rates as WFP "
            f"collected them ({', '.join(w.get('labels') or [])}); {level}. Judged against the country's own "
            f"{w['baseline_n']} earlier medians.",
            anomaly=w["anomaly"], data_as_of=_month_end_by(w["period"], generated, hdx_modified.get(cc)),
            generated=generated,
            valid_until=valid_until, countries=[cc], ncf=["provide_funding_liquidity", "provide_capital_markets"],
            requirement_ids=["HW-PIR-4"],
            measures={"median_change_pct": w["median_change_pct"], "markets": w["markets"],
                      "per_usd_median": None if w.get("split") else w["per_usd_median"], "z": w["z"],
                      "baseline_n": w["baseline_n"], "flag_rate": w.get("flag_rate")},
            anchor="countries", source={**SRC_WFP, "url": w.get("dataset") or SRC_WFP["url"]},
            indicator_id="HW-IND-4",
            baseline_ref=f"rolling: the country's own {food.WFPFX_WINDOW} prior monthly medians; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a median move of at least {food.WFPFX_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("wfp"), ascope=["events", "people"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))

    for e in snapshot.get("energy") or []:
        feats.append(_observation(
            f"headwind:energy:{e['id']}",
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
            coverage=1.0, lane_accessed=accessed("energy"), ascope=["events"], hypothesis_id="HW-H-2B"))

    for c in snapshot.get("fao") or []:
        feats.append(_observation(
            f"headwind:food:{c['id']}",
            f"{c['name']} ({c['period']}): {c['value']:g}, {c['change_pct']:+.1f}% on the month ({_z_text(c['z'])})",
            f"{c['value']:g} for {c['period']}, against {c['prior_value']:g} for {c['prior_period']} "
            f"(2014-2016 = 100). FAO revises earlier months; these are the values as published today."
            f"{_rules_text(c)}",
            anomaly=c["anomaly"], data_as_of=_month_end(c["period"]), generated=generated, valid_until=valid_until,
            countries=[], ncf=["provide_food_products", "provide_agricultural_products", "maintain_supply_chains"],
            requirement_ids=["HW-PIR-3"],
            measures={"index_value": c["value"], "change_pct": c["change_pct"], "z": c["z"],
                      "baseline_n": c["baseline_n"], "flag_rate": c.get("flag_rate"), "rules": c.get("rules", []),
                      "rise_run": c.get("rise_run")},
            anchor="food", source=SRC_FAO, indicator_id="HW-IND-3",
            baseline_ref=f"rolling: the index's own {food.FAO_WINDOW} prior monthly changes; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g}, a rise in the top 5% of them, or six or more rises in a row, "
                         f"with a move of at least {food.FAO_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("fao"), ascope=["events"]))

    for c in snapshot.get("pinksheet") or []:
        crit = (f" On the US Final 2025 List of Critical Minerals as {c['critical_list_name']}."
                if c.get("critical_list_name") else "")
        feats.append(_observation(
            f"headwind:pinksheet:{c['id']}",
            f"{c['name']} ({c['period']}): {c['value']:g} {c['unit']}, {c['change_pct']:+.1f}% on the month "
            f"({_z_text(c['z'])})",
            f"{c['value']:g} {c['unit']} for {c['period']}, against {c['prior_value']:g} for {c['prior_period']}; "
            f"monthly average in nominal US dollars from the World Bank's Pink Sheet.{crit}",
            anomaly=c["anomaly"], data_as_of=_month_end(c["period"]), generated=generated, valid_until=valid_until,
            countries=[], ncf=PINK_NCF.get(c.get("group"), ["maintain_supply_chains"]),
            requirement_ids=["HW-PIR-6"],
            measures={"price": c["value"], "change_pct": c["change_pct"], "z": c["z"],
                      "baseline_n": c["baseline_n"], "flag_rate": c.get("flag_rate")},
            anchor="pinksheet", source=SRC_PINKSHEET, indicator_id=None,
            baseline_ref=f"rolling: the series' own {pinksheet.WINDOW} prior monthly changes; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a move of at least {c.get('floor_pct', pinksheet.FLOOR):g}%",
            coverage=1.0, lane_accessed=accessed("pinksheet"), ascope=["events"]))

    for w in snapshot.get("local_food") or []:
        if w.get("stale"):
            continue        # too old to describe current conditions; the page lists it as no recent data
        cc = w["country"]
        name = geo.name(cc) or cc
        feats.append(_observation(
            f"headwind:localfood:{cc}",
            f"{name}: local food prices {w['median_change_pct']:+.0f}% in {food.WFP_HORIZON} months, median of "
            f"{w['series']} price series ({_z_text(w['z'])})",
            f"Median {food.WFP_HORIZON}-month change to {w['period']} across {w['series']} market-and-commodity "
            f"series in {w['markets']} markets; {round(w['share_rising'] * 100)}% of series rose. Nominal prices in "
            f"local currency, judged against the country's own {w['baseline_n']} earlier medians.{_rules_text(w)}",
            anomaly=w["anomaly"], data_as_of=_month_end_by(w["period"], generated, w.get("hdx_last_modified")),
            generated=generated,
            valid_until=valid_until, countries=[cc], ncf=["provide_food_products", "provide_agricultural_products"],
            requirement_ids=["HW-PIR-5"],
            measures={"median_change_pct": w["median_change_pct"], "series": w["series"], "markets": w["markets"],
                      "share_rising": w["share_rising"], "z": w["z"], "baseline_n": w["baseline_n"], "flag_rate": w.get("flag_rate"),
                      "rules": w.get("rules", []), "rise_run": w.get("rise_run")},
            anchor="local-food", source={**SRC_WFP, "url": w.get("dataset") or SRC_WFP["url"]},
            indicator_id="HW-IND-6",
            baseline_ref=f"rolling: the country's own {food.WFP_WINDOW} prior monthly medians; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g}, a rise in the top 5% of them, or six or more rises in a row, "
                         f"with a median move of at least {food.WFP_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("wfp"), ascope=["events", "people"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))
    return feats


# The currency each watched country uses, where the ECB quotes it but under another country (the Palestinian
# territories use the Israeli shekel). Shown in the country view only; the feed item stays Israel's.
CURRENCY_IN_USE = {"PS": "ILS"}
NON_DIAGNOSTIC = frozenset({"HW-IND-6"})     # doctrine/indicators.json: gentry.diagnostic false

# Shown with "market against official" on the page. A gap this wide more often means the two sources report
# different rates than that one market trades at that premium.
GAP_CAVEAT = {
    "YE": ("Yemen has had two rials in use since 2019, Aden's and Sana'a's. Which rate the World Bank's monthly "
           "figure reports is not verified, so this gap may set two different rates side by side."),
}
GAP_WIDE_PCT = 100.0
GAP_WIDE = ("A gap this wide can mean the two sources report different rates, not a market premium; which rate the "
            "World Bank's figure is has not been checked for this country.")


def country_view(snapshot: dict) -> list[dict]:
    """One row per watched country: its daily rate (ECB) where there is one, its official monthly rate (World Bank
    GEM), its market rate (WFP), the market rate against the official one for the same month, its local food
    reading, and the HW-WP-2 indicators present. Measurements side by side; nothing is combined into a score."""
    by_cc = {f["country"]: f for f in snapshot.get("fx") or [] if f.get("country")}
    by_cur = {f["currency"]: f for f in snapshot.get("fx") or []}
    off = {o["country"]: o for o in snapshot.get("fx_official") or []}
    mkt = {w["country"]: w for w in snapshot.get("market_fx") or []}
    lf = {w["country"]: w for w in snapshot.get("local_food") or []}
    missing = {m["country"]: m["reason"] for m in snapshot.get("local_food_missing") or []}
    out = []
    for cc in sorted(WATCHED):
        daily = by_cc.get(cc) or by_cur.get(CURRENCY_IN_USE.get(cc, ""))
        o, w, f = off.get(cc), mkt.get(cc), lf.get(cc)
        row = {"country": cc, "name": geo.name(cc) or cc}
        row["daily"] = None if not daily else {
            "currency": daily["currency"], "per_usd": daily["per_usd"], "change_pct": daily["change_pct"],
            "z": daily["z"], "anomaly": daily["anomaly"], "date": daily["date"],
            "note": None if daily.get("country") == cc else f"{daily['currency']}, the currency in use"}
        row["official"] = None if not o else {k: o[k] for k in ("per_usd", "change_pct", "z", "anomaly", "period",
                                                                "stale")}
        row["market"] = None if not w else {k: w.get(k) for k in ("per_usd_median", "per_usd_low", "per_usd_high",
                                                                  "split", "unofficial", "median_change_pct", "z",
                                                                  "anomaly", "period", "stale", "markets")}
        gap = None
        if o and w and not w.get("split"):
            # The newest month both give (WFP's and the World Bank's months seldom end together), and never a
            # month in which the markets were too far apart to be one market.
            official, market = dict(o.get("recent") or []), dict(w.get("recent") or [])
            both = sorted((set(official) & set(market)) - set(w.get("split_months") or []))
            if both and official[both[-1]] > 0:
                gap = {"period": both[-1], "pct": round((market[both[-1]] / official[both[-1]] - 1.0) * 100.0, 1)}
                caveat = GAP_CAVEAT.get(cc) or (GAP_WIDE if abs(gap["pct"]) >= GAP_WIDE_PCT else None)
                if caveat:
                    gap["caveat"] = caveat
        row["market_vs_official"] = gap
        row["local_food"] = None if not f else {k: f[k] for k in ("median_change_pct", "z", "anomaly", "period",
                                                                  "stale")}
        if not f and cc in missing:
            row["local_food_missing"] = missing[cc]
        present = []
        if any(x and x.get("anomaly") and not x.get("stale") for x in (by_cc.get(cc), o, w)):
            present.append("HW-IND-4")
        if f and f.get("anomaly"):
            present.append("HW-IND-6")
        row["indicators_present"] = present
        out.append(row)
    return out


def build_feed(snapshot: dict) -> dict:
    """Build a contract-v2 GeoJSON FeatureCollection from Headwind's normalized snapshot."""
    generated = snapshot["generated_at"]
    features = list_features(snapshot)

    # Exchange rates, energy, FAO indices, local food prices. Measurements only.
    features.extend(live_features(snapshot))

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "headwind",
        "generated_at": generated,
        "licence": ("Headwind code GNU AGPL-3.0; ECB reference rates free to reuse with credit; World Bank Global Economic "
                    "Monitor CC BY 4.0; EIA data US public domain; "
                    "FAO CC BY 4.0; WFP food prices CC BY-IGO; OFAC list, Consolidated Screening List and "
                    "Federal Register and its public inspection US public domain; USITC tariff schedule releases and White House presidential actions US government works; UN Security Council list, no "
                    "licence stated; EU financial "
                    "sanctions list, European Commission reuse notice; UK Sanctions List, Open Government Licence v3.0; "
                    "France's Registre national des gels, Licence Ouverte 2.0; Canada's consolidated autonomous "
                    "sanctions list, non-commercial reproduction (Canada.ca terms); Australian Sanctions Consolidated "
                    "List, CC BY 4.0 (Department of Foreign Affairs and Trade website – www.dfat.gov.au); UN press "
                    "releases, linked only; "
                    "Supreme Court of the United States opinions and dockets, US government works"),
        "attribution": ("Headwind, The Intelligence Company. Data: European Central Bank; World Bank; US Energy Information "
                        "Administration; FAO; World Food Programme via the Humanitarian Data Exchange; "
                        "US Treasury (OFAC); United Nations Security Council; European Commission; UK Foreign, Commonwealth "
                        "and Development Office; French Treasury (Direction générale du Trésor); Global Affairs Canada; Australian "
                        "Department of Foreign Affairs and Trade; Supreme Court of the United States; US International Trade Administration; "
                        "US Federal Register and the Office of the Federal Register; US International Trade Commission; The White House."),
        "language_key": LANGUAGE_KEY,
        # One entry per source, keyed by the source id the items carry (headwind/health.py): whether this run read
        # it, how old its newest data are, and any drift or quiet-publisher warning. COP and the kit's history log
        # read this; a source shown "failing" is a last good copy, not a quiet one.
        "health": snapshot.get("health") or {},
        "features": features,
    }
