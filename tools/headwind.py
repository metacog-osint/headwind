"""Headwind CLI: collect, build, and check.

    python tools/headwind.py collect
    python tools/headwind.py build
    python tools/headwind.py check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import commodities, controls, feed, sanctions  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

SEED_SNAPSHOT = {
    "generated_at": "2026-11-01T12:00:00Z",
    "raw_sanctions": [
        {
            "id": "ofac-2026-10-30-shadow-fleet",
            "date": "2026-10-30",
            "title": "Baltic & Red Sea Shadow-Fleet Crude Tanker Designations",
            "program_tag": "RUSSIA-EO14024 / IRAN-EO13902",
            "countries": ["RU", "IR", "PA"],
            "entities_added": 14,
            "dual_use_network": True,
            "lat": 59.76,
            "lon": 24.42,
            "vessels": [
                {"name": "MV BALTIC TRANSPORTER", "imo": "9384710", "mmsi": "273458910", "flag": "RU"},
                {"name": "MT CRUDE NAVIGATOR", "imo": "9411208", "mmsi": "352981400", "flag": "PA"},
                {"name": "MT HORMUZ STAR", "imo": "9298104", "mmsi": "577412000", "flag": "IR"},
            ],
            "summary": (
                "OFAC designated 14 entities and 3 shadow-fleet tankers (including MV BALTIC TRANSPORTER MMSI 273458910 "
                "and MT CRUDE NAVIGATOR MMSI 352981400, both tracked loitering near the Gulf of Finland subsea corridor by Wake)."
            ),
        }
    ],
    "raw_controls": [
        {
            "id": "bis-affiliates-stay-2026-11-10",
            "doc_number": "2025-19846",
            "agency": "BIS",
            "title": "Affiliates (50% Ownership) Rule One-Year Stay Expiration",
            "published_date": "2025-11-12",
            "deadline_date": "2026-11-10",
            "days_to_deadline": 9,
            "countries": ["US", "CN"],
            "lat": 38.8951,
            "lon": -77.0364,
            "url": "https://www.federalregister.gov/documents/2025/11/12/2025-19846/one-year-suspension-of-expansion-of-end-user-controls-for-affiliates-of-certain-listed-entities",
            "summary": (
                "BIS Affiliates 50% rule stay expires 10 Nov 2026 (9 days away); USTR proposed extending its matching "
                "Section 301 maritime suspension to 9 Jan 2027 (FR Doc 2026-21755)."
            ),
        },
        {
            "id": "ustr-maritime-section-301-2026-21755",
            "doc_number": "2026-21755",
            "agency": "USTR",
            "title": "Further Suspension of Section 301 Action: China Maritime & Logistics",
            "published_date": "2026-10-26",
            "deadline_date": "2027-01-09",
            "days_to_deadline": 69,
            "countries": ["US", "CN"],
            "lat": 38.9005,
            "lon": -77.0398,
            "url": "https://www.federalregister.gov/documents/2026/10/26/2026-21755/request-for-comments-on-further-suspension-of-section-301-action-chinas-targeting-of-the-maritime",
            "summary": "USTR notice proposing extension of Section 301 port-fee suspension through 9 Jan 2027.",
        },
    ],
    "raw_commodities": [
        {
            "id": "igc-goi",
            "name": "IGC Grains and Oilseeds Index (GOI)",
            "publisher": "International Grains Council",
            "period": "2026-10",
            "current_value": 231.4,
            "prior_value": 241.8,
            "next_release_date": "2026-11-20",
            "url": "https://igc.int/en/public-site/markets/marketinfo-goi.aspx",
            "summary": "IGC Grains and Oilseeds Index fell -4.30% in October (wheat -5.4%, maize -6.9%), pointing to a lower October FAO Food Price Index print on 6 Nov.",
        },
        {
            "id": "fao-ffpi",
            "name": "FAO Food Price Index (FFPI)",
            "publisher": "FAO",
            "period": "2026-09",
            "current_value": 136.0,
            "prior_value": 134.0,
            "next_release_date": "2026-11-06",
            "url": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
            "summary": "September 2026 FAO Food Price Index printed at 136.0 (+1.49%); October release scheduled for 6 Nov 2026.",
        },
    ],
}


def build_snapshot(raw: dict | None = None) -> dict:
    raw = raw or SEED_SNAPSHOT
    s_list = sanctions.normalize_sanctions_deltas(raw.get("raw_sanctions", []))
    c_list = controls.normalize_control_rules(raw.get("raw_controls", []))
    m_list = commodities.normalize_commodities(raw.get("raw_commodities", []))
    events_doc = controls.build_verdict_events(c_list, m_list)
    return {
        "generated_at": raw.get("generated_at", "2026-11-01T12:00:00Z"),
        "sanctions": s_list,
        "controls": c_list,
        "commodities": m_list,
        "events": events_doc,
    }


def collect() -> dict:
    normalized = build_snapshot(SEED_SNAPSHOT)
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "snapshot.json").write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return normalized


def build_site(root: Path = ROOT) -> dict[str, str]:
    snap_path = root / "data" / "snapshot.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else build_snapshot()
    feed_doc = feed.build_feed(snap)

    files = {
        "data/snapshot.json": json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
        "data/feed.geojson": json.dumps(feed_doc, indent=2, ensure_ascii=False) + "\n",
        "data/events.json": json.dumps(snap["events"], indent=2, ensure_ascii=False) + "\n",
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
        build_site(root)
    feed_doc = json.loads(feed_path.read_text(encoding="utf-8"))
    for feat in feed_doc.get("features", []):
        fid = (feat.get("properties") or {}).get("id", "?")
        for std, sev, msg in contract.check(feat, regs):
            if sev == "error":
                errs.append(f"{fid}: {std}: {msg}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headwind sanctions, export controls & commodity monitor.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect")
    sub.add_parser("build")
    sub.add_parser("check")
    args = ap.parse_args(argv)

    if args.cmd == "collect":
        snap = collect()
        print(
            f"Collected {len(snap['sanctions'])} OFAC batches, "
            f"{len(snap['controls'])} export-control rules, {len(snap['commodities'])} commodity indices."
        )
        return 0
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
