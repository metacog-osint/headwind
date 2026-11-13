"""One anomaly measure for every Headwind series: the latest change against the series' own past changes.

For a series of (date, value) points in time order:
- change    = value now / value `horizon` observations ago - 1
- baseline  = the same change computed at each of the `window` observations before that, none of
              which overlaps the latest change
- z         = (change - median(baseline)) / (1.4826 * MAD(baseline))

The median and the median absolute deviation (MAD) are used in place of the mean and standard
deviation because price changes have fat tails: one past spike inflates a standard deviation
enough to hide the next one. 1.4826 scales the MAD to a standard deviation for normal data.

A series is an anomaly when |z| >= Z_ANOMALY and |change| >= the lane's floor. The floor stops a
pegged or very quiet series (a large z on a 0.05% move) from being flagged. For the same reason the
scale is never allowed below floor / Z_ANOMALY, so a nearly constant baseline cannot produce a z in
the hundreds.
flag_rate is the share of the baseline's own changes that the same rule would have flagged: how
often this series trips the rule in ordinary times.
The baseline is rolling. A fixed baseline is not kept yet (see doctrine/method.md).
"""
from __future__ import annotations

import statistics

Z_ANOMALY = 3.5
MIN_BASELINE = 24


def changes(values: list[float], horizon: int) -> list[float | None]:
    """Simple change over `horizon` steps for each index (None where it can't be computed)."""
    out: list[float | None] = []
    for i, v in enumerate(values):
        if i < horizon or values[i - horizon] is None or v is None or values[i - horizon] <= 0:
            out.append(None)
        else:
            out.append(v / values[i - horizon] - 1.0)
    return out


def score(value: float, base: list[float], floor: float) -> dict:
    """z, anomaly flag and flag_rate for `value` against `base`; `floor` is in the same units as value."""
    z = rate = None
    if len(base) >= MIN_BASELINE:
        med = statistics.median(base)
        scale = max(1.4826 * statistics.median(abs(b - med) for b in base), floor / Z_ANOMALY)
        if scale > 0:
            z = (value - med) / scale
            rate = sum(1 for b in base if abs((b - med) / scale) >= Z_ANOMALY and abs(b) >= floor) / len(base)
    return {
        "z": None if z is None else round(z, 2),
        "baseline_n": len(base),
        "flag_rate": None if rate is None else round(rate, 3),
        "anomaly": bool(z is not None and abs(z) >= Z_ANOMALY and abs(value) >= floor),
    }


def measure(points: list[tuple[str, float]], horizon: int, window: int, floor_pct: float) -> dict | None:
    """Latest change, its robust z-score against the rolling baseline, and whether it counts as an anomaly."""
    if len(points) <= horizon:
        return None
    values = [v for _, v in points]
    ch = changes(values, horizon)
    latest = ch[-1]
    if latest is None:
        return None
    base = [c for c in ch[max(0, len(ch) - horizon - window): len(ch) - horizon] if c is not None]
    return {
        "date": points[-1][0],
        "value": values[-1],
        "prior_date": points[-1 - horizon][0],
        "prior_value": values[-1 - horizon],
        "change_pct": round(latest * 100.0, 2),
        **score(latest, base, floor_pct / 100.0),
    }
