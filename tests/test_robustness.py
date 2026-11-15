"""Source health, drift checks, list edits, the fetch retry and the kit copy (14 Nov 2026). Offline."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
sys.path.insert(0, str(ROOT / "tests"))

from headwind import feed, fetch, health, sanctions, screening  # noqa: E402

spec = importlib.util.spec_from_file_location("headwind_cli", ROOT / "tools" / "headwind.py")
headwind_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(headwind_cli)
from test_headwind import fake_getter  # noqa: E402


class TestHealth(unittest.TestCase):
    def test_states_follow_each_sources_own_rhythm(self):
        today = date(2026, 11, 16)                       # a Monday
        self.assertEqual(health._judge("ecb-eurofxref", date(2026, 11, 13), today), "fresh")   # Friday's rates
        self.assertEqual(health._judge("ecb-eurofxref", date(2026, 11, 10), today), "late")
        self.assertEqual(health._judge("ecb-eurofxref", date(2026, 11, 1), today), "stale")
        self.assertEqual(health._judge("fao-ffpi", health._month_end("2026-10"), today), "fresh")
        self.assertEqual(health._judge("fao-ffpi", health._month_end("2026-08"), today), "stale")
        self.assertEqual(health._judge("worldbank-wdi", None, today), "up")
        self.assertEqual(health._month_end("2026-12"), date(2026, 12, 31))

    def test_a_quiet_publisher_is_noted_not_failed(self):
        today = date(2026, 11, 30)
        eu = {"source_generated": "2026-10-23T17:05:43.888+02:00"}
        self.assertEqual(health.quiet_notes("eu-fsf", eu, today),
                         ["the publisher's file is dated 2026-10-23, 38 days ago"])
        self.assertEqual(health.quiet_notes("uk-sanctions-list", {"source_generated": "2026-11-12"}, today), [])
        ofac = {"baseline_set_at": "2026-11-01T00:00:00Z", "last_change_at": None}
        self.assertIn("no change seen since the baseline of 2026-11-01", health.quiet_notes("ofac-sdn", ofac, today)[0])
        ofac["last_change_at"] = "2026-11-25T00:00:00Z"
        self.assertEqual(health.quiet_notes("ofac-sdn", ofac, today), [])


class TestDrift(unittest.TestCase):
    def test_a_short_reading_fails_a_parsed_source_and_warns_on_a_moving_one(self):
        hist = {"fx": [29, 29, 29], "controls": [25, 24, 26]}
        fails, warns = health.drift("fx", {"fx": 10}, hist)
        self.assertEqual(len(fails), 1)
        self.assertIn("10 currencies against a usual 29", fails[0])
        self.assertEqual(health.drift("fx", {"fx": 28}, hist), ([], []))
        fails, warns = health.drift("controls", {"controls": 5}, hist)
        self.assertEqual(fails, [])                      # a window of rules moves on its own: a warning only
        self.assertEqual(warns[0][0], "us-federal-register")
        self.assertEqual(health.drift("fx", {"fx": 1}, {"fx": [29, 29]}), ([], []))   # too little history yet

    def test_history_keeps_the_last_ten(self):
        h = {}
        for n in range(15):
            h = health.remember(h, {"fx": n})
        self.assertEqual(h["fx"], list(range(5, 15)))

    def test_collect_keeps_the_last_good_copy_when_a_page_parses_short(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src")
            (tmp / "config").mkdir()
            shutil.copy(ROOT / "config" / "wfp_countries.json", tmp / "config" / "wfp_countries.json")
            first = headwind_cli.collect(tmp, getter=fake_getter)
            # Pretend the ECB file usually gave four times as many currencies.
            snap_path = tmp / "data" / "snapshot.json"
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            snap["drift_history"]["fx"] = [len(first["fx"]) * 4] * 3
            snap_path.write_text(json.dumps(snap), encoding="utf-8")
            again = headwind_cli.collect(tmp, getter=fake_getter)
            self.assertEqual(again["lanes"]["fx"]["status"], "failed")
            self.assertIn("usual", again["lanes"]["fx"]["error"])
            self.assertEqual(again["fx"], first["fx"])   # the last good copy, not the short reading
            self.assertEqual(again["health"]["ecb-eurofxref"]["state"], "failing")
            self.assertEqual(again["health"]["ecb-eurofxref"]["failures"], 1)
            self.assertEqual(again["health"]["ecb-eurofxref"]["last_ok"], first["generated_at"])
            self.assertEqual(again["drift_history"]["fx"], [len(first["fx"]) * 4] * 3)   # a failed reading is not kept
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHealthInFeed(unittest.TestCase):
    def test_every_item_source_has_a_health_entry(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src")
            (tmp / "config").mkdir()
            shutil.copy(ROOT / "config" / "wfp_countries.json", tmp / "config" / "wfp_countries.json")
            snap = headwind_cli.collect(tmp, getter=fake_getter)
            h = snap["health"]
            self.assertEqual(set(h), set(health.LANE_OF))
            for key, e in h.items():
                self.assertIn(e["state"], ("fresh", "late", "stale", "up"), key)
                self.assertEqual(e["last_ok"], e["checked_at"])     # read on this run: the history log counts it
                self.assertEqual(e["failures"], 0)
            headwind_cli.build_site(tmp)
            doc = json.loads((tmp / "site" / "data" / "feed.geojson").read_text(encoding="utf-8"))
            self.assertEqual(doc["health"], h)
            sources = {f["properties"]["sources"][0]["id"] for f in doc["features"]}
            self.assertTrue(sources <= set(h), sources - set(h))
            page = json.loads((tmp / "site" / "data" / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(page["health"], h)
            self.assertEqual(headwind_cli.check_all(tmp), [])

            def eu_down(url, timeout=60):
                if "webgate.ec.europa.eu" in url:
                    raise OSError("EU server down")
                return fake_getter(url, timeout)
            partial = headwind_cli.collect(tmp, getter=eu_down)
            self.assertEqual(partial["health"]["eu-fsf"]["state"], "failing")
            self.assertEqual(partial["health"]["ofac-sdn"]["failures"], 0)
            self.assertIn("EU server down", partial["health"]["eu-fsf"]["error"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestListEdits(unittest.TestCase):
    def test_a_sanctions_entry_that_stays_and_changes_is_reported(self):
        prev = {"1": ["entity", ["IRAN"]], "2": ["vessel", ["IRAN"], {"name": "OLD NAME", "imo": "9000001",
                                                                       "mmsi": None, "flag": "Panama",
                                                                       "vessel_type": "Crude Oil Tanker"}],
                "3": ["individual", ["SDGT"]]}
        new = {"1": ["entity", ["IRAN", "RUSSIA-EO14024"]], "2": ["vessel", ["IRAN"], {"name": "NEW NAME",
                                                                                         "imo": "9000001", "mmsi": None,
                                                                                         "flag": "Cameroon",
                                                                                         "vessel_type": "Crude Oil Tanker"}],
               "3": ["individual", ["SDGT"]]}
        d = sanctions.delta("ofac-sdn", prev, new, "2026-11-15T00:00:00Z", "2026-11-14T00:00:00Z")
        self.assertEqual((d["added"], d["removed"], d["changed"]), (0, 0, 1))
        self.assertEqual(d["programs_gained"], {"RUSSIA-EO14024": 1})
        self.assertEqual(d["vessels_changed"][0]["changed"], {"name": ["OLD NAME", "NEW NAME"],
                                                              "flag": ["Panama", "Cameroon"]})
        self.assertIn("RU", d["countries"])
        self.assertIsNone(sanctions.delta("ofac-sdn", new, new, "2026-11-15T00:00:00Z", None))
        f = feed.list_features({"generated_at": "2026-11-15T00:00:00Z", "sanctions": [d], "lanes": {}})[0]
        p = f["properties"]
        self.assertIn("1 changed", p["title"])
        self.assertIn("programs gained, RUSSIA-EO14024 1", p["summary"])
        self.assertIn("NEW NAME (IMO 9000001): name OLD NAME to NEW NAME, flag Panama to Cameroon", p["summary"])
        self.assertEqual((p["measures"]["changed"], p["measures"]["vessels_changed"]), (1, 1))

    def test_a_screening_entry_under_a_new_id_is_one_entry(self):
        key = screening.name_key("Acme  Trading, Ltd.")
        self.assertEqual(key, screening.name_key("ACME TRADING LTD"))
        prev = {"old": ["entity", ["EAR"], ["CN"], key], "gone": ["entity", [], ["RU"], screening.name_key("Other")]}
        lst = {"name": "Entity List", "publisher": "US BIS", "url": "u",
               "index": {"new": ["entity", ["EAR"], ["HK"], key], "fresh": ["entity", [], ["IR"], screening.name_key("X")]}}
        d = screening.delta("EL", lst, prev, "2026-11-15T00:00:00Z", None)
        self.assertEqual((d["added"], d["removed"], d["rekeyed"], d["changed"]), (1, 1, 1, 1))   # moved CN to HK
        self.assertEqual(d["added_by_country"], {"IR": 1})
        f = feed.list_features({"generated_at": "2026-11-15T00:00:00Z", "screening": [d], "lanes": {}})[0]
        self.assertIn("came back under a new id", f["properties"]["summary"])
        # An index written before name keys were kept still compares: no pairing, no false edits.
        old_format = {"a": ["entity", ["EAR"], ["CN"]]}
        same = {"name": "Entity List", "publisher": "US BIS", "url": "u", "index": {"a": ["entity", ["EAR"], ["CN"], key]}}
        self.assertIsNone(screening.delta("EL", same, old_format, "2026-11-15T00:00:00Z", None))


class TestRetry(unittest.TestCase):
    def test_a_timeout_is_tried_once_more_and_a_refusal_is_not(self):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"ok"
        calls = []

        def flaky(req, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("The read operation timed out")
            return Resp()
        with mock.patch("urllib.request.urlopen", flaky):
            self.assertEqual(fetch.get("https://example.test/x", wait=0), b"ok")
        self.assertEqual(len(calls), 2)

        calls.clear()

        def refused(req, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", refused):
            with self.assertRaises(urllib.error.HTTPError):
                fetch.get("https://example.test/x", wait=0)
        self.assertEqual(len(calls), 1)


class TestKitCopy(unittest.TestCase):
    def test_nothing_inside_doctrine_kit_was_edited(self):
        kit = ROOT / "doctrine" / "kit"
        # CRLF read as LF, as the kit's sync.py hashes, so a Windows checkout matches.
        recorded = json.loads((kit / "KIT.json").read_text(encoding="utf-8"))["files"]
        edited = [f for f, sha in recorded.items()
                  if hashlib.sha256((kit / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest() != sha]
        self.assertEqual(edited, [], "edit the kit repo (tic-doctrine) and sync, not doctrine/kit/")

    @unittest.skipUnless((ROOT.parent / "tic-doctrine" / "tools" / "sync.py").exists(),
                         "the kit repo is not beside this checkout (a runner): the edit check above still runs")
    def test_the_kit_copy_is_current(self):
        r = subprocess.run([sys.executable, str(ROOT.parent / "tic-doctrine" / "tools" / "sync.py"), str(ROOT),
                            "--check"], capture_output=True, text=True)
        self.assertIn("kit copy OK", r.stdout, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
