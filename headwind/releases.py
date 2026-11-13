"""Scheduled economic dates for Verdict's calendar, read from the publishers' own pages.

Covered: Federal Reserve FOMC decisions, ECB monetary policy decisions, FAO Food Price Index
releases. Not covered: US CPI and jobs reports (bls.gov refused automated requests on
12 Nov 2026), and any other central bank.
A rate decision is exported with kind "rule_date", the nearest of Verdict's event kinds.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

FOMC_PAGE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_PAGE = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

MON3 = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                         "nov", "dec"])}


def fomc_dates(page_html: str) -> list[str]:
    """Decision days (the last day of each scheduled meeting) as ISO dates."""
    out = []
    parts = re.split(r"(\d{4}) FOMC Meetings", page_html)
    for i in range(1, len(parts) - 1, 2):
        year, body = int(parts[i]), parts[i + 1]
        months = re.findall(r'fomc-meeting__month[^>]*>\s*(?:<strong>)?\s*([A-Za-z/]+)', body)
        days = re.findall(r'fomc-meeting__date[^>]*>\s*([^<]+)<', body)
        for mon, d in zip(months, days):
            if re.search(r"notation|unscheduled|cancel", d, flags=re.I):
                continue
            nums = re.findall(r"\d{1,2}", d)
            if not nums:
                continue
            m = MON3.get(mon.split("/")[-1].strip().lower()[:3])
            if m:
                out.append(f"{year:04d}-{m:02d}-{int(nums[-1]):02d}")
    return sorted(set(out))


def ecb_dates(page_html: str) -> list[str]:
    """Decision days (day 2 of each monetary policy meeting) as ISO dates."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page_html))
    out = []
    for d, m, y in re.findall(
            r"(\d{2})/(\d{2})/(\d{4}) Governing Council of the ECB: monetary policy meeting[^/]*?\(Day 2\)", text):
        out.append(f"{y}-{m}-{d}")
    return sorted(set(out))


def build_events(today: date, fomc: list[str], ecb: list[str], fao: list[str], fao_next_period: str | None,
                 days_ahead: int = 180) -> list[dict]:
    lo, hi = today.isoformat(), (today + timedelta(days=days_ahead)).isoformat()
    ev = []
    for d in fomc:
        if lo <= d <= hi:
            ev.append({"id": f"{d}-fomc-decision", "date": d, "kind": "rule_date", "countries": ["US"], "ref": "FOMC",
                       "title": "Federal Reserve FOMC rate decision",
                       "source": {"publisher": "Board of Governors of the Federal Reserve System", "url": FOMC_PAGE}})
    for d in ecb:
        if lo <= d <= hi:
            ev.append({"id": f"{d}-ecb-decision", "date": d, "kind": "rule_date", "countries": [], "ref": "ECB",
                       "title": "ECB Governing Council monetary policy decision",
                       "source": {"publisher": "European Central Bank", "url": ECB_PAGE}})
    upcoming_fao = [d for d in fao if lo <= d <= hi]
    for i, d in enumerate(upcoming_fao):
        label = f" ({fao_next_period} data)" if i == 0 and fao_next_period else ""
        ev.append({"id": f"{d}-fao-ffpi-release", "date": d, "kind": "data_release", "countries": [], "ref": "FFPI",
                   "title": f"FAO Food Price Index monthly release{label}",
                   "source": {"publisher": "FAO",
                              "url": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"}})
    ev.sort(key=lambda e: (e["date"], e["id"]))
    return ev


def question_drafts(fao_measures: list[dict], next_release: str | None) -> list[dict]:
    """Draft Verdict questions with a naive baseline. Drafts only: Tom sets the number and registers."""
    out = []
    for m in fao_measures:
        if m["id"] not in ("ffpi", "cereals") or not next_release:
            continue
        y, mo = int(m["period"][:4]), int(m["period"][5:7])
        nxt = f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"
        out.append({
            "draft_id": f"headwind-{m['id']}-{nxt}",
            "question": f"Will the {m['name']} for {nxt}, as first published, be above {m['value']} "
                        f"(the {m['period']} value as published on the day this draft was written)?",
            "resolves_on": next_release,
            "resolution_source": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
            "baseline": {
                "kind": "climatology",
                "probability": m["rose_share_120m"],
                "basis": "Share of the last 120 months in which the index rose from the month before, "
                         "in today's revised series.",
            },
            "caveat": "FAO revises earlier months; the comparison value can change before the release.",
            "status": "draft, not registered",
        })
    return out
