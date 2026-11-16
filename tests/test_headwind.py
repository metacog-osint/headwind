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
import xml.etree.ElementTree as ET
import zipfile
from unittest import mock
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import scotus, unpress  # noqa: E402
from headwind import (baseline, batches, controls, feed, food, health, inspection, markets, minerals, releases,  # noqa: E402
                      sanctions, screening, stats, tariffs, trade)
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
    if "federalregister.gov/api/v1/documents.json" in url and "PRESDOCU" in url:
        return (FIX / "fr_presidential.json").read_bytes()
    if "federalregister.gov/api/v1/documents.json" in url and "section+232" in url:
        return (FIX / "fr_section232.json").read_bytes()
    if "federalregister.gov/documents/full_text/text/" in url:
        f = FIX / f"fr_pres_raw_{url.rsplit('/', 1)[1].removesuffix('.txt')}.txt"
        if f.exists():
            return f.read_bytes()
        raise OSError(f"no fixture for {url}")
    if "hts.usitc.gov/reststop/releaseList" in url:
        return (FIX / "hts_releases.json").read_bytes()
    if "whitehouse.gov/presidential-actions/feed" in url:
        return (FIX / "wh_presidential_actions.xml").read_bytes()
    if "federalregister.gov/api/v1/documents.json" in url and "type%5D%5B%5D=NOTICE" in url:
        return (FIX / ("fr_ustr_notices.json" if "fields%5B%5D=abstract" in url else "fr_register_ustr.json")).read_bytes()
    if "federalregister.gov/api/v1/documents.json" in url and "fields%5B%5D=abstract" not in url:
        return (FIX / "fr_register_rules.json").read_bytes()
    if "api.census.gov" in url:
        code = re.search(r"I_COMMODITY=(\d+)", url).group(1)
        f = FIX / f"census_{code}.json"
        return f.read_bytes() if f.exists() else b""         # Census answers 204, no body, for a code with no rows
    if "slipopinion_rss.aspx" in url:
        f = FIX / f"scotus_feed_{re.search(r'TYear=(\d+)', url).group(1)}.xml"
        return (f if f.exists() else FIX / "scotus_feed_26.xml").read_bytes()
    if "supremecourt.gov/RSS/Cases/JSON/" in url:
        f = FIX / f"scotus_docket_{url.rsplit('/', 1)[1][:-5]}.json"
        if not f.exists():
            raise OSError(f"no fixture for {url}")         # the lane notes it and goes on
        return f.read_bytes()
    if "api.worldbank.org" in url and "source=15" in url:
        return (FIX / "worldbank_gem.json").read_bytes()
    table = [("petroleum/pri/spt", "eia_petroleum.json"), ("natural-gas/pri/fut", "eia_natural_gas.json"),
             ("foodpricesindex", "fao_page.html"),
             ("food_price_indices_data.csv", "fao.csv"), ("package_search", "hdx.json"),
             ("wfp_food_prices_sdn.csv", "wfp_sdn.csv"), ("api.worldbank.org", "worldbank.json"),
             ("fomccalendars", "fomc.html"), ("calendars/mgcgc", "ecb_calendar.html"),
             ("ofac/downloads/sdn.csv", "ofac_sdn.csv"), ("scsanctions.un.org", "un_consolidated.xml"),
             ("fsd/fsf/public/files/xmlFullSanctionsList_1_1", "eu_fsf.xml"),
             ("sanctionslist.fcdo.gov.uk", "uk_sanctions.xml"), ("gels-avoirs.dgtresor.gouv.fr", "fr_gels.json"),
             ("sanctions/sema-lmes.xml", "canada_sema.xml"), ("press.un.org/en/rss.xml", "un_press.xml"),
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
        self.assertEqual((s["imo_numbers"], s["on_both"], s["only"]), (15, 1, {"ofac-sdn": 8, "uk-sanctions": 6, "france-gels": 0, "canada-sema": 0}))
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


class TestFrance(unittest.TestCase):
    """France's Registre national des gels, cut redacted from the 6 Nov 2026 file and the 7 Aug 2026 Wayback copy
    (people keep id, type and legal bases only; ships their name and IMO number)."""

    def readings(self):
        _, old = sanctions.parse_fr_json((FIX / "fr_gels_2026-08-07.json").read_bytes())
        gen, new = sanctions.parse_fr_json((FIX / "fr_gels.json").read_bytes())
        return gen, old, new

    def test_parse(self):
        gen, old, new = self.readings()
        self.assertEqual(gen[:10], "2026-11-06")
        self.assertEqual((len(old), len(new)), (16, 20))
        self.assertEqual(sanctions._tally(new, new)[0], {"entity": 2, "individual": 15, "vessel": 3})
        self.assertEqual(new["1121"][1], ["FR national, art L. 562-3"])
        self.assertEqual({sanctions.fr_origin(g) for e in new.values() for g in e[1]}, {"national", "EU", "UN"})
        self.assertEqual(sanctions.unknown_programs("france-gels", new), [])
        self.assertEqual(sanctions.unknown_programs("france-gels", {"1": ["entity", ["Dispositif inconnu"]]}),
                         ["Dispositif inconnu"])
        # headwind-1.9: people and organizations carry a name and countries only, ships their public fields.
        self.assertTrue(all(len(e) == 3 and sorted(e[2]) == ["countries", "name"] and e[2]["name"]
                            for e in new.values() if e[0] != "vessel"))

    def test_regime_labels(self):
        self.assertEqual(sanctions.fr_regime("(UE) 2022/332 du 25/02/2022 (UE Ukraine intégrité territoriale - "
                                             "R (UE) 269/2014)"), "UE Ukraine intégrité territoriale")
        self.assertEqual(sanctions.fr_regime(" ECOT2628560A du 06/11/2026 (Dispositif national de gel des avoirs - art "
                                             "L. 562-3 du code monétaire et financier)"), "FR national, art L. 562-3")
        self.assertEqual(sanctions.fr_regime("ECOT2616999A du 30/07/2026 (Dispositif national de gel des avoirs - art "
                                             "L. 562-2-1 du code monétaire et financier)"), "FR national, art L. 562-2-1")
        self.assertEqual(sanctions.fr_origin("ONU Corée du Nord"), "UN")
        self.assertEqual(sanctions.fr_origin("UE Russie répression R (UE) 2024/1485"), "EU")

    def test_ship_names_drop_the_owner(self):
        _, old, new = self.readings()
        self.assertEqual(sanctions.fr_ship_name("Ocean Maritime Management Company, Limited - navire HUI CHON"), "HUI CHON")
        self.assertEqual(old["2218"][2], {"name": "HUI CHON", "imo": "8405270", "mmsi": None, "flag": None,
                                          "vessel_type": None})
        self.assertEqual(old["2218"][2], new["2218"][2])          # the August owner prefix is not a rename

    def test_national_counted_apart(self):
        _, old, new = self.readings()
        d = sanctions.delta("france-gels", old, new, "2026-11-15T20:00:00Z", "2026-08-07T16:25:20Z")
        self.assertEqual((d["added"], d["removed"], d["changed"]), (6, 2, 0))
        n = d["national"]
        self.assertEqual((n["added"], n["removed"], n["added_by_type"]), (3, 0, {"entity": 1, "individual": 2}))
        self.assertEqual(d["restated"], {"added": 3, "removed": 2, "changed": 0})
        self.assertEqual([(b["basis"], b["added"]) for b in d["batches"]], [("headwind readings", 3)])
        self.assertEqual((d["countries"], d["vessels_changed"]), ([], []))
        # An EU package of 300 restated in France scores nothing; three national freezes are the batch.
        big = {**new, **{f"x{i}": ["entity", ["UE Russie"]] for i in range(300)}}
        d2 = sanctions.delta("france-gels", new, big, "2026-11-16T00:00:00Z", None, added_history=[2] * 30)
        self.assertEqual((d2["national"]["added"], d2["restated"]["added"], d2["batches"], d2["anomaly"]),
                         (0, 300, [], False))

    def test_feed_item(self):
        _, old, new = self.readings()
        d = sanctions.delta("france-gels", old, new, "2026-11-15T20:00:00Z", "2026-08-07T16:25:20Z")
        snap = {"generated_at": "2026-11-15T20:00:00Z", "sanctions": [d], "lanes": {}}
        f = next(x for x in feed.list_features(snap) if x["properties"]["id"].startswith("headwind:sanctions:"))
        p = f["properties"]
        self.assertEqual(p["title"], "France's asset-freeze register (Registre national des gels): 3 national freezes "
                                     "added, 0 removed; 3 added and 2 removed restating EU and UN measures")
        self.assertIn("counted here but not scored and place no country: 3 added, 2 removed, 0 changed.", p["summary"])
        self.assertEqual((p["measures"]["national_added"], p["measures"]["restated_removed"]), (3, 2))
        self.assertEqual(p["sources"][0]["id"], "dgtresor-gels")
        self.assertEqual(lint({"features": [f]}), [])

    def test_ships_cross_listed(self):
        ofac = sanctions.parse_sdn_csv(text("ofac_sdn.csv").rstrip("\n") + "\n" + text("crosslist_ofac.csv"))
        _, uk = sanctions.parse_uk_xml((FIX / "crosslist_uk.xml").read_bytes())
        _, _, fr = self.readings()
        s, t = sanctions.vessel_crosslist({"ofac-sdn": ofac, "uk-sanctions": uk, "france-gels": fr})
        r = next(r for r in t if r["imo"] == "7303803")
        self.assertEqual(sorted(r["on"]), ["france-gels", "ofac-sdn", "uk-sanctions"])
        self.assertEqual(r["on"]["france-gels"], {"ids": ["2205"], "name": "AN SAN 1", "flag": None})
        self.assertEqual((s["on_both"], s["combos"]["france-gels+ofac-sdn+uk-sanctions"]), (1, 1))
        self.assertGreaterEqual(s["on_two_or_more"], 1)

    def test_health_entry(self):
        self.assertEqual(health.LIST_KEY["france-gels"], "dgtresor-gels")
        self.assertEqual(health.LANE_OF["dgtresor-gels"], "sanctions")


class TestCanada(unittest.TestCase):
    """Canada's consolidated autonomous sanctions list, 24 records cut redacted from the file of 10 Nov 2026 (people:
    regime, schedule, item and listing date, the name replaced by PERSON-<hash>; ships: name, IMO and type)."""

    def read(self):
        dates, names = {}, {}
        _, idx = sanctions.parse_canada_xml((FIX / "canada_sema.xml").read_bytes(), dates, names)
        return idx, dates, names

    def test_parse(self):
        idx, dates, names = self.read()
        self.assertEqual(len(idx), 24)
        self.assertEqual(sanctions._tally(idx, idx)[0], {"entity": 8, "individual": 13, "vessel": 3})
        self.assertEqual(sanctions.unknown_programs("canada-sema", idx), [])
        self.assertTrue(any(k.startswith("Moldova|") for k in idx))         # "Moldova " in the file
        self.assertTrue(any("|1, Part 3|" in k for k in idx))               # "1,Part 3" in the file
        self.assertTrue(all(dates[k] for k in idx))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{12}", names[k]) for k in idx))
        self.assertTrue(all(len(e) == 3 and e[2]["name"] and e[2]["countries"] == []    # Canada prints no address
                            for e in idx.values() if e[0] != "vessel"))
        ship = next(e[2] for e in idx.values() if e[0] == "vessel")
        self.assertEqual(sorted(ship), ["flag", "imo", "mmsi", "name", "vessel_type"])
        self.assertTrue(re.fullmatch(r"\d{7}", ship["imo"]) and ship["vessel_type"] and ship["name"])

    def test_keys_are_regime_schedule_item(self):
        rec = ET.fromstring("<record><Country-Pays>Belarus / B\u00e9larus</Country-Pays><Schedule-Annexe>1,Part 3 "
                            "</Schedule-Annexe><Item-NumeroDarticle> 7</Item-NumeroDarticle></record>")
        self.assertEqual(sanctions.canada_key(rec), "Belarus|1, Part 3|7")
        dup = b"<data-set>" + b"<record><Country-Pays>Iran</Country-Pays><Item-NumeroDarticle>1</Item-NumeroDarticle></record>" * 2 + b"</data-set>"
        with self.assertRaises(ValueError):
            sanctions.parse_canada_xml(dup)

    def test_change_dated_batches_and_countries(self):
        idx, dates, _ = self.read()
        hamas = next(k for k in idx if k.startswith("Hamas"))
        russian = sorted(k for k in idx if k.startswith("Russia|") and dates[k] == "2022-02-24")
        prev = {k: v for k, v in idx.items() if k not in russian and k != hamas}
        d = sanctions.delta("canada-sema", prev, idx, "2026-11-16T06:00:00Z", "2026-11-15T06:00:00Z", dates=dates)
        self.assertEqual((d["added"], d["countries"]), (len(russian) + 1, ["RU"]))
        self.assertIn(("designation date", "2022-02-24"), [(b["basis"], b["date"]) for b in d["batches"]])

    def test_renumbered_items_are_not_removals(self):
        idx, _, names = self.read()
        people = sorted(k for k in idx if idx[k][0] == "individual" and k.startswith("Russia|"))
        moved, dropped = people[0], people[1]
        new_key = moved.rsplit("|", 1)[0] + "|999"
        new = {(new_key if k == moved else k): v for k, v in idx.items() if k != dropped}
        new_names = {(new_key if k == moved else k): v for k, v in names.items() if k != dropped}
        pairs = sanctions.canada_renumbered(idx, new, names, new_names)
        self.assertEqual(pairs, [(moved, new_key)])
        d = sanctions.delta("canada-sema", sanctions.apply_renumbering(idx, pairs), new, "2026-11-16T06:00:00Z", None)
        self.assertEqual((d["added"], d["removed"]), (0, 1))
        self.assertEqual(sanctions.canada_renumbered(idx, new, None, new_names), [])     # no hashes before: no pairing

    def test_real_renumbering_8_to_10_nov(self):
        """Canada moved four records listed 4 Sep 2026 from items 1700-1703 to 1620-1623 (Russia, Schedule 1, Part 1)
        between its files of 8 Nov (Wayback) and 10 Nov 2026; cut redacted, with three records that did not move."""
        na, nb = {}, {}
        _, a = sanctions.parse_canada_xml((FIX / "canada_renumber_2026-11-08.xml").read_bytes(), None, na)
        _, b = sanctions.parse_canada_xml((FIX / "canada_renumber_2026-11-10.xml").read_bytes(), None, nb)
        pairs = sanctions.canada_renumbered(a, b, na, nb)
        self.assertEqual(pairs, [(f"Russia|1, Part 1|{o}", f"Russia|1, Part 1|{o - 80}") for o in range(1700, 1704)])
        self.assertIsNone(sanctions.delta("canada-sema", sanctions.apply_renumbering(a, pairs), b,
                                          "2026-11-10T12:00:00Z", None))
        d = sanctions.delta("canada-sema", a, b, "2026-11-10T12:00:00Z", None)              # without the guard
        self.assertEqual((d["added"], d["removed"]), (4, 4))

    def test_a_new_layout_fails_loudly(self):
        old = b"<data-set>" + b"<record><Country>Iran</Country><Item>1</Item></record>" * 2 + b"</data-set>"
        with self.assertRaisesRegex(ValueError, "layout"):
            sanctions.parse_canada_xml(old)

    def test_ships_cross_listed(self):
        idx, _, _ = self.read()
        s, t = sanctions.vessel_crosslist({"canada-sema": idx})
        self.assertEqual((s["only"]["canada-sema"], s["without_imo"]["canada-sema"]), (3, 0))


class TestUnPress(unittest.TestCase):
    """UN press feed: the copy of 13 Nov 2026 and a Wayback copy of 2 Jul 2026, cut redacted (titles kept only on
    Security Council releases, which the classifier reads)."""

    def test_live_copy_has_no_committee_release(self):
        items = unpress.parse((FIX / "un_press.xml").read_bytes())
        self.assertEqual(len(items), 10)
        import gzip
        self.assertEqual(unpress.parse(gzip.compress((FIX / "un_press.xml").read_bytes())), items)   # as the UN sends it
        self.assertEqual([r for r in map(unpress.committee_release, items) if r], [])

    def test_committee_release(self):
        items = unpress.parse((FIX / "un_press_2026-07-02.xml").read_bytes())
        found = [r for r in map(unpress.committee_release, items) if r]
        self.assertEqual([r["id"] for r in found], ["SC/16404"])
        self.assertEqual(found[0]["url"], "https://press.un.org/en/2026/sc16404.doc.htm")
        self.assertEqual(sorted(found[0]), ["id", "published", "url"])                 # no title is kept

    def test_which_titles_count(self):
        def one(title, link="https://press.un.org/en/2026/sc16488.doc.htm"):
            return unpress.committee_release({"title": title, "link": link, "published": "2026-10-26T20:00:00Z"})
        self.assertIsNotNone(one("Security Council ISIL (Da'esh) and Al-Qaida Sanctions Committee Removes Three Entries"))
        self.assertIsNotNone(one("Security Council Committee Established Pursuant to Resolution 1718 (2006) Adds One Entry"))
        self.assertIsNone(one("Security Council Committee Established Pursuant to Resolution 1540 (2004) Holds Meeting"))
        self.assertIsNone(one("Security Council Extends Mandate of Sanctions Panel"))
        self.assertIsNone(one("Sanctions Committee Chair Briefs", link="https://press.un.org/en/2026/sgsm23373.doc.htm"))

    def test_coverage_and_merge(self):
        items = unpress.parse((FIX / "un_press.xml").read_bytes())
        c = unpress.coverage(items, "2026-11-13T12:00:00Z", "2026-11-14T00:00:00Z")
        self.assertEqual((c["oldest"], c["may_have_missed"]), ("2026-11-13T16:42:12Z", True))
        self.assertFalse(unpress.coverage(items, "2026-11-13T17:00:00Z", "2026-11-14T00:00:00Z")["may_have_missed"])
        self.assertFalse(unpress.coverage(items, None, "2026-11-14T00:00:00Z")["may_have_missed"])
        r = {"id": "SC/16404", "published": "2026-07-01T20:00:00Z", "url": "u"}
        kept = unpress.merge([], [r], "2026-07-02T00:00:00Z")
        self.assertEqual(unpress.merge(kept, [r], "2026-07-03T00:00:00Z"), kept)          # seen once
        self.assertEqual(unpress.merge(kept, [], "2026-09-15T00:00:00Z"), [])              # gone after 60 days
        with self.assertRaises(ValueError):
            unpress.parse(b"<html><title>Client Challenge</title></html>")

    def test_feed_item(self):
        items = unpress.parse((FIX / "un_press_2026-07-02.xml").read_bytes())
        rel = unpress.merge([], [r for r in map(unpress.committee_release, items) if r], "2026-07-02T09:31:52Z")
        snap = {"generated_at": "2026-07-05T00:00:00Z", "un_committee_releases": rel, "lanes": {}}
        f = feed.unpress_features(snap, snap["generated_at"], "2026-07-07T00:00:00Z")
        self.assertEqual([x["properties"]["id"] for x in f], ["headwind:unpress:sc16404"])
        p = f[0]["properties"]
        self.assertTrue(p["title"].startswith("UN Security Council sanctions committee press release SC/16404 (2026-07-0"))
        self.assertNotIn("2745", p["title"] + p["summary"])                                # nothing of the release's words
        self.assertEqual(lint({"features": f}), [])
        self.assertEqual(feed.unpress_features({**snap, "generated_at": "2026-07-30T00:00:00Z"}, "2026-07-30T00:00:00Z",
                                               "2026-08-01T00:00:00Z"), [])


class TestScotus(unittest.TestCase):
    """The Supreme Court's slip opinion feeds (2025 and 2026 terms, read 16 Nov 2026, cut to nine items with the
    syllabus text dropped) and seven dockets (titles, lower court, related dockets, the opinion entry and the newest
    entry only; attorneys and contact details dropped)."""

    def feeds(self):
        return (scotus.parse_feed((FIX / "scotus_feed_25.xml").read_bytes(), 25)
                + scotus.parse_feed((FIX / "scotus_feed_26.xml").read_bytes(), 26))

    def dockets(self):
        return {p.stem[len("scotus_docket_"):]: scotus.parse_docket(p.read_bytes())
                for p in FIX.glob("scotus_docket_*.json")}

    def test_terms(self):
        self.assertEqual(scotus.term_years(date(2026, 11, 16)), (26, 25))
        self.assertEqual(scotus.term_years(date(2026, 9, 30)), (25, 24))

    def test_feed(self):
        ops = self.feeds()
        self.assertEqual(len(ops), 8)                                      # the decree in 141, Orig. is not an opinion
        lr = next(o for o in ops if o["docket"] == "24-1287")
        self.assertEqual((lr["title"], lr["kind"], lr["author"], lr["term"]),
                         ("Learning Resources, Inc. v. Trump", "signed", "Chief Justice John G. Roberts, Jr.", "25"))
        self.assertTrue(lr["link"].startswith("https://www.supremecourt.gov/opinions/"))
        self.assertEqual(next(o["title"] for o in ops if o["docket"] == "24-699"),
                         "Exxon Mobil Corp. v. Corporaci\u00f3n Cimex, S. A. (Cuba)")
        self.assertEqual({o["kind"] for o in ops if o["docket"] in ("26A124", "26A476", "26A560")}, {"per curiam"})

    def test_docket(self):
        d = self.dockets()["24-1287"]
        self.assertEqual((d["decided"], d["related"], d["last_entry"]),
                         ("2026-02-20", ["25-250"], {"date": "2026-03-24", "text": "Judgment Issued."}))
        self.assertEqual(d["decision"], "Judgment in No. 24-1287 is VACATED and case REMANDED with instructions to "
                                        "dismiss for lack of jurisdiction; the judgment in No. 25-250 is AFFIRMED.")
        self.assertEqual(self.dockets()["25-250"]["decision"], "Adjudged to be AFFIRMED. Judgment in No. 24-1287 is "
                         "VACATED and case REMANDED with instructions to dismiss for lack of jurisdiction.")
        self.assertEqual(d["petitioner"], "Learning Resources, Inc., et al., Petitioners")
        self.assertEqual(self.dockets()["26A476"]["decided"], "2026-10-14")
        # 25A312's opinion entry (29 Jun 2026) names the opinion without linking it.
        bare = {"CaseNumber": "25A312", "ProceedingsandOrder": [
            {"Date": "Jan 21 2026", "Text": "Argued."},
            {"Date": "Jun 29 2026", "Text": "Application (25A312) denied by the Court.  Roberts, C. J., delivered the "
                                            "opinion of the Court."}]}
        self.assertEqual(scotus.parse_docket(json.dumps(bare).encode())["decided"], "2026-06-29")

    def test_us_person_data(self):
        self.assertEqual(scotus.us_person_data("Learning Resources, Inc. v. Trump"), "individuals")
        self.assertEqual(scotus.us_person_data("Exxon Mobil Corp. v. Corporaci\u00f3n Cimex, S. A. (Cuba)"), "organizations")
        self.assertEqual(scotus.us_person_data("FCC v. AT&T"), "organizations")
        self.assertEqual(scotus.us_person_data("Texas v. New Mexico"), "none")
        self.assertEqual(scotus.us_person_data("West Virginia v. B. P. J."), "individuals")
        self.assertEqual(scotus.party_kind("Illinois Bd. of Elections"), "government")
        self.assertEqual(scotus.party_kind("Mullin"), "person")            # an official named in office is a person

    def test_merge_and_features(self):
        ops = scotus.merge([], self.feeds(), self.dockets(), "2026-11-16T06:00:00Z")
        self.assertEqual(ops[0]["docket"], "26A560")                       # no docket read: sorted by its posting day
        self.assertEqual(next(o for o in ops if o["docket"] == "24-1287")["decided"], "2026-02-20")
        again = scotus.merge(ops, self.feeds(), {}, "2026-11-17T06:00:00Z")
        self.assertEqual(next(o for o in again if o["docket"] == "24-1287")["first_seen"], "2026-11-16T06:00:00Z")
        self.assertEqual(scotus.needs_docket(ops), ["26A560", "24-699"])
        snap = {"generated_at": "2026-11-16T06:00:00Z", "scotus_opinions": ops, "lanes": {}}
        f = feed.scotus_features(snap, snap["generated_at"], "2026-11-18T06:00:00Z")
        self.assertEqual([x["properties"]["id"] for x in f], ["headwind:scotus:26A560"])
        self.assertIn("the decision date was not read from the docket", f[0]["properties"]["summary"])
        snap = {"generated_at": "2026-02-25T06:00:00Z", "scotus_opinions": ops, "lanes": {}}
        f = feed.scotus_features(snap, snap["generated_at"], "2026-02-27T06:00:00Z")
        p = next(x["properties"] for x in f if x["properties"]["id"] == "headwind:scotus:24-1287")
        self.assertEqual(p["title"], "Supreme Court of the United States: Learning Resources, Inc. v. Trump, No. 24-1287 "
                                     "(2026-02-20)")
        self.assertIn("an opinion of the Court delivered by Chief Justice John G. Roberts, Jr.", p["summary"])
        self.assertEqual((p["us_person_data"], p["countries"]), ("individuals", ["US"]))
        self.assertEqual(lint({"features": f}), [])

    def test_tracked_docket_item(self):
        t = {**self.dockets()["24-1287"], "url": scotus.DOCKET_PAGE.format(docket="24-1287")}
        snap = {"generated_at": "2026-03-30T06:00:00Z", "scotus_tracked": [t], "lanes": {}}
        f = feed.scotus_features(snap, snap["generated_at"], "2026-04-01T06:00:00Z")
        self.assertEqual([x["properties"]["id"] for x in f], ["headwind:scotusdocket:24-1287:2026-03-24"])
        self.assertIn('"Judgment Issued."', f[0]["properties"]["summary"])
        self.assertEqual(lint({"features": f}), [])


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
        self.assertEqual(idx["36"][:2], ["entity", ["CUBA"]])       # a blank type is an entity
        ships = {k: v[2] for k, v in idx.items() if v[0] == "vessel"}
        self.assertEqual(ships["15042"]["imo"] and len(ships["15042"]["imo"]), 7)
        self.assertTrue(all(s["name"] for s in ships.values()))
        # headwind-1.9: people and organizations carry a name and countries, nothing more (this fixture was cut with
        # names blanked, so they read as no name).
        self.assertTrue(all(len(v) == 3 and sorted(v[2]) == ["countries", "name"] for v in idx.values() if v[0] != "vessel"))
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
        self.assertTrue(all(len(v) == 3 and sorted(v[2]) == ["countries", "name"] for v in idx.values() if v[0] != "vessel"))
        self.assertTrue(all(v[2]["name"] for v in idx.values()))
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
        self.assertTrue(all(len(v) == 3 and sorted(v[2]) == ["countries", "name"] for v in idx.values() if v[0] != "vessel"))
        self.assertTrue(all(v[2]["name"] for v in idx.values()))
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
        # headwind-1.9: every filing is titled, OFAC's and BIS's notices too, with the register's own address.
        self.assertEqual([(r["id"], r["counted_only"]) for r in five],
                         [("2026-22725", False), ("2026-22726", False), ("2026-22793", False)])
        stay = five[2]
        self.assertEqual((stay["filed_at_utc"], stay["filed_on"], stay["publication_date"]),
                         ("2026-11-05T21:15:00Z", "2026-11-05", "2026-11-09"))
        self.assertTrue(all(r["title"] for r in five))
        self.assertTrue(five[0]["title"].startswith("Agency Information Collection Activities"))
        self.assertIn("/public-inspection/2026-22793/extension-of-the-suspension", stay["url"])   # titled: as given
        self.assertFalse(inspection.wants_text(five[0]))      # a party notice's text is still not read
        self.assertTrue(inspection.wants_text(stay))
        # A filing kept from before headwind-1.9 as counted only keeps the short form until it ages out.
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
        self.assertEqual(inspection.counted(list(recs.values())), {})
        self.assertNotIn("indicator_state", recs["2026-22861"])
        self.assertNotIn("indicator_state", recs["2026-22725"])   # HW-IND-2 is not measured on party notices

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
        self.assertEqual(sorted(props), ["headwind:inspection:2026-22725", "headwind:inspection:2026-22726",
                                         "headwind:inspection:2026-22793", "headwind:inspection:2026-22802",
                                         "headwind:inspection:2026-22861", "headwind:inspection:2026-22867",
                                         "headwind:inspection:2026-22868", "headwind:inspection:2026-22925"])
        self.assertEqual({p["us_person_data"] for p in props.values()}, {"none"})
        self.assertEqual(inspection.person_label({"agency": "BIS", "type": "Notice",
                                                  "title": "Order Denying Export Privileges"}), "individuals")
        self.assertEqual(inspection.person_label({"agency": "OFAC", "type": "Notice", "title": "Sanctions Action"}),
                         "none")
        p = props["headwind:inspection:2026-22793"]
        self.assertEqual((p["kind"], p["tier"], p["indicator_id"], p["hypothesis_id"], p["direction"], p["indicator_state"]),
                         ("observation", "routine", "HW-IND-2", "HW-H-1B", "supports", "present"))
        self.assertEqual((p["measures"]["days_to_deadline"], p["data_as_of"], p["requirement_ids"]),
                         (4, "2026-11-05T21:15:00Z", ["HW-EEI-2", "HW-PIR-2"]))
        self.assertIn("filed 4 days before a date that document 2025-19846 (same RIN 0694-AK34) set", p["summary"])
        self.assertEqual(props["headwind:inspection:2026-22868"]["direction"], "neutral")
        self.assertEqual(props["headwind:inspection:2026-22925"]["countries"], ["CN"])
        self.assertTrue(props["headwind:inspection:2026-22861"]["title"].endswith(": Sanctions Action"))   # titled since headwind-1.9
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
                self.assertIn("8 BIS, OFAC and USTR filings in the last 30 days, 2 of 5 days",
                              h["detail"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestTariffs(unittest.TestCase):
    """Tariff actions (presidential documents, Section 232 notices), HTS revisions and signed actions, on the
    replies read live on 15 Nov 2026."""

    def pres(self):
        return controls.parse_presidential((FIX / "fr_presidential.json").read_bytes())

    def test_presidential_keeps_tariff_actions_only(self):
        docs = self.pres()
        self.assertEqual(len(docs), 60)                     # of 85 in the fixture; the 25 others are not tariffs
        self.assertEqual({d["agency"] for d in docs}, {"President"})
        robot = next(d for d in docs if d["id"] == "2026-22385")
        self.assertEqual((robot["action"], robot["signing_date"], robot["published_date"]),
                         ("Proclamation", "2026-10-28", "2026-11-02"))
        self.assertFalse(any("Wildfire" in d["title"] for d in docs))
        self.assertEqual(sum(1 for d in docs if d["published_date"].startswith("2026")), 24)
        self.assertEqual(sum(1 for d in docs if d["published_date"].startswith("2025")), 36)
        canada = next(d for d in docs if d["id"] == "2026-22292")
        self.assertEqual(canada["countries"], ["CA"])

    def test_line_of_duty_is_not_a_tariff(self):
        self.assertFalse(controls.is_tariff("Honoring the Victims Killed in the Line of Duty"))
        self.assertTrue(controls.is_tariff("Adjusting Imports of Medium- and Heavy-Duty Vehicles"))
        self.assertTrue(controls.is_tariff("Continuing the Suspension of Duty-Free De Minimis Treatment"))

    def test_text_dates(self):
        t = (FIX / "fr_pres_raw_2026-22292.txt").read_text(encoding="utf-8")
        # Effective 12:01 a.m. on the day it was published; the 22 Aug date it recalls is earlier, so left out.
        self.assertEqual(controls.text_dates(t, "2026-10-30", "2026-10-23"), (["2026-10-30"], []))
        t = (FIX / "fr_pres_raw_2026-22385.txt").read_text(encoding="utf-8")
        # No tariff yet: an agreement within 180 days of the proclamation's date, counted from its signing.
        self.assertEqual(controls.text_dates(t, "2026-11-02", "2026-10-28"), ([], ["2027-04-26"]))

    def test_section232_notices(self):
        docs = controls.parse_section232((FIX / "fr_section232.json").read_bytes())
        ids = {d["id"] for d in docs}
        self.assertIn("2026-19498", ids)                    # tariff adjustments for specialty pharmaceuticals
        self.assertIn("2026-13663", ids)                    # comments on a Section 232 investigation
        self.assertNotIn("2026-22726", ids)                 # an information collection
        self.assertNotIn("2026-17619", ids)                 # an antidumping court decision
        # BIS and ITA; a notice issued with USTR (2025-21940, the Korea agreement) carries USTR's label.
        self.assertEqual({d["agency"] for d in docs}, {"BIS", "ITA", "USTR"})
        self.assertIn("2026-05681", ids)                    # an inclusions window opening

    def test_register_and_events_carry_presidential_dates(self):
        docs = self.pres()
        for d in docs:
            if d["id"] == "2026-22385":
                d["computed_dates"] = ["2027-04-26"]
        reg = controls.scheduled(docs, date(2026, 11, 15))
        e = next(x for x in reg if x["doc"] == "2026-22385")
        self.assertEqual((e["date"], e["agency"]), ("2027-04-26", "President"))
        self.assertIn("counted from its signing date", e["what"])
        ev = controls.build_events(docs, date(2026, 11, 15))
        self.assertTrue(any(x["ref"] == "2026-22385" and x["date"] == "2027-04-26" for x in ev))

    def test_pace(self):
        p = controls.pace(self.pres(), date(2026, 11, 15))
        self.assertEqual((p["count"], p["ids"]), (3, ["2026-22049", "2026-22292", "2026-22385"]))
        self.assertEqual(p["baseline_windows"], 27)
        self.assertFalse(p["anomaly"])                      # three is under the floor of four
        # One a window for 27 windows, then six in the latest: unusual.
        today = date(2026, 11, 15)
        from datetime import timedelta
        docs = [{"id": f"x{k}", "published_date": (today - timedelta(days=28 * k + 3)).isoformat()} for k in range(1, 28)]
        docs += [{"id": f"n{i}", "published_date": (today - timedelta(days=i)).isoformat()} for i in range(6)]
        p = controls.pace(docs, today)
        self.assertEqual((p["count"], p["median"]), (6, 1.0))
        self.assertTrue(p["anomaly"])

    def test_hts_releases(self):
        rel = tariffs.parse_releases((FIX / "hts_releases.json").read_bytes())
        self.assertEqual(len(rel), 186)
        self.assertEqual((rel[0]["name"], rel[0]["posted"], rel[0]["in_effect_from"]),
                         ("2026HTSRev23", "2026-11-09", "2026-11-10"))
        self.assertFalse(any("creator" in r for r in rel))
        years = tariffs.year_counts(rel)
        self.assertEqual((years["2025"], years["2026"]), (33, 23))
        p = tariffs.hts_pace(rel, date(2026, 11, 15))
        self.assertEqual(p["baseline_windows"], 27)
        self.assertIsNotNone(p["z"])

    def test_signed_actions_matched_to_the_register(self):
        signed = tariffs.parse_signed((FIX / "wh_presidential_actions.xml").read_bytes(), date(2026, 11, 15))
        self.assertEqual(len(signed), 3)
        self.assertTrue(all(s["url"].startswith("https://www.whitehouse.gov/presidential-actions/") for s in signed))
        tariffs.mark_published(signed, self.pres())
        self.assertEqual(sorted(s["fr_document"] for s in signed), ["2026-22049", "2026-22292", "2026-22385"])
        extra = [{"title": "Adjusting Imports of Something New", "url": "https://www.whitehouse.gov/x", "date": "2026-11-14"}]
        self.assertIsNone(tariffs.mark_published(extra, self.pres())[0]["fr_document"])

    def test_feed_items(self):
        docs = self.pres()
        snap = {"generated_at": "2026-11-15T12:00:00Z", "lanes": {}, "controls": [d for d in docs if d["published_date"] >= "2026-11-01"],
                "tariff_pace": controls.pace(docs, date(2026, 11, 15)),
                "hts_pace": tariffs.hts_pace(tariffs.parse_releases((FIX / "hts_releases.json").read_bytes()), date(2026, 11, 15)),
                "hts_releases": {"revisions": tariffs.parse_releases((FIX / "hts_releases.json").read_bytes())[:12]}}
        feats = {f["properties"]["id"]: f["properties"] for f in feed.tariff_features(snap, snap["generated_at"], "2026-11-17T12:00:00Z")}
        self.assertIn("headwind:tariffpace:presidential", feats)
        self.assertEqual(feats["headwind:tariffpace:presidential"]["tier"], "routine")
        self.assertIn("headwind:hts:2026HTSRev23", feats)
        self.assertEqual(feats["headwind:hts:2026HTSRev23"]["sources"][0]["id"], "usitc-hts")
        pres = {f["properties"]["id"]: f["properties"] for f in feed.list_features(snap)}
        item = pres["headwind:control:2026-22385"]
        self.assertTrue(item["title"].startswith("President, proclamation (2026-11-02): Adjusting Imports of Robotics"))
        self.assertIn("signed 2026-10-28", item["summary"])


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
            self.assertEqual([t["docket"] for t in snap["scotus_tracked"]], ["24-1287", "25-250"])
            self.assertIn("supremecourt-gov", snap["health"])
            self.assertEqual([(l["id"], l["total"]) for l in snap["sanctions_lists"]],
                             [("ofac-sdn", 36), ("un-consolidated", 14), ("eu-fsf", 9), ("uk-sanctions", 11),
                              ("france-gels", 20), ("canada-sema", 24)])
            self.assertTrue(list((tmp / "data" / "raw" / "eu-fsf").glob("*.xml.gz")))
            # 5 rules and 3 USTR notices (one left out); tariff actions of the last 60 days come on top, so how many
            # depends on the day the test runs.
            s232 = {d["id"] for d in controls.parse_section232((FIX / "fr_section232.json").read_bytes())}
            self.assertEqual(len([c for c in snap["controls"] if c["agency"] != "President" and c["id"] not in s232]), 8)
            self.assertEqual(snap["tariff_pace"]["baseline_windows"], 27)
            self.assertEqual(snap["hts_releases"]["total"], 186)
            self.assertIn("usitc-hts", snap["health"])
            self.assertIn("whitehouse-actions", snap["health"])
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


class TestNames(unittest.TestCase):
    """headwind-1.9: names on list changes (Tom, 15-16 Nov 2026: publish what the licences allow). Fixtures cut from
    OFAC's sdn.csv and add.csv of 12 Nov 2026 and trade.gov's file of 15 Nov 2026, as published (street addresses
    and remarks dropped from the trade.gov cut)."""

    def ofac(self):
        return sanctions.parse_sdn_csv(text("ofac_sdn_names.csv"), sanctions.parse_add_csv(text("ofac_add_names.csv")))

    def test_ofac_names_and_countries(self):
        idx = self.ofac()
        self.assertEqual(idx["36"], ["entity", ["CUBA"], {"name": "AEROCARIBBEAN AIRLINES", "countries": ["Cuba"]}])
        self.assertIn("United States", idx["7116"][2]["countries"])
        self.assertEqual(idx["2677"][:2], ["individual", ["SDGT"]])
        self.assertEqual(idx["2677"][2], {"name": "AL-ZOMOR, Abboud Abdul Latif Hassan", "countries": ["Egypt"]})
        self.assertEqual(idx["15042"][2]["name"], "DIAMOND II")               # a vessel keeps its own record
        self.assertNotIn("DOB", json.dumps(idx))                              # remarks are never carried
        # Without the address file the list is still read, with no countries.
        self.assertEqual(sanctions.parse_sdn_csv(text("ofac_sdn_names.csv"))["36"][2]["countries"], [])

    def change(self):
        new = self.ofac()
        prev = {k: [v[0], list(v[1]), dict(v[2])] for k, v in new.items() if k != "7116"}   # 7116 is added
        prev["36"][1] = []                                                    # 36 gains CUBA
        prev["15042"] = new["15042"]
        new = {k: v for k, v in new.items() if k != "2677"}                   # 2677 is removed
        return sanctions.delta("ofac-sdn", prev, new, "2026-11-16T18:00:00Z", "2026-11-16T12:00:00Z")

    def test_delta_names_what_changed(self):
        d = self.change()
        self.assertEqual([r["name"] for r in d["named_added"]], ["HOLY LAND FOUNDATION FOR RELIEF AND DEVELOPMENT"])
        self.assertEqual([(r["name"], r["gained"]) for r in d["named_changed"]], [("AEROCARIBBEAN AIRLINES", ["CUBA"])])
        self.assertEqual([(r["name"], r["type"]) for r in d["named_removed"]],
                         [("AL-ZOMOR, Abboud Abdul Latif Hassan", "individual")])
        self.assertEqual((d["unnamed_removed"], d["us_person_data"]), (0, "organizations"))   # US addresses of 7116

    def test_feed_names_people_removed_on_the_page_only(self):
        d = self.change()
        snap = {"generated_at": "2026-11-16T18:00:00Z", "lanes": {}, "sanctions": [d]}
        fs = [f for f in feed.list_features(snap) if f["properties"]["id"].startswith("headwind:sanctions:")]
        self.assertEqual(lint({"features": fs}), [])
        p = fs[0]["properties"]
        self.assertIn("Added: HOLY LAND FOUNDATION FOR RELIEF AND DEVELOPMENT (entity, SDGT)", p["summary"])
        self.assertIn("Changed: AEROCARIBBEAN AIRLINES (entity; programs gained CUBA)", p["summary"])
        # The feed goes into the history log for good: a person no longer listed is counted there, named on the page.
        self.assertNotIn("AL-ZOMOR", p["summary"])
        self.assertIn("1 individual removed, no longer on the list: named on the page for 30 days", p["summary"])
        self.assertIn("support@theintelligence.company", p["summary"])
        self.assertEqual((p["us_person_data"], p["measures"]["named"]), ("organizations", 3))

    def test_renames_and_the_name_form_guard(self):
        prev = {"1": ["entity", ["X"], {"name": "OLD NAME", "countries": []}]}
        new = {"1": ["entity", ["X"], {"name": "NEW NAME", "countries": []}]}
        d = sanctions.delta("uk-sanctions", prev, new, "2026-11-16T18:00:00Z", None)
        self.assertEqual((d["changed"], d["renamed"], d["named_changed"][0]["name_before"]), (1, 1, "OLD NAME"))
        self.assertIsNone(sanctions.delta("uk-sanctions", prev, new, "2026-11-16T18:00:00Z", None, compare_names=False))
        # A reading kept before names were carried: removals are counted, not named; nothing is compared by name.
        old = {"1": ["entity", ["X"]], "2": ["individual", ["X"]]}
        d = sanctions.delta("eu-fsf", old, {"1": new["1"]}, "2026-11-16T18:00:00Z", None)
        self.assertEqual((d["removed"], d["named_removed"], d["unnamed_removed"], d["changed"]), (1, [], 1, 0))

    def test_the_un_list_is_never_named(self):
        _, idx = sanctions.parse_un_xml((FIX / "un_consolidated.xml").read_bytes())
        self.assertTrue(all(len(v) == 2 for v in idx.values()))
        prev = dict(idx)
        gone = next(iter(idx))
        del idx[gone]
        d = sanctions.delta("un-consolidated", prev, idx, "2026-11-16T18:00:00Z", None)
        self.assertNotIn("named_added", d)
        self.assertEqual((d["named_changed"], d["us_person_data"]), ([], "none"))
        s = feed._names_text(d, True)
        self.assertIn("counts only (the UN's terms of use bar redistributing its content)", s)

    def test_person_label(self):
        from headwind import names
        self.assertTrue(all(names.is_us(c) for c in ("US", "United States", "ETATS-UNIS", "États-Unis", "U.S.A.")))
        self.assertFalse(names.is_us("Russia"))
        us_person = [{"type": "individual", "countries": ["United States"]}]
        us_org = [{"type": "entity", "countries": ["US"]}]
        unstated = [{"type": "not stated", "countries": ["US"]}]          # trade.gov's Entity List and DPL
        self.assertEqual(names.person_data(us_org, us_person), "individuals")
        self.assertEqual(names.person_data(us_org), "organizations")
        self.assertEqual(names.person_data(unstated), "individuals")
        self.assertEqual(names.person_data([{"type": "individual", "countries": ["Egypt"]}]), "none")

    def test_screening_names(self):
        lists = screening.parse(text("trade_gov_csl_names.json"))
        self.assertEqual([v[4] for v in lists["DPL"]["index"].values()], ["KAL TEK LABS"])
        el = lists["EL"]
        prev = {k: v[:4] for k, v in el["index"].items()}                    # a reading kept before names
        first = screening.delta("EL", el, prev, "2026-11-16T18:00:00Z", None)
        self.assertIsNone(first)                                             # no name comparison against it
        gone = next(iter(el["index"]))
        later = {"name": el["name"], "publisher": el["publisher"], "url": el["url"], "dates": el["dates"],
                 "index": {k: v for k, v in el["index"].items() if k != gone}}
        d = screening.delta("EL", later, el["index"], "2026-11-16T18:00:00Z", None)
        self.assertEqual([r["name"] for r in d["named_removed"]], [el["index"][gone][4]])
        dpl = lists["DPL"]
        d = screening.delta("DPL", dpl, {}, "2026-11-16T18:00:00Z", None)
        self.assertEqual((d["named_added"][0]["name"], d["named_added"][0]["listed"], d["us_person_data"]),
                         ("KAL TEK LABS", "1988-08-26", "individuals"))         # unstated type with a US address


if __name__ == "__main__":
    unittest.main()
