"""Offline tests for Headwind. Fixtures under tests/fixtures are cut from real source files fetched 12-13 Nov 2026.

The sanctions-list and screening-list fixtures keep each entry's id, type, program and address country only;
names and remarks are blanked.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from unittest import mock
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import (baseline, batches, controls, feed, food, health, inspection, markets, minerals, releases,  # noqa: E402
                      sanctions, screening, stats, trade)
from tic_doctrine import contract, registers  # noqa: E402

_spec = importlib.util.spec_from_file_location("headwind_cli", ROOT / "tools" / "headwind.py")
headwind_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(headwind_cli)

os.environ["EIA_API_KEY"] = "test-key-not-real"      # the energy lane needs a key; the fixtures stand in for EIA
os.environ["CENSUS_API_KEY"] = "census-test-key-not-real"   # the same for the trade lane

# The real lists hold thousands of entries; the fixtures hold a few dozen.
for _l in sanctions.LISTS.values():
    _l["min_entries"] = 5
screening.MIN_ENTRIES = 5
screening.SHRINK_FLOOR = 4


def text(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8-sig")


def fake_getter(url: str, timeout: int = 60) -> bytes:
    """Serve fixtures in place of the network."""
    if "list+of+critical+minerals" in url:
        return (FIX / "fr_critical_minerals_lists.json").read_bytes()
    if "sciencebase.gov/catalog/items?" in url:
        return (FIX / "sciencebase_mcs_search_2027.json").read_bytes()
    if "eurofxref-hist.zip" in url:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("eurofxref-hist.csv", text("ecb.csv"))
        return buf.getvalue()
    if "public-inspection-documents.json" in url:
        day = re.search(r"available_on%5D=(\d{4}-\d{2}-\d{2})", url).group(1)
        f = FIX / f"fr_pi_{day}.json"
        return f.read_bytes() if f.exists() else b'{"count": 0, "results": []}'
    if "public-inspection/raw_text/" in url:
        digits = "".join(re.findall(r"\d+", url.split("raw_text/", 1)[1].rsplit(".", 1)[0]))
        f = FIX / f"fr_pi_raw_{digits[:4]}-{digits[4:]}.txt"
        if f.exists():
            return f.read_bytes()
        raise OSError(f"no fixture for {url}")
    if "federalregister.gov/api/v1/documents.json" in url and "type%5D%5B%5D=NOTICE" in url:
        return (FIX / ("fr_ustr_notices.json" if "fields%5B%5D=abstract" in url else "fr_register_ustr.json")).read_bytes()
    if "federalregister.gov/api/v1/documents.json" in url and "fields%5B%5D=abstract" not in url:
        return (FIX / "fr_register_rules.json").read_bytes()
    if "api.census.gov" in url:
        code = re.search(r"I_COMMODITY=(\d+)", url).group(1)
        f = FIX / f"census_{code}.json"
        return f.read_bytes() if f.exists() else b""         # Census answers 204, no body, for a code with no rows
    if "api.worldbank.org" in url and "source=15" in url:
        return (FIX / "worldbank_gem.json").read_bytes()
    table = [("petroleum/pri/spt", "eia_petroleum.json"), ("natural-gas/pri/fut", "eia_natural_gas.json"),
             ("foodpricesindex", "fao_page.html"),
             ("food_price_indices_data.csv", "fao.csv"), ("package_search", "hdx.json"),
             ("wfp_food_prices_sdn.csv", "wfp_sdn.csv"), ("api.worldbank.org", "worldbank.json"),
             ("fomccalendars", "fomc.html"), ("calendars/mgcgc", "ecb_calendar.html"),
             ("ofac/downloads/sdn.csv", "ofac_sdn.csv"), ("scsanctions.un.org", "un_consolidated.xml"),
             ("fsd/fsf/public/files/xmlFullSanctionsList_1_1", "eu_fsf.xml"),
             ("sanctionslist.fcdo.gov.uk", "uk_sanctions.xml"),
             ("federalregister.gov", "federal_register.json"), ("data.trade.gov", "trade_gov_csl.json")]
    for needle, name in table:
        if needle in url:
            return (FIX / name).read_bytes()
    if "sciencebase.gov/catalog/item" in url:
        return (FIX / "usgs_item.json").read_bytes()
    if "sciencebase.gov/catalog/file" in url:
        files = minerals.find_files(text("usgs_item.json"))["files"]
        name = {f["url"]: k for k, f in files.items()}[url]
        return (FIX / {"reliance": "usgs_net_import_reliance.csv", "sources": "usgs_major_import_sources.csv"}[name]).read_bytes()
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

    def test_eia(self):
        series = {}
        for name, ids in (("eia_petroleum.json", ["RBRTE", "RWTC"]), ("eia_natural_gas.json", ["RNGWHHD"])):
            series.update(markets.parse_eia_json(text(name), ids))
        en = markets.measure_energy(series)
        self.assertEqual({e["id"] for e in en}, {"brent", "wti", "henry-hub"})
        self.assertTrue(all(e["price"] > 0 and "route" not in e for e in en))
        with self.assertRaises(ValueError):          # a series missing from the reply is an error
            markets.parse_eia_json(text("eia_natural_gas.json"), ["RBRTE"])
        with self.assertRaises(ValueError):          # so is EIA's own error reply
            markets.parse_eia_json('{"error": "API_KEY_MISSING"}', ["RBRTE"])
        self.assertNotIn("api_key", markets.eia_url("petroleum/pri/spt", ["RBRTE", "RWTC"], "2024-01-01"))

    def test_the_eia_key_is_never_recorded(self):
        seen = []

        def getter(url, timeout=60):
            seen.append(url)
            return fake_getter(url, timeout)

        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            result, recs = headwind_cli._lane_energy(raw, {}, getter)
            self.assertEqual(len(result["energy"]), 3)
            self.assertTrue(all("test-key-not-real" in u for u in seen))             # sent to EIA
            self.assertNotIn("test-key-not-real", json.dumps(recs))                  # not in the record
            self.assertNotIn("test-key-not-real", (raw / "index.jsonl").read_text(encoding="utf-8"))

            def refused(url, timeout=60):
                raise OSError(f"403 for {url}")
            with self.assertRaises(OSError) as ctx:
                headwind_cli._lane_energy(raw, {}, refused)
            self.assertNotIn("test-key-not-real", str(ctx.exception))                # not in an error

    def test_a_scheduled_run_gets_its_state_back_from_the_published_site(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            a, b = Path(a), Path(b)
            shutil.copytree(ROOT / "site_src", a / "site_src")
            headwind_cli.collect(a, getter=fake_getter)
            self.assertNotIn("data/state/snapshot.json", headwind_cli.build_site(a))        # only when asked
            published = headwind_cli.build_site(a, publish_state=True)

            def site(url, timeout=60):
                rel = url.split("example.test/", 1)[1]
                if rel not in published:
                    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
                return published[rel].encode("utf-8")

            got = headwind_cli.restore(b, "https://example.test/", getter=site)
            self.assertTrue(all(v.startswith("restored") for v in got.values()), got)
            again = headwind_cli.collect(b, getter=fake_getter)
            self.assertEqual(again["sanctions"], [])                 # a second reading, not a first
            self.assertEqual(again["sanctions_lists"][0]["baseline_set_at"],
                             json.loads(published["data/state/snapshot.json"])["sanctions_lists"][0]["baseline_set_at"])
            nothing = headwind_cli.restore(Path(tempfile.mkdtemp()), "https://example.test/", getter=lambda u, t=60: b"<html>")
            self.assertTrue(all(v.startswith("not restored") for v in nothing.values()))

            def down(url, timeout=60):                                # the site cannot be reached
                raise TimeoutError("timed out")

            unreachable = headwind_cli.restore(Path(tempfile.mkdtemp()), "https://example.test/", getter=down)
            self.assertTrue(all(v.startswith("failed") for v in unreachable.values()), unreachable)

    def test_no_eia_key_fails_the_lane_plainly(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"EIA_API_KEY": "", "HEADWIND_EIA_KEY_FILE": str(Path(tmp) / "none.txt")}):
            with self.assertRaises(RuntimeError):
                headwind_cli._lane_energy(Path(tmp) / "raw", {}, fake_getter)

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
        self.assertAlmostEqual(m["median_change_pct"], 50.0, places=1)    # 50.1 with the exchange rate in
        self.assertGreaterEqual(m["series"], food.WFP_MIN_SERIES)
        self.assertFalse(m["stale"])
        self.assertTrue(food.measure_wfp(text("wfp_sdn.csv"), "2027-06")["stale"])
        self.assertIsNone(food.measure_wfp("date,price\n", "2026-11"))

    def test_wfp_market_exchange_rate(self):
        # Sudan's file has Khartoum's unofficial rate; it is read on its own and kept out of the food median.
        fx = food.measure_wfp_fx(text("wfp_sdn.csv"), "2026-11")
        self.assertTrue(fx["unofficial"])
        self.assertEqual(fx["recent"][-1], [fx["period"], fx["per_usd_median"]])
        self.assertEqual(fx["labels"], ["Exchange rate (unofficial)"])
        self.assertGreaterEqual(fx["markets"], 1)
        self.assertGreater(fx["per_usd_median"], 1000)              # Sudanese pounds per US dollar
        self.assertEqual(fx["direction"], "weaker" if fx["median_change_pct"] > 0 else fx["direction"])
        self.assertIsNone(food.measure_wfp_fx("date,commodity,price\n2026-01-15,Sorghum,10\n", "2026-11"))
        rows = ["date,market,commodity,unit,pricetype,currency,price"]
        for i in range(30):
            y, m = 2024 + i // 12, i % 12 + 1
            rows.append(f"{y}-{m:02d}-15,Aden,Exchange rate (unofficial),USD/LCU,Retail,YER,{1500 + i}")
            rows.append(f"{y}-{m:02d}-15,Sanaa,Exchange rate (unofficial),USD/LCU,Retail,YER,{530 + i}")
        split = food.measure_wfp_fx("\n".join(rows) + "\n", "2026-07")
        self.assertTrue(split["split"])                             # two rials: no single level

    def test_world_bank_gem(self):
        series, updated = markets.parse_gem(text("worldbank_gem.json"))
        self.assertEqual(updated, "2026-09-08")
        self.assertEqual(sorted(series), ["COD", "LBN", "PHL", "SDN", "YEM"])   # Somalia has no values
        rows = markets.measure_gem(series, {"COD": "CD", "LBN": "LB", "PHL": "PH", "SDN": "SD", "YEM": "YE"}, "2026-11")
        by = {r["country"]: r for r in rows}
        self.assertEqual(by["PH"]["period"], "2026-08")
        self.assertAlmostEqual(by["PH"]["per_usd"], 61.3728875, places=4)
        self.assertTrue(by["SD"]["stale"])                          # newest month October 2024
        self.assertFalse(by["SD"]["anomaly"])
        self.assertEqual(len(by["PH"]["recent"]), markets.GEM_RECENT)
        with self.assertRaises(ValueError):
            markets.parse_gem(b'[{"message": [{"id": "120", "value": "Invalid value"}]}]')
        with self.assertRaises(ValueError):
            markets.parse_gem(b'[{"page": 1, "pages": 2}, []]')

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

    def test_usgs_minerals(self):
        found = minerals.find_files(text("usgs_item.json"))
        self.assertEqual(found["published"], "2026-02-06")
        body = (FIX / "usgs_net_import_reliance.csv").read_bytes()
        minerals.check_md5(body, found["files"]["reliance"]["md5"], "reliance")
        with self.assertRaises(ValueError):
            minerals.check_md5(body + b"x", found["files"]["reliance"]["md5"], "reliance")
        rel = minerals.parse_reliance(text("usgs_net_import_reliance.csv"))
        self.assertEqual(len(rel), 68)
        gallium = next(r for r in rel if r["commodity"] == "GALLIUM")
        self.assertEqual((gallium["reliance_pct"], gallium["bound"], gallium["sources"][0], gallium["year"]),
                         (100, None, "Canada", "2025"))
        barite = next(r for r in rel if r["commodity"] == "BARITE")
        self.assertEqual((barite["reliance_text"], barite["reliance_pct"], barite["bound"]), (">75", 75, ">"))
        self.assertEqual(next(r for r in rel if r["commodity"] == "XENON")["sources"], [])     # "NA" is not a country
        crit = minerals.parse_sources(text("usgs_major_import_sources.csv"))
        antimony = next(m for m in crit if m["commodity"] == "Antimony")
        self.assertEqual(antimony["shares"][0], {"source": "China", "pct": 55})
        self.assertEqual(next(m for m in crit if m["commodity"] == "Hafnium")["shares"], [])
        doc = minerals.build(found, rel, crit, {"China": "CN", "Republic of Korea": "KR"}.get)
        self.assertEqual((doc["reliance_year"], doc["sources_period"], doc["with_sources"]), ("2025", "2021-24", 65))
        self.assertEqual(len(doc["import_sources"]), 47)
        printed = {m["commodity"]: m["reliance_text"] for m in doc["import_sources"]}
        self.assertEqual((printed["Barite"], printed["Germanium"], printed["Antimony"], printed["Hafnium"]),
                         (">75", ">50", "91", None))           # the bound USGS prints is kept
        china = next(b for b in doc["by_source"] if b["source"] == "China")
        self.assertEqual(china["country"], "CN")
        self.assertEqual(china["named_first"], sum(1 for r in rel if r["sources"][:1] == ["China"]))
        with self.assertRaises(ValueError):
            minerals.parse_reliance("Source,Commodity\nMCS2026,GALLIUM\n")

    def test_critical_minerals_list(self):
        # The tuple is the notice's own sentence, read from the Federal Register text of 7 Nov 2025.
        self.assertEqual(tuple(minerals.parse_list_sentence(text("fr_critical_minerals_2025.txt"))),
                         minerals.CRITICAL_2025)
        self.assertEqual(len(minerals.CRITICAL_2025), 60)
        with self.assertRaises(ValueError):
            minerals.parse_list_sentence("includes the following 3 minerals: tin, and zinc.")
        cm = minerals.critical_members
        self.assertEqual((cm("COPPER, refined"), cm("Phosphate, rock"), cm("Metallurgical coal"), cm("GRAPHITE (NATURAL)")),
                         (["copper"], ["phosphate"], ["metallurgical coal"], ["graphite"]))
        self.assertEqual((cm("ALUMINA"), cm("BAUXITE"), cm("ABRASIVES, fused aluminum oxide"), cm("XENON")), ([], [], [], []))
        self.assertEqual(len(cm("RARE EARTHS, compounds and metals")), 14)
        found = minerals.find_files(text("usgs_item.json"))
        doc = minerals.build(found, minerals.parse_reliance(text("usgs_net_import_reliance.csv")),
                             minerals.parse_sources(text("usgs_major_import_sources.csv")), lambda name: None)
        self.assertTrue(all(m["critical"] for m in doc["import_sources"]))     # USGS's figure 3 is list minerals only
        cl = doc["critical_list"]
        self.assertEqual((cl["count"], cl["document"], cl["not_in_import_sources"]), (60, "2025-19813", ["ruthenium"]))
        self.assertEqual(cl["not_in_reliance_table"], ["beryllium", "boron", "hafnium", "iridium", "metallurgical coal",
                                                       "phosphate", "rhodium", "ruthenium", "uranium"])
        self.assertEqual(next(r for r in doc["reliance"] if r["commodity"] == "MAGNESIUM COMPOUNDS")["critical"], ["magnesium"])

    def test_world_bank(self):
        rows = baseline.parse_wb(text("worldbank.json"), {"TR", "SD", "US"}, this_year=2026)
        self.assertIn("TR", rows)
        self.assertNotIn("1W", rows)             # aggregates dropped
        old = json.dumps([{}, [{"country": {"id": "SD"}, "date": "1999", "value": 865.87}]])
        self.assertEqual(baseline.parse_wb(old, {"SD"}, this_year=2026), {})


class TestMineralsWatch(unittest.TestCase):
    """Step 7: a newer USGS edition or critical minerals list is a warning on usgs-mcs. Fixtures are real replies
    of 14 Nov 2026: ScienceBase searched for the 2026 and the 2027 editions, the Federal Register since 2021."""
    OLDER_LIST = {"document": "2022-04027", "published": "2022-02-24"}

    def test_newer_editions(self):
        body = (FIX / "sciencebase_mcs_search_2026.json").read_bytes()
        self.assertEqual(minerals.newer_editions(body), [])                    # 2026 is the edition read
        found = minerals.newer_editions(body, 2025)
        self.assertEqual([(e["year"], e["id"], e["published"]) for e in found],
                         [(2026, "696a75d5d4be0228872d3bf8", "2026-02-06")])
        self.assertEqual(found[0]["title"], "Mineral Commodity Summaries 2026 Data Release")
        self.assertEqual(minerals.newer_editions((FIX / "sciencebase_mcs_search_2027.json").read_bytes()), [])

    def test_newer_lists(self):
        body = (FIX / "fr_critical_minerals_lists.json").read_bytes()
        self.assertEqual(minerals.newer_lists(body), [])                       # the Final 2025 list is the newest
        found = minerals.newer_lists(body, self.OLDER_LIST)
        self.assertEqual([n["document"] for n in found], ["2025-16311", "2025-19813"])   # the OCS notice is not one

    def test_notes_and_a_failed_check(self):
        sb = (FIX / "sciencebase_mcs_search_2026.json").read_bytes()
        fr = (FIX / "fr_critical_minerals_lists.json").read_bytes()
        m = {"watch": {"newer_editions": minerals.newer_editions(sb, 2025),
                       "newer_lists": minerals.newer_lists(fr, self.OLDER_LIST), "errors": []}}
        notes = minerals.watch_notes(m)
        self.assertEqual(len(notes), 3)
        self.assertIn("USGS has published Mineral Commodity Summaries 2026 Data Release (2026-02-06)", notes[0])
        self.assertIn("document 2025-19813", notes[2])

        def getter(url, timeout=60):
            if "catalog/items?" in url:
                raise urllib.error.URLError("ScienceBase down")
            return fake_getter(url, timeout)
        with tempfile.TemporaryDirectory() as tmp:
            result, recs = headwind_cli._lane_minerals(Path(tmp) / "raw", {}, getter)
        w = result["minerals"]["watch"]
        self.assertEqual((w["newer_editions"], w["newer_lists"]), ([], []))
        self.assertEqual(len(w["errors"]), 1)
        self.assertEqual(minerals.watch_notes(result["minerals"])[0][:41], "could not check for a newer USGS edition:")
        self.assertEqual(len(recs), 4)                                          # item, two CSVs, the FR search

    def test_end_to_end_has_no_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = headwind_cli.collect(Path(tmp), getter=fake_getter)
        self.assertEqual(snap["minerals"]["watch"]["errors"], [])
        self.assertNotIn("warnings", snap["health"]["usgs-mcs"])


class TestVesselCrosslist(unittest.TestCase):
    """Step 9. crosslist_ofac.csv and crosslist_uk.xml are one ship on both lists, AN SAN 1 (IMO 7303803), cut
    from the OFAC and UK files read on 14 Nov 2026. The full lists that day: 1,944 IMO numbers, 304 on both,
    1,251 on OFAC's only, 389 on the UK's only."""

    def indexes(self):
        ofac = sanctions.parse_sdn_csv(text("ofac_sdn.csv").rstrip("\n") + "\n" + text("crosslist_ofac.csv"))
        _, uk = sanctions.parse_uk_xml((FIX / "uk_ships_2026-11-12.xml").read_bytes())
        _, one = sanctions.parse_uk_xml((FIX / "crosslist_uk.xml").read_bytes())
        return ofac, {**uk, **one}

    def test_crosslist(self):
        ofac, uk = self.indexes()
        s, t = sanctions.vessel_crosslist({"ofac-sdn": ofac, "uk-sanctions": uk})
        self.assertEqual((s["imo_numbers"], s["on_both"], s["only"]), (15, 1, {"ofac-sdn": 8, "uk-sanctions": 6}))
        r = next(r for r in t if r["imo"] == "7303803")
        self.assertEqual(r["on"]["ofac-sdn"], {"ids": ["23730"], "name": "AN SAN 1",
                                               "flag": "Democratic People's Republic of Korea"})
        self.assertEqual((r["on"]["uk-sanctions"]["ids"], r["on"]["uk-sanctions"]["name"]), (["DPR0097"], "An San 1"))
        s2, _ = sanctions.vessel_crosslist({"ofac-sdn": ofac}, stale=("uk-sanctions",))
        self.assertEqual((s2["on_both"], s2["read"]["uk-sanctions"], s2["from_earlier_run"]),
                         (0, False, ["uk-sanctions"]))

    def test_also_on_in_a_change_and_the_feed(self):
        ofac, uk = self.indexes()
        prev = {k: v for k, v in uk.items() if k != "DPR0097"}
        d = sanctions.delta("uk-sanctions", prev, uk, "2026-11-15T15:00:00Z", "2026-11-14T22:52:09Z")
        _, t = sanctions.vessel_crosslist({"ofac-sdn": ofac, "uk-sanctions": uk})
        sanctions.mark_also_on(d, t)
        v = d["vessels_added"][0]
        self.assertEqual((v["name"], v["imo"], v["also_on"]), ("An San 1", "7303803", ["ofac-sdn"]))
        self.assertIn("An San 1 (IMO 7303803, flag North Korea, also on the OFAC SDN list)",
                      feed._vessel_text("added", d["vessels_added"]))

    def test_lane_and_site_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = headwind_cli.collect(Path(tmp), getter=fake_getter)
            self.assertEqual(snap["vessel_crosslist"]["imo_numbers"], len(snap["vessel_table"]))
            files = headwind_cli.build_site(Path(tmp), snap)
            self.assertIn("data/vessels.json", files)
            doc = json.loads((Path(tmp) / "site" / "data" / "vessels.json").read_text(encoding="utf-8"))
            self.assertEqual(len(doc["vessels"]), snap["vessel_crosslist"]["imo_numbers"])
            page = json.loads((Path(tmp) / "site" / "data" / "snapshot.json").read_text(encoding="utf-8"))
            self.assertNotIn("vessel_table", page)


class TestTrade(unittest.TestCase):
    def test_parse_and_summarize_real_replies(self):
        rec = trade.summarize("2846", trade.parse(text("census_2846.json")), "2026-09", "2024-09")
        self.assertTrue(rec["description_ok"])
        self.assertEqual(rec["newest_month"], "2026-09")
        self.assertEqual(rec["window"], ["2025-10", "2026-09"])
        self.assertEqual(rec["sources"][0]["country"], "CHINA")
        self.assertGreater(rec["china_share_pct"], 50)
        self.assertTrue(all(s["share_pct"] <= 100 for s in rec["sources"]))
        self.assertNotIn("OECD", [s["country"] for s in rec["sources"]])          # groupings are not countries
        nickel = trade.summarize("7502", trade.parse(text("census_7502.json")))
        self.assertIn("NICKLE", nickel["description"])                              # Census's own spelling
        self.assertTrue(nickel["description_ok"])
        # A month with no trade is missing from the reply; the windows stay calendar months.
        cut = trade.parse(text("census_2846.json"))
        cut["months"].pop("2026-03")
        gap = trade.summarize("2846", cut, "2026-09", "2024-09")
        self.assertEqual(gap["window"], ["2025-10", "2026-09"])
        self.assertLess(gap["imports_12m_usd"], rec["imports_12m_usd"])
        self.assertEqual(gap["imports_prior_12m_usd"], rec["imports_prior_12m_usd"])
        self.assertIsNone(trade.summarize("2846", trade.parse(text("census_2846.json")), "2026-09", "2025-06")["change_pct"])
        self.assertEqual(trade.summarize("2605", trade.parse(b"")), {"hs": "2605", "minerals": ["cobalt"],
                         "description": None, "description_ok": False, "newest_month": None})
        with self.assertRaises(ValueError):
            trade.parse(b'{"error": "bad"}')

    def test_every_code_stands_for_list_minerals(self):
        names = {n.lower() for n in minerals.CRITICAL_2025}
        for code, meta in trade.CODES.items():
            for m in meta["minerals"]:
                self.assertTrue(m in names or m == "rare earths", (code, m))

    def test_the_key_stays_out_of_what_is_kept(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            result, recs = headwind_cli._lane_trade(tmp / "raw", {}, fake_getter)
            kept = (tmp / "raw" / "index.jsonl").read_text(encoding="utf-8") + json.dumps(result)
            self.assertNotIn("census-test-key-not-real", kept)
            self.assertTrue(all("key=" not in r["url"] for r in recs))
            self.assertEqual([c["hs"] for c in result["mineral_trade"]["codes"] if c["newest_month"]], ["2846", "7502"])

            def refused(url, timeout=60):
                raise OSError(f"HTTP 400 for {url}")
            with self.assertRaises(RuntimeError) as cm:
                headwind_cli._lane_trade(tmp / "raw", {}, refused)
            self.assertNotIn("census-test-key-not-real", str(cm.exception))
            with mock.patch.dict(os.environ, {"CENSUS_API_KEY": "", "HEADWIND_CENSUS_KEY_FILE": str(tmp / "none.txt")}):
                with self.assertRaises(RuntimeError):
                    headwind_cli._lane_trade(tmp / "raw", {}, fake_getter)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBatches(unittest.TestCase):
    def test_dated_batches(self):
        # 30 earlier designation dates of 3 to 6 entries, then one of 40: unusual; one of 6 is not.
        dates = {f"old{d}-{i}": f"2026-01-{d:02d}" for d in range(1, 31) for i in range(3 + d % 4)}
        dates.update({f"big-{i}": "2026-03-01" for i in range(40)})
        dates.update({f"small-{i}": "2026-03-02" for i in range(6)})
        out = {b["date"]: b for b in batches.measure([f"big-{i}" for i in range(40)] + ["small-0"], dates, None,
                                                     "2026-03-02T12:00:00Z")}
        self.assertEqual((out["2026-03-01"]["size"], out["2026-03-01"]["added"]), (40, 40))
        self.assertTrue(out["2026-03-01"]["anomaly"])
        self.assertEqual(out["2026-03-02"]["added"], 1)
        self.assertFalse(out["2026-03-02"]["anomaly"])
        self.assertEqual(out["2026-03-01"]["baseline_n"], 30)

    def test_small_batches_are_never_unusual(self):
        # The UN's dates are nearly all one entry: a batch of 8 has a large z but stays under the floor.
        dates = {f"o{d}": f"2025-{1 + d // 28:02d}-{1 + d % 28:02d}" for d in range(60)}
        dates.update({f"n{i}": "2026-07-14" for i in range(8)})
        b = batches.measure([f"n{i}" for i in range(8)], dates, None, "2026-07-15T00:00:00Z")[0]
        self.assertGreater(b["z"], stats.Z_ANOMALY)
        self.assertFalse(b["anomaly"])

    def test_seen_batches_need_a_history(self):
        b = batches.measure(["a", "b"], None, [2, 1, 3], "2026-11-14T20:00:00Z")[0]
        self.assertEqual((b["basis"], b["z"], b["baseline_n"], b["anomaly"]), ("headwind readings", None, 3, False))
        hist = [2, 3, 1, 4, 2, 2, 3, 1, 5, 2] * 3
        self.assertTrue(batches.seen(60, hist, "2026-11-14")["anomaly"])
        self.assertEqual(batches.remember(hist, 0), hist[-batches.HISTORY_KEEP:])
        self.assertEqual(len(batches.remember(list(range(1, 200)), 7)), batches.HISTORY_KEEP)
        self.assertEqual(batches.measure([], None, hist, "2026-11-14"), [])

    def test_parsers_give_designation_dates(self):
        d_eu, d_uk, d_un = {}, {}, {}
        _, eu = sanctions.parse_eu_xml((FIX / "eu_fsf.xml").read_bytes(), d_eu)
        _, uk = sanctions.parse_uk_xml((FIX / "uk_sanctions.xml").read_bytes(), d_uk)
        _, un = sanctions.parse_un_xml((FIX / "un_consolidated.xml").read_bytes(), d_un)
        self.assertEqual((set(d_eu), set(d_uk), set(d_un)), (set(eu), set(uk), set(un)))
        for d in (d_eu, d_uk, d_un):
            self.assertTrue(any(d.values()))
            self.assertTrue(all(v is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in d.values()))
        doc = json.loads(text("trade_gov_csl.json"))
        el = next(e for e in doc["results"] if e["source"].startswith("Entity List"))
        el["start_date"] = "2025-10-08"
        lists = screening.parse(json.dumps(doc))
        self.assertIn("2025-10-08", lists["EL"]["dates"].values())

    def test_a_large_batch_makes_the_change_an_anomaly(self):
        prev = {f"old{d}-{i}": ["entity", ["RUS"]] for d in range(1, 31) for i in range(3 + d % 4)}
        dates = {f"old{d}-{i}": f"2026-01-{d:02d}" for d in range(1, 31) for i in range(3 + d % 4)}
        index = dict(prev, **{f"new{i}": ["entity", ["RUS"]] for i in range(45)})
        dates.update({f"new{i}": "2026-11-12" for i in range(45)})
        d = sanctions.delta("uk-sanctions", prev, index, "2026-11-13T15:00:00Z", "2026-11-12T15:00:00Z", dates=dates)
        self.assertTrue(d["anomaly"])
        snap = {"generated_at": "2026-11-13T16:00:00Z", "lanes": {}, "sanctions": [d], "controls": []}
        fc = feed.build_feed(snap)
        self.assertEqual(lint(fc), [])
        p = fc["features"][0]["properties"]
        self.assertEqual(p["tier"], "anomaly")
        self.assertIn("designation dates", p["baseline_ref"]["window"])
        self.assertEqual((p["baseline_ref"]["id"], p["baseline_ref"]["type"]), ("headwind-designation-batch", "rolling"))
        self.assertIn("Designation batches: 2026-11-12: 45 entries", p["summary"])
        self.assertEqual(p["measures"]["batch_size_max"], 45)
        self.assertIn("flag_rate", p["measures"])                 # every scored item carries its flag rate
        self.assertEqual(p["measures"]["flag_rate"], d["batches"][0]["flag_rate"])
        self.assertNotIn("probability", p)
        self.assertNotIn("new0", json.dumps(fc))                  # entry ids are not published


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

    def test_official_and_market_rates_and_the_country_view(self):
        snap = self.snapshot()
        snap["fx_official"] = [{"country": "YE", "iso3": "YEM", "per_usd": 1600.0, "prior_per_usd": 1500.0,
                                "period": "2026-10", "prior_period": "2026-09", "change_pct": 6.7, "z": 5.1,
                                "baseline_n": 60, "flag_rate": 0.02, "direction": "weaker", "months_old": 1,
                                "stale": False, "anomaly": True, "recent": [["2026-09", 1500.0], ["2026-10", 1600.0]]},
                               {"country": "SD", "iso3": "SDN", "per_usd": 600.0, "prior_per_usd": 600.0,
                                "period": "2024-10", "prior_period": "2024-09", "change_pct": 0.0, "z": 0.0,
                                "baseline_n": 60, "flag_rate": 0.0, "direction": "unchanged", "months_old": 25,
                                "stale": True, "anomaly": False, "recent": []}]
        snap["market_fx"] = [{"country": "YE", "iso3": "YEM", "dataset": "https://data.humdata.org/dataset/x",
                              "period": "2026-10", "median_change_pct": 1.0, "markets": 11, "per_usd_median": 1760.0,
                              "per_usd_low": 1700.0, "per_usd_high": 1800.0, "split": False, "unofficial": True,
                              "labels": ["Exchange rate (unofficial)"], "direction": "weaker", "share_weaker": 0.6,
                              "z": 0.4, "baseline_n": 60, "flag_rate": 0.01, "months_old": 1, "stale": False,
                              "anomaly": False, "recent": [["2026-09", 1650.0], ["2026-10", 1760.0], ["2026-11", 1800.0]]}]
        snap["lanes"]["gem"] = {"fetched_at": "2026-11-13T05:00:00Z"}
        fc = feed.build_feed(snap)
        self.assertEqual(lint(fc), [])
        p = {f["properties"]["id"]: f["properties"] for f in fc["features"]}
        ye = p["headwind:fxofficial:YE:2026-10"]
        self.assertEqual((ye["tier"], ye["indicator_id"], ye["hypothesis_id"]), ("anomaly", "HW-IND-4", "HW-H-2A"))
        self.assertEqual(ye["sources"][0]["id"], "worldbank-gem")
        self.assertNotIn("headwind:fxofficial:SD:2024-10", p)       # stale official rate stays off the feed
        mk = p["headwind:fxmarket:YE:2026-10"]
        self.assertEqual(mk["tier"], "routine")
        self.assertIn("unofficial market", mk["title"])
        view = {r["country"]: r for r in feed.country_view(snap)}
        self.assertEqual(sorted(view), sorted(feed.WATCHED))
        gap = view["YE"]["market_vs_official"]
        self.assertEqual((gap["period"], gap["pct"]), ("2026-10", 10.0))
        self.assertIn("two rials", gap["caveat"])                     # Yemen's gap always carries its caveat
        # A month whose markets were too far apart to be one market is never compared: the month before is.
        split_snap = dict(snap, market_fx=[dict(snap["market_fx"][0], split_months=["2026-10"])])
        gap = {r["country"]: r for r in feed.country_view(split_snap)}["YE"]["market_vs_official"]
        self.assertEqual((gap["period"], gap["pct"]), ("2026-09", 10.0))
        # Any other country with a gap of 100% or more gets the general caveat.
        wide = dict(snap, market_fx=[dict(snap["market_fx"][0], country="LB", recent=[["2026-10", 3300.0]])],
                    fx_official=[dict(snap["fx_official"][0], country="LB")])
        gap = {r["country"]: r for r in feed.country_view(wide)}["LB"]["market_vs_official"]
        self.assertEqual((gap["pct"], gap["caveat"]), (106.2, feed.GAP_WIDE))
        self.assertEqual(view["YE"]["indicators_present"], ["HW-IND-4"])
        self.assertEqual(view["SD"]["indicators_present"], ["HW-IND-6"])
        self.assertIsNone(view["CU"]["daily"])

    def test_hw_wp_2_indicators_on_anomalies(self):
        snap = self.snapshot()
        php = dict(snap["fx"][0], currency="PHP", country="PH", per_usd=61.2, prior_per_usd=57.0)
        snap["fx"].append(php)
        fc = feed.build_feed(snap)
        self.assertEqual(lint(fc), [])
        p = {f["properties"]["id"].split(":")[1] + ":" + f["properties"]["id"].split(":")[2]: f["properties"]
             for f in fc["features"]}
        self.assertEqual([p["fx:PHP"][k] for k in ("indicator_id", "hypothesis_id", "direction", "indicator_state")],
                         ["HW-IND-4", "HW-H-2A", "supports", "present"])
        self.assertNotIn("indicator_id", p["fx:TRY"])               # Turkey is not a watched country
        self.assertNotIn("indicator_id", p["fx:EUR"])               # routine items carry none
        self.assertEqual((p["energy:brent"]["indicator_id"], p["energy:brent"]["hypothesis_id"]), ("HW-IND-5", "HW-H-2B"))
        self.assertEqual([p["localfood:SD"][k] for k in ("indicator_id", "hypothesis_id", "direction", "indicator_state")],
                         ["HW-IND-6", "HW-H-2A", "neutral", "present"])     # expected under 2A and 2B alike
        reg = {i["id"]: i for i in json.loads((ROOT / "doctrine" / "indicators.json").read_text(encoding="utf-8"))["indicators"]}
        self.assertEqual(sorted(feed.NON_DIAGNOSTIC), sorted(k for k, v in reg.items() if k in ("HW-IND-4", "HW-IND-5",
                         "HW-IND-6") and not v["gentry"]["diagnostic"]))      # the code follows the register
        self.assertIn("World Bank", reg["HW-IND-4"]["text"])         # HW-IND-4 names all three readings
        self.assertNotIn("indicator_id", p["food:cereals"])         # HW-IND-3 has no warning problem
        wp = next(w for w in json.loads((ROOT / "doctrine" / "indicators.json").read_text(encoding="utf-8"))["warning_problems"] if w["id"] == "HW-WP-2")
        self.assertEqual([h["id"] for h in wp["hypotheses"]], ["HW-H-2A", "HW-H-2B", "HW-H-2C"])
        self.assertTrue(all(cc in feed.WATCHED for cc in ("PH", "SD", "YE")))

    def test_list_changes_and_rules_are_counts_and_published_facts(self):
        snap = self.snapshot()
        old = sanctions.parse_sdn_csv(text("ofac_sdn.csv"))
        new = dict(old)
        del new["36"]
        new["99999"] = ["vessel", ["RUSSIA-EO14024"], {"name": "TEST HULL", "imo": "9999993", "mmsi": None,
                                                        "flag": "Panama", "vessel_type": "Crude Oil Tanker"}]
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
        self.assertEqual([(v["name"], v["imo"]) for v in d["vessels_added"]], [("TEST HULL", "9999993")])
        self.assertIn("TEST HULL (IMO 9999993, flag Panama)", s["summary"])
        self.assertEqual(s["us_person_data"], "none")
        legacy = {"1": ["vessel", ["CUBA"]], "2": ["entity", ["CUBA"]]}              # an index from before vessel details
        gone = sanctions.delta("ofac-sdn", legacy, {"2": legacy["2"]}, "2026-11-13T04:00:00Z", None)
        self.assertEqual((gone["removed_by_type"], gone["vessels_removed"]), ({"vessel": 1}, []))
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
        ships = {k: v[2] for k, v in idx.items() if v[0] == "vessel"}
        self.assertEqual(ships["15042"]["imo"] and len(ships["15042"]["imo"]), 7)
        self.assertTrue(all(s["name"] for s in ships.values()))
        self.assertTrue(all(len(v) == 2 for v in idx.values() if v[0] != "vessel"))   # no names for anyone else
        kinds = {v[0] for v in idx.values()}
        self.assertEqual(kinds, {"entity", "individual", "vessel", "aircraft"})
        self.assertTrue(any(len(v[1]) > 1 for v in idx.values()))   # "[A] [B]" splits into two programs
        self.assertEqual(sanctions.countries_for(["RUSSIA-EO14024", "SDGT", "DPRK3"]), ["KP", "RU"])

    def test_un(self):
        generated, idx = sanctions.parse_un_xml((FIX / "un_consolidated.xml").read_bytes())
        self.assertEqual(generated[:10], "2026-11-13")
        self.assertEqual(len(idx), 14)
        self.assertEqual(idx["6907993"], ["individual", ["DRC"]])

    def test_eu(self):
        generated, idx = sanctions.parse_eu_xml((FIX / "eu_fsf.xml").read_bytes())
        self.assertEqual(generated[:10], "2026-10-23")
        self.assertEqual(len(idx), 9)
        self.assertEqual({v[0] for v in idx.values()}, {"individual", "entity"})
        self.assertTrue(all(len(v) == 2 for v in idx.values()))     # counts only: no names carried
        self.assertEqual(sanctions.countries_for(["UKR", "TAQA", "IRN"], "eu-fsf"), ["IR", "RU"])
        self.assertEqual(sanctions.countries_for(["SDNZ"], "eu-fsf"), ["SD"])   # Tom, 14 Nov 2026
        self.assertEqual(sanctions.countries_for(["SDN"], "eu-fsf"), ["SD"])   # the EU's Sudan code, not OFAC's list
        self.assertEqual(sanctions.unknown_programs("eu-fsf", idx), [])
        self.assertEqual(sanctions.unknown_programs("eu-fsf", {"1": ["entity", ["NEWX"]]}), ["NEWX"])

    def test_uk(self):
        generated, idx = sanctions.parse_uk_xml((FIX / "uk_sanctions.xml").read_bytes())
        self.assertEqual(generated, "2026-11-12")
        self.assertEqual(len(idx), 11)
        ships = [v for v in idx.values() if v[0] == "vessel"]
        self.assertEqual(len(ships), 2)
        self.assertTrue(all(v[2]["name"] and len(v[2]["imo"]) == 7 for v in ships))   # "Primary Name" and "Primary name"
        self.assertTrue(all("owner" not in json.dumps(v[2]).lower() for v in ships))
        self.assertTrue(all(len(v) == 2 for v in idx.values() if v[0] != "vessel"))
        self.assertEqual(sanctions.uk_regime("The Iran (Sanctions) (Nuclear) (EU Exit) Regulations 2019"), "Iran (Nuclear)")
        self.assertEqual(sanctions.uk_regime("The Global Human Rights Sanctions Regulations 2020"), "Global Human Rights")
        self.assertEqual(sanctions.unknown_programs("uk-sanctions", idx), [])
        old = dict(idx)
        gone = next(k for k, v in idx.items() if v[0] == "vessel")
        del idx[gone]
        d = sanctions.delta("uk-sanctions", old, idx, "2026-11-14T04:00:00Z", "2026-11-13T04:00:00Z")
        self.assertEqual((d["removed"], len(d["vessels_removed"]), d["vessels_removed"][0]["list_id"]), (1, 1, gone))
        self.assertEqual(d["countries"], sanctions.countries_for(old[gone][1], "uk-sanctions"))

    def test_screening_list(self):
        lists = screening.parse((FIX / "trade_gov_csl.json").read_bytes())
        self.assertNotIn("SDN", lists)                              # the sanctions lane reads that one from OFAC
        self.assertEqual(len(lists["EL"]["index"]), 4)
        self.assertEqual(lists["EL"]["name"], "Entity List")
        self.assertEqual(lists["EL"]["publisher"], "US Bureau of Industry and Security")
        self.assertEqual(lists["MEU"]["name"], "Military End User List")
        self.assertEqual(lists["FSE"]["index"], {})                 # named in the file, no entries
        kind, programs, countries = next(iter(lists["EL"]["index"].values()))[:3]
        self.assertEqual((kind, programs), ("not stated", []))
        self.assertTrue(countries and all(len(c) == 2 for c in countries))
        self.assertEqual(lists["EL"]["source_last_updated"][:10], "2026-08-21")
        cut = json.loads(text("trade_gov_csl.json"))
        cut["total"] += 100                                         # the file says more than it holds
        with self.assertRaises(ValueError):
            screening.parse(json.dumps(cut))

    def test_screening_changes_are_counts_by_list(self):
        now, later = "2026-11-13T15:00:00Z", "2026-11-14T15:00:00Z"
        lists = screening.parse((FIX / "trade_gov_csl.json").read_bytes())
        first, statuses, state = screening.compare(lists, {}, now)
        self.assertEqual(first, [])                                 # the first reading only sets the baseline
        self.assertEqual(statuses[0]["total"], 4)
        new = screening.parse((FIX / "trade_gov_csl.json").read_bytes())
        gone = next(iter(new["EL"]["index"]))
        del new["EL"]["index"][gone]
        new["EL"]["index"]["new-1"] = ["not stated", [], ["CN", "HK"]]
        new["EL"]["index"]["new-2"] = ["not stated", [], ["CN"]]
        new["FSE"]["index"]["55555"] = ["entity", ["FSE-IR"], []]   # a list that was empty gains an entry
        deltas, _, state2 = screening.compare(new, state, later)
        by = {d["list"]: d for d in deltas}
        self.assertEqual(sorted(by), ["EL", "FSE"])
        el = by["EL"]
        self.assertEqual((el["added"], el["removed"], el["total"]), (2, 1, 5))
        self.assertEqual(el["added_by_country"], {"CN": 2, "HK": 1})
        self.assertEqual(el["prior_checked_at"], now)
        self.assertIn("CN", el["countries"])
        self.assertEqual(by["FSE"]["added_by_country"], {"none stated": 1})
        self.assertEqual(screening.compare(new, state2, later)[0], [])
        emptied = screening.parse((FIX / "trade_gov_csl.json").read_bytes())
        emptied["EL"]["index"] = {}
        with self.assertRaises(ValueError):                         # a list that empties is a broken import
            screening.compare(emptied, state, later)
        snap = {"generated_at": later, "lanes": {}, "screening": deltas}
        fc = feed.build_feed(snap)
        self.assertEqual(lint(fc), [])
        p = next(f["properties"] for f in fc["features"] if f["properties"]["id"].startswith("headwind:screening:el:"))
        self.assertEqual((p["kind"], p["tier"], p["measures"]["added"]), ("observation", "routine", 2))
        self.assertIn("by address country, CN 2, HK 1", p["summary"])
        self.assertNotIn("probability", p)

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


class FixedDate(date):
    """date.today() on 9 Nov 2026, the day USTR filed its two China notices, for the lanes that read by date."""
    @classmethod
    def today(cls):
        return cls(2026, 11, 9)


def _pi_records(today=date(2026, 11, 9)):
    """The filings of the 5 and 9 Nov issues, with their texts read and matched against the register."""
    docs = controls.parse_fr((FIX / "fr_register_rules.json").read_bytes()) + controls.parse_fr(
        (FIX / "fr_register_ustr.json").read_bytes())
    reg = controls.scheduled(docs, today)
    read = inspection.parse_issue((FIX / "fr_pi_2026-11-05.json").read_bytes(), "2026-11-05")
    read += inspection.parse_issue((FIX / "fr_pi_2026-11-09.json").read_bytes(), "2026-11-09")
    recs = inspection.merge([], read, "2026-11-09T15:00:00Z", today)
    for r in recs:
        f = FIX / f"fr_pi_raw_{r['id']}.txt"
        if inspection.wants_text(r) and f.exists():
            r["text"] = inspection.read_text(f.read_bytes())
    return inspection.match(recs, reg)


class TestInspection(unittest.TestCase):
    """Step 10: USTR documents, the register of scheduled dates, and filings on public inspection. Fixtures are real
    replies of 15 Nov 2026: the issues available on 5 and 9 Nov, cut to the three agencies' filings and one other,
    and the texts of four filings without their contact paragraph."""

    def test_ustr_notices_and_register(self):
        notices = controls.parse_fr(text("fr_ustr_notices.json"))
        self.assertEqual([n["id"] for n in notices], ["2026-22925", "2026-22867", "2026-20615"])  # PRB notice left out
        self.assertTrue(all(n["agency"] == "USTR" and n["type"] == "Notice" for n in notices))
        self.assertEqual(next(n for n in notices if n["id"] == "2026-20615")["dockets"], ["USTR-2026-0661"])
        rules = controls.parse_fr(text("fr_register_rules.json"))
        self.assertEqual(next(r for r in rules if r["id"] == "2025-19846")["rins"], ["0694-AK34"])
        self.assertEqual(controls.subject("Notice of Modification of Section 301 Action: China's Targeting of the "
                                          "Maritime, Logistics, and Shipbuilding Sectors for Dominance"),
                         controls.subject("Section 301 Action: China's Targeting the Maritime, Logistics, and "
                                          "Shipbuilding Sectors for Dominance; Modification"))
        self.assertIsNone(controls.subject("Extension of the Suspension of Expansion of End-User Controls"))
        reg = controls.scheduled(rules + controls.parse_fr(text("fr_register_ustr.json")), date(2026, 11, 5))
        nov9 = sorted(e["doc"] for e in reg if e["date"] == "2026-11-09")
        self.assertEqual(nov9, ["2025-19846", "2025-19873", "2025-21671", "2026-22793"])
        self.assertTrue(all(e["date"] >= "2026-09-21" for e in reg))       # passed dates kept 45 days only

    def test_issue_and_text(self):
        five = inspection.parse_issue(text("fr_pi_2026-11-05.json"), "2026-11-05")
        self.assertEqual([(r["id"], r["counted_only"]) for r in five],
                         [("2026-22725", True), ("2026-22726", True), ("2026-22793", False)])
        stay = five[2]
        self.assertEqual((stay["filed_at_utc"], stay["filed_on"], stay["publication_date"]),
                         ("2026-11-05T21:15:00Z", "2026-11-05", "2026-11-09"))
        self.assertTrue(all(r["title"] is None for r in five if r["counted_only"]))   # notices are counts only
        counted = [r for r in five if r["counted_only"]]
        self.assertEqual([r["url"] for r in counted], ["https://www.federalregister.gov/d/2026-22725",
                                                       "https://www.federalregister.gov/d/2026-22726"])
        self.assertTrue(all(r["raw_text_url"] is None and r["note"] is None for r in counted))
        self.assertIn("/public-inspection/2026-22793/extension-of-the-suspension", stay["url"])   # titled: as given
        # And a build from a snapshot that predates the fix publishes the same short form.
        self.assertEqual(inspection.public_form({"id": "2026-22598", "counted_only": True, "note": "x",
                                                 "url": "https://www.federalregister.gov/public-inspection/"
                                                        "2026-22598/denial-of-export-privileges-y"})["url"],
                         "https://www.federalregister.gov/d/2026-22598")
        # A filing kept from a run before this fix loses its slug when merged, even if not read again.
        old = {"id": "2026-21840", "agency": "BIS", "type": "Notice", "counted_only": True, "title": None,
               "filed_on": "2026-11-04", "note": "Names in a note", "dockets": [],
               "url": "https://www.federalregister.gov/public-inspection/2026-21840/denial-of-export-privileges-x-y",
               "raw_text_url": "https://www.federalregister.gov/public-inspection/raw_text/202/621/840.txt"}
        kept = next(r for r in inspection.merge([old], five, "2026-11-05T22:00:00Z", date(2026, 11, 5))
                    if r["id"] == "2026-21840")
        self.assertEqual((kept["url"], kept["raw_text_url"], kept["note"]),
                         ("https://www.federalregister.gov/d/2026-21840", None, None))
        nine = inspection.parse_issue(text("fr_pi_2026-11-09.json"), "2026-11-09")
        special = next(r for r in nine if r["id"] == "2026-22802")
        self.assertEqual((special["filed_at"], special["filed_on"]), (None, "2026-11-09"))   # no filing time given
        t = inspection.read_text((FIX / "fr_pi_raw_2026-22793.txt").read_bytes())
        self.assertEqual((t["action"], t["rins"], t["dockets"]), ("Final rule; stay", ["0694-AK34"], ["261027-0002"]))
        self.assertEqual(t["schedule"], [{"date": "2026-11-09",
                                          "sentence": "The suspension was set to end November 9, 2026."}])
        u = inspection.read_text((FIX / "fr_pi_raw_2026-22925.txt").read_bytes())
        self.assertEqual([x["date"] for x in u["schedule"]], ["2025-11-29"])  # the date the phrase governs, not the next
        m = inspection.read_text((FIX / "fr_pi_raw_2026-22867.txt").read_bytes())
        self.assertIn("further suspend", m["summary_first"])          # "the U.S. Trade Representative" is one sentence
        with self.assertRaises(ValueError):
            inspection.parse_issue(json.dumps({"count": 9, "results": []}), "2026-11-09")

    def test_hw_ind_2_on_the_real_extensions(self):
        recs = {r["id"]: r for r in _pi_records()}
        stay = recs["2026-22793"]
        self.assertEqual((stay["indicator_state"], stay["days_to_deadline"], stay["kind"]), ("present", 4, "stay_or_extension"))
        self.assertEqual([(m["basis"], m.get("doc")) for m in stay["matches"]],
                         [("same RIN 0694-AK34", "2025-19846"), ("the filing says it was scheduled", None)])
        for doc, earlier in (("2026-22925", "2025-21671"), ("2026-22867", "2025-19873")):
            r = recs[doc]
            self.assertEqual((r["indicator_state"], r["days_to_deadline"], r["matches"][0]["basis"], r["matches"][0]["doc"]),
                             ("present", 0, "same investigation", earlier))
        self.assertEqual((recs["2026-22868"]["indicator_state"], recs["2026-22868"]["matches"]), ("absent", []))
        self.assertEqual(inspection.counted(list(recs.values())), {"BIS": 2, "OFAC": 2})
        self.assertNotIn("indicator_state", recs["2026-22861"])

    def test_a_filing_without_text_is_no_data_unless_matched(self):
        recs = _pi_records()
        for r in recs:
            r.pop("text", None)
        recs = {r["id"]: r for r in inspection.match(recs, [])}
        self.assertEqual(recs["2026-22793"]["indicator_state"], "no_data")
        self.assertEqual(recs["2026-22868"]["indicator_state"], "no_data")

    def test_merge_keeps_first_sight_and_text(self):
        read = inspection.parse_issue(text("fr_pi_2026-11-05.json"), "2026-11-05")
        first = inspection.merge([], read, "2026-11-05T22:00:00Z", date(2026, 11, 5))
        self.assertEqual(first[0]["id"], "2026-22793")                 # newest filing first
        first[0]["text"] = {"action": "kept"}
        again = {r["id"]: r for r in inspection.merge(first, read, "2026-11-06T04:00:00Z", date(2026, 11, 6))}
        self.assertEqual((again["2026-22793"]["first_seen_at"], again["2026-22793"]["text"]),
                         ("2026-11-05T22:00:00Z", {"action": "kept"}))
        changed = [dict(r, pdf_updated_at="2026-11-06T09:00:00.000-05:00") for r in read]
        redone = {r["id"]: r for r in inspection.merge(first, changed, "2026-11-06T16:00:00Z", date(2026, 11, 6))}
        self.assertNotIn("text", redone["2026-22793"])                 # a replaced PDF is read again
        self.assertEqual(inspection.merge(first, [], "2026-12-10T00:00:00Z", date(2026, 12, 10)), [])   # 30 days

    def test_feed_items(self):
        snap = {"generated_at": "2026-11-10T12:00:00Z", "lanes": {}, "inspection": _pi_records()}
        fc = {"features": feed.inspection_features(snap, "2026-11-10T12:00:00Z", "2026-11-12T12:00:00Z", None)}
        self.assertEqual(lint(fc), [])
        props = {f["properties"]["id"]: f["properties"] for f in fc["features"]}
        self.assertEqual(sorted(props), ["headwind:inspection:2026-22793", "headwind:inspection:2026-22867",
                                         "headwind:inspection:2026-22868", "headwind:inspection:2026-22925"])
        p = props["headwind:inspection:2026-22793"]
        self.assertEqual((p["kind"], p["tier"], p["indicator_id"], p["hypothesis_id"], p["direction"], p["indicator_state"]),
                         ("observation", "routine", "HW-IND-2", "HW-H-1B", "supports", "present"))
        self.assertEqual((p["measures"]["days_to_deadline"], p["data_as_of"], p["requirement_ids"]),
                         (4, "2026-11-05T21:15:00Z", ["HW-EEI-2", "HW-PIR-2"]))
        self.assertIn("filed 4 days before a date that document 2025-19846 (same RIN 0694-AK34) set", p["summary"])
        self.assertEqual(props["headwind:inspection:2026-22868"]["direction"], "neutral")
        self.assertEqual(props["headwind:inspection:2026-22925"]["countries"], ["CN"])
        self.assertNotIn("Sanctions Action", json.dumps(fc))          # OFAC and BIS notices are not items
        later = feed.inspection_features(dict(snap, generated_at="2026-11-20T12:00:00Z"), "2026-11-20T12:00:00Z",
                                         "2026-11-22T12:00:00Z", None)
        self.assertEqual(later, [])                                     # in the feed 7 days from filing

    def test_lane_reads_each_text_once(self):
        tmp = Path(tempfile.mkdtemp())
        calls = []

        def counting(url, timeout=60):
            if "public-inspection/raw_text/" in url:
                calls.append(url)
            return fake_getter(url, timeout)
        try:
            with mock.patch.object(headwind_cli, "date", FixedDate):
                out, recs = headwind_cli._lane_inspection(tmp / "raw", {}, counting)
                self.assertEqual(len(out["inspection_issues"]), 30)      # a first run reads back 30 days
                out["lanes"] = {"inspection": {"fetched_at": "2026-11-09T09:00:00Z"}}
                self.assertEqual(len(out["inspection"]), 8)
                self.assertEqual(len(calls), 4)                         # rules and USTR notices only
                self.assertTrue(next(r for r in out["inspection"] if r["id"] == "2026-22793")["text"]["rins"])
                calls.clear()
                again, _ = headwind_cli._lane_inspection(tmp / "raw", out, counting)
                self.assertEqual(calls, [])                             # same PDFs, texts kept
                self.assertEqual([d["day"] for d in again["inspection_issues"]],
                                 ["2026-11-09", "2026-11-08", "2026-11-07", "2026-11-06", "2026-11-05"])
                self.assertEqual((inspection.days_to_read(date(2026, 11, 20), "2026-11-09T09:00:00Z"),
                                  inspection.days_to_read(date(2026, 11, 20), None)), (16, 30))
                self.assertEqual(len(again["inspection"]), 8)
                h = health.build({"generated_at": "2026-11-09T15:00:00Z", "lanes": {"inspection": {"status": "ok"}},
                                  **again}, {}, date(2026, 11, 9))["fr-public-inspection"]
                self.assertEqual((h["state"], h["lane"]), ("up", "inspection"))
                self.assertIn("8 BIS, OFAC and USTR filings in the last 30 days (4 counted only), 2 of 5 days",
                              h["detail"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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
            self.assertEqual([w["country"] for w in snap["market_fx"]], ["SD"])
            self.assertEqual(sorted(o["country"] for o in snap["fx_official"]), ["CD", "LB", "PH", "SD", "YE"])
            self.assertIn("worldbank-gem", snap["health"])
            self.assertEqual(len(snap["country_view"]), len(feed.WATCHED))
            self.assertTrue(any(m["reason"].startswith("no WFP") for m in snap["local_food_missing"]))
            self.assertTrue((tmp / "data" / "raw" / "index.jsonl").exists())
            self.assertEqual(snap["sanctions"], [])                 # the first run only sets the baseline
            self.assertEqual([(l["id"], l["total"]) for l in snap["sanctions_lists"]],
                             [("ofac-sdn", 36), ("un-consolidated", 14), ("eu-fsf", 9), ("uk-sanctions", 11)])
            self.assertTrue(list((tmp / "data" / "raw" / "eu-fsf").glob("*.xml.gz")))
            self.assertEqual(len(snap["controls"]), 8)              # 5 rules and 3 USTR notices (one left out)
            self.assertEqual(snap["lanes"]["inspection"]["status"], "ok")
            self.assertIn("fr-public-inspection", snap["health"])
            self.assertTrue((tmp / "data" / "state" / "sanctions_index.json").exists())
            self.assertEqual(snap["screening"], [])                 # first reading
            self.assertEqual(len(snap["screening_lists"]), 12)
            self.assertTrue(list((tmp / "data" / "raw" / "trade-gov-csl").glob("*.json.gz")))
            self.assertEqual(len(snap["minerals"]["reliance"]), 68)
            files = headwind_cli.build_site(tmp)
            for name in ("data/feed.geojson", "data/events.json", "data/baseline.json", "data/question_drafts.json",
                         "data/minerals.json", "index.html"):
                self.assertIn(name, files)
            self.assertEqual(headwind_cli.check_all(tmp), [])
            # The kit's history log ends an item only when its lane (the item's first source id) is in the health
            # record; an item whose lane is missing would never end.
            fc = json.loads(files["data/feed.geojson"])
            self.assertTrue({f["properties"]["sources"][0]["id"] for f in fc["features"]} <= set(fc["health"]))
            from tic_doctrine import history as tic_history
            from datetime import datetime
            now = datetime.fromisoformat(fc["generated_at"].replace("Z", "+00:00"))
            _, lines = tic_history.update({}, fc, fc["health"], now, [])
            self.assertEqual({l["change"] for l in lines}, {"new"})
            self.assertEqual(len(lines), len(fc["features"]))
            wf = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
            self.assertIn("tic.py history site/data/feed.geojson --dir history --ended site/data/ended.geojson", wf)

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

            # One list that cannot be read keeps its last reading and says so; the others go on.
            def eu_down(url, timeout=60):
                if "webgate.ec.europa.eu" in url:
                    raise OSError("EU server down")
                return fake_getter(url, timeout)
            partial = headwind_cli.collect(tmp, getter=eu_down)
            self.assertEqual(partial["lanes"]["sanctions"]["status"], "ok")
            eu = next(l for l in partial["sanctions_lists"] if l["id"] == "eu-fsf")
            self.assertEqual((eu["total"], "EU server down" in eu["error"]), (9, True))
            kept = json.loads((tmp / "data" / "state" / "sanctions_index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(kept["eu-fsf"]["index"]), 9)       # the EU baseline survives the failed read

            # A list that changes between runs is reported once, as counts.
            def changed(url, timeout=60):
                body = fake_getter(url, timeout)
                if "sdn.csv" in url:
                    lines = body.decode("utf-8").splitlines()[1:]
                    lines.append("99999,TEST HULL,vessel,RUSSIA-EO14024,-0- ,-0- ,Crude Oil Tanker,-0- ,-0- ,Panama,"
                                 "-0- ,Vessel Registration Identification IMO 9999993.")
                    return ("\n".join(lines) + "\n").encode("utf-8")
                if "data.trade.gov" in url:
                    doc = json.loads(body)
                    doc["results"].append({"source": "Entity List (EL) - Bureau of Industry and Security",
                                           "id": "added-1", "addresses": [{"country": "CN"}]})
                    doc["total"] += 1
                    return json.dumps(doc).encode("utf-8")
                return body
            third = headwind_cli.collect(tmp, getter=changed)
            self.assertEqual([(d["list"], d["added"], d["removed"]) for d in third["sanctions"]], [("ofac-sdn", 1, 1)])
            fourth = headwind_cli.collect(tmp, getter=changed)
            self.assertEqual(len(fourth["sanctions"]), 1)           # kept, not reported a second time
            self.assertEqual([(d["list"], d["added"], d["removed"]) for d in fourth["screening"]], [("EL", 1, 0)])
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
            self.assertEqual((snap["screening"], snap["screening_lists"], snap["minerals"]), ([], [], {}))
            self.assertEqual(feed.build_feed(snap)["features"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
