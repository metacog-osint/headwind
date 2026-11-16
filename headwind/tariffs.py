"""US tariff schedule revisions (USITC) and tariff actions signed but not yet in the Federal Register (White House).

- The US International Trade Commission publishes each revision of the Harmonized Tariff Schedule (HTS) in a
  release list (keyless JSON): its name, the day it was posted and the day it took effect. A revision is how a
  proclamation's tariff changes reach the schedule. Headwind counts revisions per 28 days against its own history,
  as it counts tariff actions (controls.pace). The list names the staff member who posted each revision; that name
  is never kept.
- The White House's presidential-actions feed (RSS) carries a document on the day it is signed, days before the
  Federal Register publishes it. Tariff actions in it that the Federal Register does not yet carry are listed as
  signed, not yet published. Titles are the White House's own.

Facts as published; nothing here says what a tariff will do.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

from . import controls

HTS_RELEASES = "https://hts.usitc.gov/reststop/releaseList"
HTS_PAGE = "https://hts.usitc.gov/"
WH_FEED = "https://www.whitehouse.gov/presidential-actions/feed/"
WH_PAGE = "https://www.whitehouse.gov/presidential-actions/"
HTS_FLOOR = 3             # revisions: fewer than this in a window is never unusual
HTS_SHOWN = 12            # revisions kept in the snapshot
SIGNED_DAYS = 30          # a signed action is listed this long, or until the Federal Register carries it
FEED_DAYS = 14            # a revision stays in the feed this long after it was posted


def _us_date(s: str | None) -> str | None:
    """USITC writes dates as MM/DD/YYYY."""
    try:
        return datetime.strptime((s or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def parse_releases(body: bytes | str) -> list[dict]:
    """Every HTS revision in the list, newest first: name, title, posted, in effect from and to, status."""
    import json
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("USITC release list is not a list")
    out = []
    for r in rows:
        posted = _us_date(r.get("date"))
        if not r.get("name") or not posted:
            continue
        out.append({"name": r["name"], "title": " ".join((r.get("title") or r.get("description") or r["name"]).split()),
                    "posted": posted, "in_effect_from": _us_date(r.get("releaseStartDate")),
                    "in_effect_to": _us_date(r.get("releaseEndDate")), "status": r.get("status")})
    if len(out) < 20:
        raise ValueError(f"USITC release list parsed short ({len(out)} revisions)")
    out.sort(key=lambda x: (x["posted"], x["name"]), reverse=True)
    return out


def hts_pace(releases: list[dict], today: date) -> dict:
    """Revisions posted in the last 28 days against the 27 windows before (controls.pace's rule, 3 at least)."""
    docs = [{"id": r["name"], "published_date": r["posted"]} for r in releases]
    return controls.pace(docs, today, floor=HTS_FLOOR)


def year_counts(releases: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in releases:
        out[r["posted"][:4]] = out.get(r["posted"][:4], 0) + 1
    return dict(sorted(out.items()))


def parse_signed(body: bytes | str, today: date, days: int = SIGNED_DAYS) -> list[dict]:
    """Tariff actions in the White House's presidential-actions feed of the last `days`: title, link, date."""
    root = ET.fromstring(body if isinstance(body, bytes) else body.encode("utf-8"))
    lo = (today - timedelta(days=days)).isoformat()
    out = []
    for item in root.iter("item"):
        title = " ".join((item.findtext("title") or "").split())
        link = (item.findtext("link") or "").strip()
        try:
            when = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            continue
        if when >= lo and controls.is_tariff(title) and link.startswith("https://www.whitehouse.gov/"):
            out.append({"title": title, "url": link, "date": when})
    out.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    return out


def _norm(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))


def mark_published(signed: list[dict], docs: list[dict]) -> list[dict]:
    """Each signed action gets `fr_document` when a presidential document in the Federal Register has the same
    title (case and punctuation aside), else None: signed, not yet published."""
    by_title = {_norm(d["title"]): d["id"] for d in docs if d.get("agency") == "President"}
    for s in signed:
        s["fr_document"] = by_title.get(_norm(s["title"]))
    return signed


def recent(releases: list[dict], generated_at: str, days: int = FEED_DAYS) -> list[dict]:
    cutoff = (datetime.fromisoformat(generated_at.replace("Z", "+00:00")) - timedelta(days=days)).date().isoformat()
    return [r for r in releases if r["posted"] >= cutoff]

