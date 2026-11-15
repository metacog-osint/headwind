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

from . import batches, controls, food, inspection, markets, stats  # noqa: E402

SITE = "https://headwind.theintelligence.company"
METHOD = "headwind-1.6"
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

LIST_SOURCE = {"ofac-sdn": SRC_OFAC, "un-consolidated": SRC_UN, "eu-fsf": SRC_EU, "uk-sanctions": SRC_UK}

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
    "publisher": "US Federal Register (BIS, OFAC, USTR)",
    "title": "Federal Register documents",
    "url": "https://www.federalregister.gov/api/v1/documents.json",
    "licence": "US public domain",
    "grade": "A1",
    "independence_group": "us-federal-register",
    "source_type": "official or market data",
    "descriptor": "Rules, proposed rules and notices as published by the agency in the official journal.",
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


def _month_end_by(period: str, generated: str) -> str:
    """The month's end, or the collection time for a month still under way: never dated in the future."""
    return min(_month_end(period), generated)


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
        # the item id ("headwind:fxmarket:SD:2026-10" -> "headwind-fxmarket"); every series rule is rolling.
        props["baseline_ref"] = {"id": f"headwind-{item_id.split(':')[1]}", "type": "rolling", "version": METHOD,
                                 "window": baseline_ref.removeprefix("rolling: ")}
        if hypothesis_id:
            # HW-WP-2: an anomaly for a watched country (or an energy benchmark) is its indicator present. The
            # direction is the register's: each indicator is emerging under the hypothesis named here.
            props.update({"indicator_id": indicator_id, "hypothesis_id": hypothesis_id, "direction": "supports",
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
ALSO_ON = {"ofac-sdn": "the OFAC SDN list", "uk-sanctions": "the UK Sanctions List"}


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
        parts = []
        if s["added"]:
            parts.append(f"Added {s['added']}: by type, {_counts(s['added_by_type'])}; by program, "
                         f"{_counts(s['added_by_program'])}.")
        if s["removed"]:
            parts.append(f"Removed {s['removed']}: by type, {_counts(s['removed_by_type'])}; by program, "
                         f"{_counts(s['removed_by_program'])}.")
        parts.append(_edit_text(s))
        since = f" since Headwind's reading of {s['prior_checked_at'][:10]}" if s.get("prior_checked_at") else ""
        feats.append(_official(
            f"headwind:sanctions:{s['id']}",
            f"{s['list_name']}: {s['added']} added, {s['removed']} removed{_changed_title(s)}",
            f"{' '.join(x for x in parts if x)} The list now holds {s['total']} entries. This is the difference between two of "
            f"Headwind's readings{since}, seen on {s['detected_at'][:10]}; the dates of the designations are in "
            f"the publisher's own notices.{_vessel_text('added', s.get('vessels_added') or [])}"
            f"{_vessel_text('removed', s.get('vessels_removed') or [])}{_rekeyed_text(s.get('vessels_rekeyed') or [])}"
            f"{_renamed_text(s.get('vessels_changed') or [])}{batches.text(s.get('batches') or [])}"
            f" People and organizations are counts "
            f"only; their names are on the official list.",
            data_as_of=s["detected_at"], generated=generated, valid_until=valid_until, countries=s["countries"],
            pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "provide_funding_liquidity"], requirement_ids=["HW-PIR-1"],
            measures={"added": s["added"], "removed": s["removed"], "total": s["total"],
                      "changed": s.get("changed", 0), "vessels_added": s["added_by_type"].get("vessel", 0),
                      "vessels_changed": len(s.get("vessels_changed") or []), "rekeyed": s.get("rekeyed", 0),
                      **_batch_measures(s)},
            visual={"type": "page", "url": f"{SITE}/#sanctions"},
            source=LIST_SOURCE[s["list"]],
            accessed=(lanes.get("sanctions") or {}).get("fetched_at"), anomaly_ref=_batch_ref(s)))

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
            f"dates of the listings are in the publisher's own notices.{batches.text(s.get('batches') or [])} Counts "
            f"only; names are on the official list.",
            data_as_of=s["detected_at"], generated=generated, valid_until=valid_until, countries=s["countries"],
            pmesii=["economic", "political"], ascope=["organizations"],
            ncf=["maintain_supply_chains", "manufacture_equipment"], requirement_ids=["HW-PIR-1"],
            measures={"added": s["added"], "removed": s["removed"], "total": s["total"],
                      "changed": s.get("changed", 0), "rekeyed": s.get("rekeyed", 0), **_batch_measures(s)},
            visual={"type": "page", "url": f"{SITE}/#screening"},
            source={**SRC_CSL, "url": s.get("url") or SRC_CSL["url"]},
            accessed=(lanes.get("screening") or {}).get("fetched_at"), anomaly_ref=_batch_ref(s)))

    for r in controls.recent(snapshot.get("controls") or [], generated, RULE_DAYS):
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
    dates they line up with; HW-IND-2's state on BIS and USTR filings. Notices counted only are not items."""
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
            coverage=1.0, lane_accessed=accessed("fx"), ascope=["events"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))

    for o in snapshot.get("fx_official") or []:
        if o.get("stale"):
            continue        # the page lists it with its newest month
        cc = o["country"]
        name = geo.name(cc) or cc
        feats.append(_observation(
            f"headwind:fxofficial:{cc}:{o['period']}",
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

    for w in snapshot.get("market_fx") or []:
        if w.get("stale"):
            continue
        cc = w["country"]
        name = geo.name(cc) or cc
        kind = "unofficial market" if w.get("unofficial") else "market"
        level = (f"rates from {w['per_usd_low']:g} to {w['per_usd_high']:g} per US dollar, too far apart to be one "
                 f"market" if w.get("split") else f"median rate {w['per_usd_median']:g} per US dollar")
        feats.append(_observation(
            f"headwind:fxmarket:{cc}:{w['period']}",
            f"{name}: {kind} exchange rate {abs(w['median_change_pct']):.1f}% {w['direction']} against the US dollar "
            f"in {w['period']}, median of {w['markets']} market{'s' if w['markets'] != 1 else ''} "
            f"({_z_text(w['z'])})",
            f"Median one-month change to {w['period']} across {w['markets']} markets' exchange rates as WFP "
            f"collected them ({', '.join(w.get('labels') or [])}); {level}. Judged against the country's own "
            f"{w['baseline_n']} earlier medians.",
            anomaly=w["anomaly"], data_as_of=_month_end_by(w["period"], generated), generated=generated,
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
            coverage=1.0, lane_accessed=accessed("energy"), ascope=["events"], hypothesis_id="HW-H-2B"))

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
            anomaly=w["anomaly"], data_as_of=_month_end_by(w["period"], generated), generated=generated,
            valid_until=valid_until, countries=[cc], ncf=["provide_food_products", "provide_agricultural_products"],
            requirement_ids=["HW-PIR-5"],
            measures={"median_change_pct": w["median_change_pct"], "series": w["series"], "markets": w["markets"],
                      "share_rising": w["share_rising"], "z": w["z"], "baseline_n": w["baseline_n"], "flag_rate": w.get("flag_rate")},
            anchor="local-food", source={**SRC_WFP, "url": w.get("dataset") or SRC_WFP["url"]},
            indicator_id="HW-IND-6",
            baseline_ref=f"rolling: the country's own {food.WFP_WINDOW} prior monthly medians; anomaly at "
                         f"|z| >= {stats.Z_ANOMALY:g} and a median move of at least {food.WFP_FLOOR:g}%",
            coverage=1.0, lane_accessed=accessed("wfp"), ascope=["events", "people"],
            hypothesis_id="HW-H-2A" if cc in WATCHED else None))
    return feats


