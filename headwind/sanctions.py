"""OFAC SDN & Consolidated Sanctions List delta normalizer."""
from __future__ import annotations


def normalize_sanctions_deltas(batches: list[dict]) -> list[dict]:
    """Normalize OFAC SDN delta batches into structured sanctions action records."""
    out = []
    for b in batches:
        vessels = b.get("vessels") or []
        entities = int(b.get("entities_added", len(vessels)))
        out.append({
            "id": b.get("id") or f"ofac-{b.get('date', '2026-11-01')}",
            "date": b.get("date") or "2026-11-01",
            "title": b["title"],
            "program_tag": b.get("program_tag") or "RUSSIA-EO14024 / IRAN",
            "countries": [c.upper() for c in (b.get("countries") or ["RU"])],
            "entities_added": entities,
            "vessels_added": len(vessels),
            "vessels": vessels,
            "dual_use_network": bool(b.get("dual_use_network", False)),
            "lat": float(b.get("lat", 59.75)),
            "lon": float(b.get("lon", 24.40)),
            "url": b.get("url") or "https://ofac.treasury.gov/recent-actions",
            "summary": b.get("summary") or (
                f"OFAC designated {entities} entities and {len(vessels)} vessels under {b.get('program_tag', 'sanctions')}."
            ),
        })
    out.sort(key=lambda x: (x["date"], -x["entities_added"]), reverse=True)
    return out
