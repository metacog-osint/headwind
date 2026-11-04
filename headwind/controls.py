"""Federal Register (BIS / USTR / OFAC) rule-stay tracker and Verdict calendar exporter."""
from __future__ import annotations


def normalize_control_rules(rules: list[dict]) -> list[dict]:
    out = []
    for r in rules:
        out.append({
            "id": r["id"],
            "doc_number": r.get("doc_number") or r["id"],
            "agency": r.get("agency") or "BIS",
            "title": r["title"],
            "published_date": r.get("published_date") or "2026-10-26",
            "deadline_date": r["deadline_date"],
            "days_to_deadline": int(r.get("days_to_deadline", 10)),
            "status_note": r.get("status_note") or "Active stay window",
            "countries": [c.upper() for c in (r.get("countries") or ["US", "CN"])],
            "lat": float(r.get("lat", 38.8951)),
            "lon": float(r.get("lon", -77.0364)),
            "url": r.get("url") or "https://www.federalregister.gov/",
            "summary": r["summary"],
        })
    out.sort(key=lambda x: x["deadline_date"])
    return out


def build_verdict_events(rules: list[dict], commodities: list[dict]) -> dict:
    """Export dated regulatory deadlines and data releases in Verdict's sync_calendar format."""
    events = []
    for r in rules:
        events.append({
            "id": f"{r['deadline_date']}-{r['id']}",
            "date": r["deadline_date"],
            "title": f"{r['agency']}: {r['title']}",
            "kind": "rule_date",
            "countries": r["countries"],
            "ref": r["doc_number"],
            "source": {
                "publisher": f"Federal Register ({r['agency']})",
                "url": r["url"],
            },
        })
    for c in commodities:
        if c.get("next_release_date"):
            events.append({
                "id": f"{c['next_release_date']}-{c['id']}-release",
                "date": c["next_release_date"],
                "title": f"{c['name']} monthly release",
                "kind": "data_release",
                "countries": [],
                "ref": c["id"].upper(),
                "source": {
                    "publisher": c["publisher"],
                    "url": c["url"],
                },
            })
    return {"source": "headwind", "events": events}
