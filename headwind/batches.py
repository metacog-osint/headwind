"""Designation batches: is the set of entries a change adds to a list unusually large for that list?

A batch is the entries a list gives one designation date. The EU (`designationDate`), the UK (`DateDesignated`),
the UN (`LISTED_ON`) and the trade.gov screening lists (`start_date`; the Entity List among them) carry that date
on each entry, so a change Headwind sees can be measured against the list's own earlier batches, read from the
same file: the size of each designation date among the entries added (all entries on the list with that date,
now), against the sizes of the BATCH_WINDOW designation dates before it.

OFAC's sdn.csv carries no designation date, so for OFAC (and for any list whose added entries carry none) the batch
is what Headwind saw added between two of its own readings, measured against the earlier changes it saw
(`added_history` in the run state). That baseline starts empty: no z until stats.MIN_BASELINE changes are kept.

The measure is the same robust z as everywhere in Headwind (median and MAD), on the logarithm of the batch size,
because batch sizes run from one entry to hundreds. A batch is unusual only upward: z >= stats.Z_ANOMALY and at
least BATCH_FLOOR entries. A small batch is never flagged.

Limits: past batches are counted from today's file, so entries since removed are missing from them (an older
batch looks smaller than it was). A batch spread over two of Headwind's readings is measured on each.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

from . import stats

BATCH_WINDOW = 60       # earlier designation dates (or earlier changes seen) a batch is measured against
BATCH_FLOOR = 10        # a batch smaller than this is never unusual
LOG_FLOOR = math.log(2.0)   # the scale is never below log(2) / Z_ANOMALY: a list whose batches are all one size
HISTORY_KEEP = 120      # changes seen kept per list, for the lists without designation dates


def _score(size: int, base_sizes: list[int]) -> dict:
    z = rate = None
    base = [math.log(b) for b in base_sizes if b > 0]
    if len(base) >= stats.MIN_BASELINE and size > 0:
        med = statistics.median(base)
        scale = max(1.4826 * statistics.median(abs(b - med) for b in base), LOG_FLOOR / stats.Z_ANOMALY)
        z = (math.log(size) - med) / scale
        rate = sum(1 for b, n in zip(base, base_sizes) if (b - med) / scale >= stats.Z_ANOMALY
                   and n >= BATCH_FLOOR) / len(base)
    return {"z": None if z is None else round(z, 2), "baseline_n": len(base),
            "flag_rate": None if rate is None else round(rate, 3),
            "anomaly": bool(z is not None and z >= stats.Z_ANOMALY and size >= BATCH_FLOOR)}


def dated(added: list[str], dates: dict[str, str | None]) -> list[dict]:
    """One record per designation date among the added entries."""
    sizes = Counter(d for d in dates.values() if d)
    seen = Counter(dates.get(i) for i in added if dates.get(i))
    days = sorted(sizes)
    out = []
    for day, n_added in sorted(seen.items()):
        earlier = [sizes[d] for d in days if d < day][-BATCH_WINDOW:]
        out.append({"basis": "designation date", "date": day, "added": n_added, "size": sizes[day],
                    **_score(sizes[day], earlier)})
    return out


def seen(added: int, history: list[int], detected_at: str) -> dict:
    """A change's additions as one batch, against the earlier changes Headwind saw on the list."""
    return {"basis": "headwind readings", "date": detected_at[:10], "added": added, "size": added,
            **_score(added, [h for h in history if h > 0][-BATCH_WINDOW:])}


def measure(added: list[str], dates: dict[str, str | None] | None, history: list[int] | None,
            detected_at: str) -> list[dict]:
    """The batches in one change: by designation date where the added entries carry one, else as Headwind saw it."""
    if not added:
        return []
    if dates and any(dates.get(i) for i in added):
        return dated(added, dates)
    return [seen(len(added), history or [], detected_at)]


def remember(history: list[int] | None, added: int) -> list[int]:
    out = list(history or [])
    if added > 0:
        out.append(added)
    return out[-HISTORY_KEEP:]


def text(batches: list[dict]) -> str:
    """One sentence on a change's batches, for the feed."""
    if not batches:
        return ""
    bits = []
    for b in batches:
        z = "no baseline yet" if b["z"] is None else f"z {b['z']:+.1f}"
        if b["basis"] == "designation date":
            bits.append(f"{b['date']}: {b['size']} entries on the list carry that designation date, {b['added']} of them "
                        f"added in this change ({z} against the list's {b['baseline_n']} earlier designation dates"
                        f"{', unusual' if b['anomaly'] else ''})")
        else:
            bits.append(f"{b['added']} added at once ({z} against the {b['baseline_n']} earlier changes Headwind saw on "
                        f"this list{', unusual' if b['anomaly'] else ''})")
    return " Designation batches: " + "; ".join(bits) + "."
