"""Feed contract revision 2.1 fields (headwind/contract21.py)."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from tic_doctrine import history  # noqa: E402

from headwind import contract21, stats  # noqa: E402


def item(item_id, data_as_of="2026-11-20T00:00:00Z", tier="routine"):
    return {"type": "Feature", "geometry": None, "properties": {
        "id": item_id, "tier": tier, "data_as_of": data_as_of, "published_at": "2026-11-23T12:00:00Z",
        "sources": [{"id": "src"}]}}


def change(stamp, detected, prior):
    return {"id": f"france-gels:{stamp}", "list": "france-gels", "detected_at": detected, "prior_checked_at": prior}


class Exceedance(unittest.TestCase):
    def test_never_finer_than_one_in_n_plus_one(self):
        base = [i / 1000 for i in range(28)]
        got = stats.exceedance(1.0, base, 0.0135)
        self.assertGreaterEqual(got, 1 / 29)
        self.assertLess(got, 1 / 29 + 0.0001)

    def test_score_reports_centre_and_share(self):
        base = [0.01 * (i % 5) for i in range(30)]
        s = stats.score(0.5, base, 0.01)
        self.assertEqual(s["expected"], 2.0)
        self.assertEqual(s["exceedance"], stats.exceedance(0.5, base, 0.02))

    def test_short_baseline_states_neither(self):
        s = stats.score(0.5, [0.01, 0.02], 0.01)
        self.assertIsNone(s["expected"])
        self.assertIsNone(s["exceedance"])


class Fields(unittest.TestCase):
    def test_series_window_and_signal(self):
        f = item("headwind:fx:BRL", tier="anomaly")
        snap = {"fx": [{"currency": "BRL", "date": "2026-11-20", "prior_date": "2026-11-13", "change_pct": 5.13,
                        "baseline_n": 250, "expected": 0.1, "exceedance": 0.004}]}
        contract21.apply([f], snap)
        p = f["properties"]
        self.assertEqual(p["subject_id"], "headwind:fx:BRL")
        self.assertEqual((p["event_start"], p["event_end"]), ("2026-11-13T00:00:00Z", "2026-11-20T00:00:00Z"))
        self.assertEqual(p["event_time_precision"], "day")
        self.assertEqual(p["signal"]["value"], 5.13)
        self.assertEqual(p["signal"]["exceedance"], 0.004)
        self.assertNotIn("last_change", p)      # from the history log

    def test_month_series(self):
        f = item("headwind:localfood:SD")
        contract21.apply([f], {"local_food": [{"country": "SD", "period": "2026-02"}]})
        self.assertEqual(f["properties"]["event_start"], "2025-11-01T00:00:00Z")
        self.assertEqual(f["properties"]["event_end"], "2026-02-01T00:00:00Z")
        self.assertEqual(f["properties"]["event_time_precision"], "month")

    def test_notice_takes_effect_and_states_no_end(self):
        f = item("headwind:control:2026-1")
        contract21.apply([f], {"controls": [{"id": "2026-1", "published_date": "2026-11-20",
                                             "effective_on": "2026-12-01"}]})
        self.assertEqual(f["properties"]["event_start"], "2026-12-01T00:00:00Z")
        self.assertNotIn("event_end", f["properties"])

    def test_health_dates_published_at_midnight_and_stored_copy_untouched(self):
        stored = {"ecb": {"data_as_of": "2026-11-23", "state": "fresh"}, "x": {"data_as_of": "2026-11-23T10:00:00Z"},
                  "y": {"data_as_of": None}}
        out = contract21.published_health(stored)
        self.assertEqual(out["ecb"]["data_as_of"], "2026-11-23T00:00:00Z")
        self.assertEqual(out["x"]["data_as_of"], "2026-11-23T10:00:00Z")
        self.assertIsNone(out["y"]["data_as_of"])
        self.assertEqual(stored["ecb"]["data_as_of"], "2026-11-23")


class ListChanges(unittest.TestCase):
    """Each list change is its own subject, so no change drops out of a log that has no reading key (COP's ledger)."""

    def feed(self, changes):
        feats = [item(f"headwind:sanctions:{c['id']}", c["detected_at"]) for c in changes]
        contract21.apply(feats, {"sanctions": changes})
        return {"type": "FeatureCollection", "features": feats}

    def test_two_changes_of_one_list_stay_apart(self):
        a = change("20261118T1539", "2026-11-18T15:39:00Z", "2026-11-18T09:00:00Z")
        b = change("20261118T1627", "2026-11-18T16:27:00Z", "2026-11-18T15:39:00Z")
        feed = self.feed([b, a])
        subjects = {f["properties"]["subject_id"] for f in feed["features"]}
        self.assertEqual(len(subjects), 2)
        p = feed["features"][1]["properties"]
        self.assertEqual((p["last_change"], p["last_change_at"]), ("new", "2026-11-18T15:39:00Z"))
        self.assertEqual((p["event_start"], p["event_end"]), ("2026-11-18T09:00:00Z", "2026-11-18T15:39:00Z"))

    def test_a_new_change_writes_a_line_without_a_reading_key(self):
        a = change("20261118T1539", "2026-11-18T15:39:00Z", "2026-11-18T09:00:00Z")
        b = change("20261118T1627", "2026-11-18T16:27:00Z", "2026-11-18T15:39:00Z")
        state, _ = history.update({}, self.feed([a]), None, datetime(2026, 11, 18, 16, tzinfo=timezone.utc))
        _, lines = history.update(state, self.feed([b, a]), None, datetime(2026, 11, 18, 17, tzinfo=timezone.utc))
        self.assertEqual([(x["change"], x["id"]) for x in lines], [("new", "headwind:sanctions:france-gels:20261118T1627")])


if __name__ == "__main__":
    unittest.main()
