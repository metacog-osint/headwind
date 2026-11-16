"""UN Security Council sanctions committee press releases: counted and linked, never quoted.

Source: the UN's Meetings Coverage and Press Releases RSS feed (press.un.org/en/rss.xml), the only feed found on
15 Nov 2026 (a Security Council feed was not found; the listing pages and older release pages sit behind a bot
challenge, so Headwind does not walk release numbers). The UN's terms of use allow personal, non-commercial use
and no redistribution, so Headwind keeps and publishes a release's document number, date and link only, as it does
with the UN list. The title is read to decide whether a release is a sanctions committee's and is not kept.

**The feed can drop releases.** It holds the 10 newest releases of every UN body. On 13 Nov 2026 they spanned
about 7 hours; ten Wayback copies from 2026 spanned 4 hours to 3 days. Headwind runs every 4 to 9 hours, so on a
busy day a committee release can come and go between two runs (SC/16488 of 26 Oct 2026, "... Sanctions Committee
Removes Three Entries", was no longer in the feed copied on 27 Oct). Each run therefore states whether the feed's
oldest item is newer than the run before (`may_have_missed`). The committees' list changes themselves are seen on
the UN list (sanctions lane), which does not depend on this feed.
"""
from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FEED = "https://press.un.org/en/rss.xml"
PAGE = "https://press.un.org/en"
KEEP_DAYS = 60          # releases kept in the snapshot
FEED_DAYS = 14          # releases in the feed
MIN_ITEMS = 3           # fewer parsed items than this is a broken read, not a quiet day

_SC_DOC = re.compile(r"/(sc)(\d{4,6})\.doc\.htm$", re.IGNORECASE)
# A Security Council sanctions committee names itself "... Sanctions Committee ..." or "Security Council Committee
# (established) pursuant to resolution N"; the 1540 (non-proliferation) and Counter-Terrorism (1373) committees
# are not sanctions committees.
_COMMITTEE = re.compile(r"\bSanctions\s+Committee\b|\bCommittee\s+(?:established\s+)?pursuant\s+to\s+resolution\s+(\d{3,4})",
                        re.IGNORECASE)
NOT_SANCTIONS = {"1540", "1373"}


def _utc(text: str | None) -> str | None:
    try:
        dt = parsedate_to_datetime((text or "").strip())
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(body: bytes) -> list[dict]:
    """Every item in the feed: link, publication time (UTC) and title (for the test only). The UN's server sends the
    feed gzipped even when not asked (seen 16 Nov 2026), so a gzip body is opened first."""
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"the UN press feed is not XML (a bot challenge page?): {exc}") from exc
    items = [{"link": (i.findtext("link") or "").strip(), "published": _utc(i.findtext("pubDate")),
              "title": " ".join((i.findtext("title") or "").split())} for i in root.iter("item")]
    if len(items) < MIN_ITEMS:
        raise ValueError(f"the UN press feed gave {len(items)} items")
    return items


def committee_release(item: dict) -> dict | None:
    """A Security Council sanctions committee's release as Headwind keeps it: document number, date and link."""
    m = _SC_DOC.search(item["link"])
    c = _COMMITTEE.search(item["title"])
    if not m or not c or (c.group(1) or "") in NOT_SANCTIONS or not item.get("published"):
        return None
    return {"id": f"SC/{m.group(2)}", "published": item["published"], "url": item["link"]}


def coverage(items: list[dict], last_read: str | None, now: str) -> dict:
    """How far back the feed reached on this reading, and whether that leaves a gap after the reading before."""
    times = sorted(t for t in (i.get("published") for i in items) if t)
    oldest = times[0] if times else None
    return {"items": len(items), "oldest": oldest, "newest": times[-1] if times else None,
            "previous_read": last_read, "checked_at": now,
            "may_have_missed": bool(last_read and oldest and oldest > last_read)}


def merge(previous: list[dict], found: list[dict], now: str) -> list[dict]:
    """Releases kept for KEEP_DAYS, newest first, each with the time Headwind first saw it."""
    cutoff = (datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {r["id"]: r for r in previous or [] if r.get("published", "") >= cutoff}
    for r in found:
        if r["id"] not in out and r["published"] >= cutoff:
            out[r["id"]] = {**r, "seen_at": now}
    return sorted(out.values(), key=lambda r: (r["published"], r["id"]), reverse=True)
