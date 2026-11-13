"""Offline tests for Headwind. Fixtures under tests/fixtures are cut from real source files fetched 12-13 Nov 2026.

The two sanctions-list fixtures keep each entry's id, type and program only; names and remarks are blanked.
"""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import baseline, controls, feed, food, markets, releases, sanctions, stats  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

_spec = importlib.util.spec_from_file_location("headwind_cli", ROOT / "tools" / "headwind.py")
headwind_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(headwind_cli)

# The real lists hold thousands of entries; the fixtures hold a few dozen.
for _l in sanctions.LISTS.values():
    _l["min_entries"] = 5


def text(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8-sig")


def fake_getter(url: str, timeout: int = 60) -> bytes:
    """Serve fixtures in place of the network."""
    if "eurofxref-hist.zip" in url:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("eurofxref-hist.csv", text("ecb.csv"))
        return buf.getvalue()
    table = [("fredgraph.csv", "fred.csv"), ("foodpricesindex", "fao_page.html"),
             ("food_price_indices_data.csv", "fao.csv"), ("package_search", "hdx.json"),
             ("wfp_food_prices_sdn.csv", "wfp_sdn.csv"), ("api.worldbank.org", "worldbank.json"),
             ("fomccalendars", "fomc.html"), ("calendars/mgcgc", "ecb_calendar.html"),
             ("ofac/downloads/sdn.csv", "ofac_sdn.csv"), ("scsanctions.un.org", "un_consolidated.xml"),
             ("federalregister.gov", "federal_register.json")]
    for needle, name in table:
        if needle in url:
            return (FIX / name).read_bytes()
    raise OSError(f"no fixture for {url}")


def lint(fc: dict) -> list[str]:
    regs = registers.ids(ROOT / "doctrine")
    return [f"{f['properties']['id']}: {m}" for f in fc["features"]
            for _, sev, m in contract.check(f, regs) if sev == "error"]


class TestStats(unittest.TestCase):
    def test_a_past_spike_does_not_hide_the_next(self):
        vals = [100.0 + (i % 5) * 0.2 for i in range(300)]
        vals[100] = 160.0                       # an old spike that would inflate a standard deviation
        vals[-1] = vals[-2] * 1.12
        m = stats.measure([(str(i), v) for i, v in enumerate(vals)], 1, 250, 5.0)
        self.assertTrue(m["anomaly"])
        self.assertGreater(m["z"], stats.Z_ANOMALY)
        self.assertGreater(m["flag_rate"], 0)   # the old spike is counted in the usual flag rate

    def test_floor_keeps_a_pegged_series_quiet(self):
        vals = [7.80 + (0.0001 if i % 2 else 0.0) for i in range(300)]
        vals[-1] = 7.81                          # a huge z on a 0.1% move
        m = stats.measure([(str(i), v) for i, v in enumerate(vals)], 1, 250, 1.0)
        self.assertFalse(m["anomaly"])

    def test_thin_baseline_gives_no_z(self):
        m = stats.measure([(str(i), 1.0 + i / 100) for i in range(10)], 1, 250, 1.0)
        self.assertIsNone(m["z"])
        self.assertFalse(m["anomaly"])


class TestParsers(unittest.TestCase):
    def test_ecb(self):
        series = markets.parse_ecb_csv(text("ecb.csv"))
        self.assertNotIn("USD", series)
        self.assertIn("EUR", series)
        self.assertIn("TRY", series)
        fx = markets.measure_fx(series)
        self.assertGreaterEqual(len(fx), 25)
        tr = next(f for f in fx if f["currency"] == "TRY")
        self.assertEqual(tr["country"], "TR")
        self.assertGreater(tr["per_usd"], 1)
        self.assertEqual(tr["baseline_n"], 250)

    def test_fred(self):
        en = markets.measure_energy(markets.parse_fred_csv(text("fred.csv")))
        self.assertEqual({e["id"] for e in en}, {"brent", "wti", "henry-hub"})
        self.assertTrue(all(e["price"] > 0 for e in en))

    def test_fao(self):
        page = text("fao_page.html")
        self.assertIn("food_price_indices_data.csv", food.fao_csv_url(page))
        self.assertNotIn("&amp;", food.fao_csv_url(page))
        self.assertIn("2026-12-04", food.fao_release_dates(page))
        fao = food.measure_fao(food.parse_fao_csv(text("fao.csv")))
        ffpi = next(m for m in fao if m["id"] == "ffpi")
        self.assertEqual((ffpi["period"], ffpi["value"], ffpi["prior_value"]), ("2026-10", 133.9, 135.6))
        self.assertEqual(len(ffpi["as_issued"]), 12)
        self.assertEqual(food.next_period("2026-12"), "2027-01")

    def test_wfp(self):
        res = food.hdx_resources(json.loads(text("hdx.json")))
        self.assertIn("SDN", res)
        m = food.measure_wfp(text("wfp_sdn.csv"), "2026-11")
        self.assertEqual(m["period"], "2026-09")
        self.assertAlmostEqual(m["median_change_pct"], 50.1, places=1)
        self.assertGreaterEqual(m["series"], food.WFP_MIN_SERIES)
        self.assertFalse(m["stale"])
        self.assertTrue(food.measure_wfp(text("wfp_sdn.csv"), "2027-06")["stale"])
        self.assertIsNone(food.measure_wfp("date,price\n", "2026-11"))

    def test_calendars(self):
        fomc = releases.fomc_dates(text("fomc.html"))
        self.assertIn("2026-12-09", fomc)
        self.assertIn("2024-05-01", fomc)        # "Apr/May 30-1"
        self.assertIn("2023-02-01", fomc)        # "Jan/Feb 31-1"
        self.assertNotIn("2025-08-22", fomc)     # a notation vote is not a meeting
        ecb = releases.ecb_dates(text("ecb_calendar.html"))
        self.assertIn("2026-12-17", ecb)
        ev = releases.build_events(date(2026, 11, 13), fomc, ecb, ["2026-11-06", "2026-12-04"], "2026-11")
        self.assertEqual(ev[0]["id"], "2026-12-04-fao-ffpi-release")
        self.assertTrue(all("2026-11-13" <= e["date"] <= "2027-05-12" for e in ev))
        for e in ev:
            self.assertTrue(all(k in e for k in ("id", "date", "title", "kind", "countries", "source", "ref")))
            self.assertIn(e["kind"], ("data_release", "rule_date"))

    def test_world_bank(self):
        rows = baseline.parse_wb(text("worldbank.json"), {"TR", "SD", "US"}, this_year=2026)
        self.assertIn("TR", rows)
        self.assertNotIn("1W", rows)             # aggregates dropped
        old = json.dumps([{}, [{"country": {"id": "SD"}, "date": "1999", "value": 865.87}]])
        self.assertEqual(baseline.parse_wb(old, {"SD"}, this_year=2026), {})


class TestFeed(unittest.TestCase):
    def snapshot(self) -> dict:
        m = {"date": "2026-11-12", "prior_date": "2026-11-05", "change_pct": 9.4, "z": 6.2, "baseline_n": 250,
             "flag_rate": 0.012, "anomaly": True}
        return {
            "generated_at": "2026-11-13T05:00:00Z", "lanes": {"fx": {"fetched_at": "2026-11-13T05:00:00Z"}},
            "sanctions": [], "controls": [],
            "fx": [{"currency": "TRY", "country": "TR", "per_usd": 46.1, "prior_per_usd": 42.1, "direction": "weaker", **m},
                   {"currency": "EUR", "country": None, "per_usd": 0.9, "prior_per_usd": 0.9, "direction": "unchanged",
                    **{**m, "change_pct": 0.0, "z": 0.0, "anomaly": False}}],
            "energy": [{"id": "brent", "name": "Brent crude oil spot price", "unit": "US dollars per barrel",
                        "price": 107.4, "prior_price": 90.0, **{**m, "change_pct": 19.3}}],
            "fao": [{"id": "cereals", "name": "FAO Cereal Price Index", "period": "2026-10", "value": 116.8,
                     "prior_period": "2026-09", "prior_value": 100.0, "change_pct": 16.8, "z": 5.0, "baseline_n": 120,
                     "flag_rate": 0.0, "anomaly": True}],
            "local_food": [
                {"country": "SD", "period": "2026-09", "median_change_pct": 50.1, "series": 159, "markets": 19,
                 "share_rising": 0.9, "z": 4.1, "baseline_n": 60, "flag_rate": 0.05, "stale": False, "anomaly": True,
                 "dataset": "https://data.humdata.org/dataset/wfp-food-prices-for-sudan"},
                {"country": "VE", "period": "2025-05", "median_change_pct": 8.3, "series": 957, "markets": 51,
                 "share_rising": 0.7, "z": 1.7, "baseline_n": 26, "flag_rate": 0.0, "stale": True, "anomaly": False}],
        }

    def test_anomalies_pass_the_linter_and_stay_measurements(self):
        fc = feed.build_feed(self.snapshot())
        self.assertEqual(lint(fc), [])
        ids = [f["properties"]["id"] for f in fc["features"]]
        self.assertNotIn("headwind:localfood:VE:2025-05", ids)      # stale data is not published as current
        self.assertEqual(len(ids), 5)
        for f in fc["features"]:
            p = f["properties"]
            self.assertEqual(p["kind"], "observation")
            self.assertNotIn("probability", p)
            self.assertLessEqual(p["data_as_of"], p["published_at"])  # never dated in the future
        tr = next(f for f in fc["features"] if f["properties"]["id"].startswith("headwind:fx:TRY"))
        self.assertEqual(tr["properties"]["tier"], "anomaly")
        self.assertTrue(tr["properties"]["baseline_ref"])
        self.assertEqual(tr["geometry"]["type"], "Point")
        eur = next(f for f in fc["features"] if f["properties"]["id"].startswith("headwind:fx:EUR"))
        self.assertIsNone(eur["geometry"])
        self.assertEqual(eur["properties"]["precision_class"], "none")

    def test_list_changes_and_rules_are_counts_and_published_facts(self):
        snap = self.snapshot()
        old = sanctions.parse_sdn_csv(text("ofac_sdn.csv"))
        new = dict(old)
        del new["36"]
        new["99999"] = ["vessel", ["RUSSIA-EO14024"]]
        new["99998"] = ["entity", ["IRAN-EO13902", "SDGT"]]
        d = sanctions.delta("ofac-sdn", old, new, "2026-11-13T04:00:00Z", "2026-11-12T04:00:00Z")
        self.assertEqual((d["added"], d["removed"], d["total"]), (2, 1, len(old) + 1))
        self.assertEqual(d["added_by_type"], {"entity": 1, "vessel": 1})
        self.assertEqual(d["countries"], ["CU", "IR", "RU"])       # the removed entry was under CUBA
        self.assertIsNone(sanctions.delta("ofac-sdn", old, old, "2026-11-13T04:00:00Z", None))
        stale = {**d, "id": "ofac-sdn:old", "detected_at": "2026-10-01T00:00:00Z"}
        snap["sanctions"] = sanctions.roll([stale], [d], "2026-11-13T05:00:00Z")
        self.assertEqual([x["id"] for x in snap["sanctions"]], [d["id"]])            # 30 days and it is dropped
        snap["controls"] = controls.parse_fr(text("federal_register.json"))
        fc = feed.build_feed(snap)
        self.assertEqual(lint(fc), [])
        props = {f["properties"]["id"]: f["properties"] for f in fc["features"]}
        s = props[f"headwind:sanctions:{d['id']}"]
        self.assertEqual((s["kind"], s["tier"], s["measures"]["vessels_added"]), ("observation", "routine", 1))
        rules = [i for i in props if i.startswith("headwind:control:")]
        self.assertEqual(rules, ["headwind:control:2026-22793"])   # only the last 14 days reach the feed
        for p in props.values():
            self.assertNotIn("probability", p)
            self.assertNotIn("likelihood_term", p)

    def test_a_cut_short_list_is_an_error_not_a_mass_delisting(self):
        old = sanctions.parse_sdn_csv(text("ofac_sdn.csv"))
        half = dict(list(old.items())[:10])
        with self.assertRaises(ValueError):
            sanctions.check_size("ofac-sdn", half, old)
        with self.assertRaises(ValueError):
            sanctions.check_size("ofac-sdn", {}, None)


class TestListParsers(unittest.TestCase):
    def test_sdn(self):
        idx = sanctions.parse_sdn_csv(text("ofac_sdn.csv"))
        self.assertEqual(len(idx), 36)
        self.assertEqual(idx["36"], ["entity", ["CUBA"]])           # a blank type is an entity
        kinds = {v[0] for v in idx.values()}
        self.assertEqual(kinds, {"entity", "individual", "vessel", "aircraft"})
        self.assertTrue(any(len(v[1]) > 1 for v in idx.values()))   # "[A] [B]" splits into two programs
        self.assertEqual(sanctions.countries_for(["RUSSIA-EO14024", "SDGT", "DPRK3"]), ["KP", "RU"])

    def test_un(self):
        generated, idx = sanctions.parse_un_xml((FIX / "un_consolidated.xml").read_bytes())
        self.assertEqual(generated[:10], "2026-11-13")
        self.assertEqual(len(idx), 14)
        self.assertEqual(idx["6907993"], ["individual", ["DRC"]])

    def test_federal_register(self):
        rules = controls.parse_fr(text("federal_register.json"))
        self.assertEqual(len(rules), 5)
        stay = next(r for r in rules if r["id"] == "2026-22793")
        self.assertEqual((stay["agency"], stay["effective_on"], stay["named_dates"]), ("BIS", "2026-11-09", ["2027-01-10"]))
        self.assertEqual(next(r for r in rules if r["id"] == "2026-20831")["countries"], ["VE"])
        ev = controls.build_events(rules, date(2026, 11, 13))
        self.assertEqual([e["id"] for e in ev], ["2026-12-03-fr-2026-19537", "2027-01-10-fr-2026-22793"])
        self.assertTrue(all(e["kind"] == "rule_date" for e in ev))
        self.assertIn("fields%5B%5D=dates", controls.fr_url(date(2026, 11, 13)))
        with self.assertRaises(ValueError):                         # a truncated page is not passed off as complete
            controls.parse_fr(json.dumps({"count": 9, "results": json.loads(text("federal_register.json"))["results"]}))


class TestEndToEnd(unittest.TestCase):
    def test_doctrine_registers_pass(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_collect_build_check_offline(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src")
            snap = headwind_cli.collect(tmp, getter=fake_getter)
            self.assertEqual({k: v["status"] for k, v in snap["lanes"].items()}, dict.fromkeys(headwind_cli.LANES, "ok"))
            self.assertEqual([w["country"] for w in snap["local_food"]], ["SD"])
            self.assertTrue(any(m["reason"].startswith("no WFP") for m in snap["local_food_missing"]))
            self.assertTrue((tmp / "data" / "raw" / "index.jsonl").exists())
            self.assertEqual(snap["sanctions"], [])                 # the first run only sets the baseline
            self.assertEqual([l["total"] for l in snap["sanctions_lists"]], [36, 14])
            self.assertEqual(len(snap["controls"]), 5)
            self.assertTrue((tmp / "data" / "state" / "sanctions_index.json").exists())
            files = headwind_cli.build_site(tmp)
            for name in ("data/feed.geojson", "data/events.json", "data/baseline.json", "data/question_drafts.json",
                         "index.html"):
                self.assertIn(name, files)
            self.assertEqual(headwind_cli.check_all(tmp), [])

            # A source that fails keeps its last good copy and says so; nothing is invented.
            def broken(url, timeout=60):
                if "eurofxref" in url:
                    raise OSError("down")
                return fake_getter(url, timeout)
            again = headwind_cli.collect(tmp, getter=broken)
            self.assertEqual(again["lanes"]["fx"]["status"], "failed")
            self.assertTrue(again["lanes"]["fx"]["from_previous"])
            self.assertEqual(again["fx"], snap["fx"])
            self.assertEqual(again["sanctions"], [])                # same lists, no change reported

            # A list that changes between runs is reported once, as counts.
            def changed(url, timeout=60):
                body = fake_getter(url, timeout)
                if "sdn.csv" in url:
                    lines = body.decode("utf-8").splitlines()[1:]
                    lines.append("99999,-0- ,vessel,RUSSIA-EO14024" + ",-0- " * 8)
                    return ("\n".join(lines) + "\n").encode("utf-8")
                return body
            third = headwind_cli.collect(tmp, getter=changed)
            self.assertEqual([(d["list"], d["added"], d["removed"]) for d in third["sanctions"]], [("ofac-sdn", 1, 1)])
            fourth = headwind_cli.collect(tmp, getter=changed)
            self.assertEqual(len(fourth["sanctions"]), 1)           # kept, not reported a second time
            headwind_cli.build_site(tmp)
            self.assertEqual(headwind_cli.check_all(tmp), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_first_run_failure_leaves_the_lane_empty(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            def down(url, timeout=60):
                raise OSError("down")
            snap = headwind_cli.collect(tmp, getter=down)
            self.assertTrue(all(v["status"] == "failed" and not v["from_previous"] for v in snap["lanes"].values()))
            self.assertEqual((snap["fx"], snap["energy"], snap["fao"], snap["local_food"]), ([], [], [], []))
            self.assertEqual((snap["sanctions"], snap["sanctions_lists"], snap["controls"]), ([], [], []))
            self.assertEqual(feed.build_feed(snap)["features"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
