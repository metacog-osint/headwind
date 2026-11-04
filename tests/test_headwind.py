"""Offline tests for Headwind (OFAC SDN deltas, Federal Register rules, FAO/IGC commodities, Verdict events, Contract v2 Feed)."""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))

from headwind import feed  # noqa: E402
from tic_doctrine import contract, registers  # noqa: E402

_spec = importlib.util.spec_from_file_location("headwind_cli", ROOT / "tools" / "headwind.py")
headwind_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(headwind_cli)


class TestHeadwind(unittest.TestCase):
    def test_doctrine_registers_pass(self):
        self.assertEqual(registers.check(ROOT / "doctrine"), [])

    def test_sanctions_controls_and_verdict_events(self):
        snap = headwind_cli.build_snapshot()
        self.assertEqual(len(snap["sanctions"]), 1)
        self.assertEqual(snap["sanctions"][0]["vessels_added"], 3)
        self.assertEqual(len(snap["controls"]), 2)
        self.assertEqual(snap["events"]["source"], "headwind")
        self.assertEqual(len(snap["events"]["events"]), 4)

    def test_feed_contract_v2_passes_linter(self):
        snap = headwind_cli.build_snapshot()
        fc = feed.build_feed(snap)
        regs = registers.ids(ROOT / "doctrine")
        self.assertEqual(len(fc["features"]), 5)
        for feat in fc["features"]:
            errs = [m for _, sev, m in contract.check(feat, regs) if sev == "error"]
            self.assertEqual(errs, [], f"Linter errors on {feat['properties'].get('id')}: {errs}")

    def test_site_build_and_check_all(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "doctrine", tmp / "doctrine")
            shutil.copytree(ROOT / "site_src", tmp / "site_src")
            files = headwind_cli.build_site(tmp)
            self.assertIn("data/feed.geojson", files)
            self.assertIn("data/events.json", files)
            self.assertIn("index.html", files)
            self.assertEqual(headwind_cli.check_all(tmp), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