# The currency each watched country uses, where the ECB quotes it but under another country (the Palestinian
# territories use the Israeli shekel). Shown in the country view only; the feed item stays Israel's.
CURRENCY_IN_USE = {"PS": "ILS"}

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
        "licence": ("Headwind code MIT; ECB reference rates free to reuse with credit; World Bank Global Economic "
                    "Monitor CC BY 4.0; EIA data US public domain; "
                    "FAO CC BY 4.0; WFP food prices CC BY-IGO; OFAC list, Consolidated Screening List and "
                    "Federal Register and its public inspection US public domain; UN Security Council list, no "
                    "licence stated; EU financial "
                    "sanctions list, European Commission reuse notice; UK Sanctions List, Open Government Licence v3.0"),
        "attribution": ("Headwind, The Intelligence Company. Data: European Central Bank; World Bank; US Energy Information "
                        "Administration; FAO; World Food Programme via the Humanitarian Data Exchange; "
                        "US Treasury (OFAC); United Nations Security Council; European Commission; UK Foreign, Commonwealth "
                        "and Development Office; US International Trade Administration; "
                        "US Federal Register and the Office of the Federal Register."),
        "language_key": LANGUAGE_KEY,
        # One entry per source, keyed by the source id the items carry (headwind/health.py): whether this run read
        # it, how old its newest data are, and any drift or quiet-publisher warning. COP and the kit's history log
        # read this; a source shown "failing" is a last good copy, not a quiet one.
        "health": snapshot.get("health") or {},
        "features": features,
    }
