"""Strategic commodity and food price benchmark tracker (FAO FFPI, IGC GOI)."""
from __future__ import annotations


def normalize_commodities(series: list[dict]) -> list[dict]:
    out = []
    for s in series:
        cur = float(s["current_value"])
        prev = float(s["prior_value"])
        mom_pct = round(((cur - prev) / prev) * 100.0, 2) if prev else 0.0
        out.append({
            "id": s["id"],
            "name": s["name"],
            "publisher": s.get("publisher") or "FAO",
            "period": s.get("period") or "2026-10",
            "current_value": round(cur, 2),
            "prior_value": round(prev, 2),
            "mom_pct": mom_pct,
            "next_release_date": s.get("next_release_date"),
            "url": s.get("url") or "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
            "summary": s.get("summary") or (
                f"{s['name']} ({s.get('period', 'latest')}): {round(cur, 1)} vs {round(prev, 1)} prior ({mom_pct:+.2f}%)."
            ),
        })
    return out
