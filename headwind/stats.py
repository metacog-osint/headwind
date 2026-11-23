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

import math
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


def exceedance(value: float, base: list[float], centre: float) -> float:
    """The share of the baseline at least as far from its centre as `value`, counting this reading: (k + 1) / (n + 1),
    rounded up, so it is never finer than one in n + 1 (contract revision 2.1, `signal.exceedance`)."""
    k = sum(1 for b in base if abs(b - centre) >= abs(value - centre))
    return min(1.0, math.ceil((k + 1) / (len(base) + 1) * 10000) / 10000)


def score(value: float, base: list[float], floor: float) -> dict:
    """z, anomaly flag and flag_rate for `value` against `base`; `floor` is in the same units as value."""
    z = rate = expected = rarity = None
    if len(base) >= MIN_BASELINE:
        med = statistics.median(base)
        expected, rarity = round(med * 100.0, 2), exceedance(value, base, med)
        scale = max(1.4826 * statistics.median(abs(b - med) for b in base), floor / Z_ANOMALY)
        if scale > 0:
            z = (value - med) / scale
            rate = sum(1 for b in base if abs((b - med) / scale) >= Z_ANOMALY and abs(b) >= floor) / len(base)
    return {
        "z": None if z is None else round(z, 2),
        "baseline_n": len(base),
        "flag_rate": None if rate is None else round(rate, 3),
        "expected": expected,        # the baseline's median, in percent
        "exceedance": rarity,
        "anomaly": bool(z is not None and abs(z) >= Z_ANOMALY and abs(value) >= floor),
    }


RANK_TOP = 0.05      # food lanes: a rise in the top 5% of the series' own baseline
RUN_MIN = 6          # food lanes: the reading has risen this many months in a row


def rank_run(value: float, base: list[float], history: list[float], floor: float) -> dict:
    """Two rules beside z for the food lanes (Tom's yes, 16 Nov 2026, from the 15 Nov suite review: Sudan's food
    prices rose a median 50% in three months, the seventh straight monthly rise and the third-highest reading in five
    years, and z could not flag it because the baseline itself trends and has fat tails).

    rank: value is above the 95th percentile of `base` and a rise of at least `floor`.
    run:  `history` (the readings in time order, ending with `value`) rose RUN_MIN or more times in a row, and value
          is a rise of at least `floor`.
    flag_rate_rules is how often z, rank or run would have fired on the baseline's own readings (rank judged against
    the same baseline)."""
    out = {"rank_share_above": None, "rank": False, "rise_run": 0, "run": False, "flag_rate_rules": None}
    run = 0
    for a, b in zip(reversed(history[:-1]), reversed(history)):
        if b > a:
            run += 1
        else:
            break
    out["rise_run"] = run
    out["run"] = bool(run >= RUN_MIN and value >= floor)
    if len(base) >= MIN_BASELINE:
        cut = statistics.quantiles(base, n=20)[-1]
        out["rank_share_above"] = round(sum(1 for b in base if b > value) / len(base), 3)
        out["rank"] = bool(value > cut and value >= floor)
        med = statistics.median(base)
        scale = max(1.4826 * statistics.median(abs(b - med) for b in base), floor / Z_ANOMALY)
        # Where the baseline sits in history (a contiguous stretch), so each baseline reading's own run is known.
        start = next((i for i in range(len(history) - len(base), -1, -1) if history[i:i + len(base)] == base), None)
        fired = 0
        for j, b in enumerate(base):
            z_hit = scale > 0 and abs((b - med) / scale) >= Z_ANOMALY and abs(b) >= floor
            r_hit = b > cut and b >= floor
            n_hit = False
            if start is not None:
                k, r = start + j, 0
                while k - r - 1 >= 0 and history[k - r] > history[k - r - 1]:
                    r += 1
                n_hit = r >= RUN_MIN and b >= floor
            fired += 1 if (z_hit or r_hit or n_hit) else 0
        out["flag_rate_rules"] = round(fired / len(base), 3)
    return out


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
