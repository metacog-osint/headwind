"""Retention archives: list changes and fetch-index rows are kept for good, append-only, and the live view is untouched."""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from headwind import archive, sanctions  # noqa: E402


def delta(i, detected="2026-11-18T10:00:00Z", removed=None):
    return {"id": f"ofac-sdn:{i}", "list": "ofac-sdn", "detected_at": detected, "added": 1, "removed": 3,
            "named_added": [{"list_id": "1", "name": "ADDED PERSON", "type": "individual", "programs": ["X"],
                             "countries": []}],
            "named_removed": removed if removed is not None else [
                {"list_id": "10", "name": "GONE PERSON", "type": "individual", "programs": ["X"], "countries": ["US"]},
                {"list_id": "11", "name": "GONE CORP", "type": "entity", "programs": ["X"], "countries": []},
                {"list_id": "12", "name": "GONE TYPELESS", "type": "", "programs": [], "countries": []}],
            "vessels_added": [{"list_id": "5", "name": "SHIP", "imo": "9"}]}


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class TestDeltaArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = Path(self.tmp.name) / "history"

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_flag_is_off(self):
        self.assertIs(archive.ARCHIVE_REMOVED_INDIVIDUALS, False)

    def test_removed_individuals_are_counted_with_list_ids_only_when_flag_off(self):
        archive.append_deltas({"sanctions": [delta("a")]}, self.h, NOW)
        (rec,) = read(self.h / "deltas" / "2026-11.jsonl.gz")
        self.assertEqual(rec["kind"], "sanctions")
        self.assertEqual([r["name"] for r in rec["named_removed"]], ["GONE CORP"])
        self.assertEqual(rec["removed_individuals"], 2)          # the typeless entry counts as an individual
        self.assertEqual(rec["removed_individuals_list_ids"], ["10", "12"])
        self.assertNotIn("GONE PERSON", json.dumps(rec))
        self.assertEqual(rec["named_added"][0]["name"], "ADDED PERSON")     # added in full
        self.assertEqual(rec["vessels_added"][0]["imo"], "9")

    def test_flag_on_keeps_full_records(self):
        archive.append_deltas({"sanctions": [delta("a")]}, self.h, NOW, archive_removed_individuals=True)
        (rec,) = read(self.h / "deltas" / "2026-11.jsonl.gz")
        self.assertEqual(len(rec["named_removed"]), 3)
        self.assertNotIn("removed_individuals", rec)

    def test_dropped_after_30_days_still_archived(self):
        old = delta("old", "2026-10-01T00:00:00Z")
        snap_before = {"sanctions": [old]}
        self.assertEqual(archive.append_deltas(snap_before, self.h, datetime(2026, 10, 2, tzinfo=timezone.utc)), 1)
        rolled = sanctions.roll([old], [], "2026-11-18T12:00:00Z")      # the live view drops it
        self.assertEqual(rolled, [])
        ids = archive.archived_ids(self.h / "deltas")
        self.assertIn("ofac-sdn:old", ids)

    def test_append_only_and_idempotent(self):
        snap = {"sanctions": [delta("a")], "screening": [{**delta("s"), "list": "x", "id": "x:s"}]}
        self.assertEqual(archive.append_deltas(snap, self.h, NOW), 2)
        f = self.h / "deltas" / "2026-11.jsonl.gz"
        first = f.read_bytes()
        self.assertEqual(archive.append_deltas(snap, self.h, NOW), 0)
        self.assertEqual(f.read_bytes(), first)
        snap["sanctions"].append(delta("b"))
        self.assertEqual(archive.append_deltas(snap, self.h, NOW), 1)
        self.assertTrue(f.read_bytes().startswith(first))        # earlier bytes untouched
        self.assertEqual([r["id"] for r in read(f)], ["ofac-sdn:a", "x:s", "ofac-sdn:b"])

    def test_closed_month_file_is_never_opened_again(self):
        archive.append_deltas({"sanctions": [delta("a")]}, self.h, NOW)
        nov = self.h / "deltas" / "2026-11.jsonl.gz"
        before = nov.read_bytes()
        dec = datetime(2026, 12, 2, tzinfo=timezone.utc)
        archive.append_deltas({"sanctions": [delta("a"), delta("late")]}, self.h, dec)
        self.assertEqual(nov.read_bytes(), before)
        self.assertEqual([r["id"] for r in read(self.h / "deltas" / "2026-12.jsonl.gz")], ["ofac-sdn:late"])

    def test_snapshot_not_modified(self):
        snap = {"sanctions": [delta("a")]}
        before = json.dumps(snap, sort_keys=True)
        archive.append_deltas(snap, self.h, NOW)
        self.assertEqual(json.dumps(snap, sort_keys=True), before)       # list-changes.json / the live view unchanged


class TestFetchIndexAndVessels(unittest.TestCase):
    def test_fetch_index_rows_append_once_without_bodies(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            idx = t / "index.jsonl"
            row = {"source_id": "ofac-sdn", "url": "https://u/x.csv", "sha256": "ab" * 32, "bytes": 5,
                   "fetched_at": "2026-11-18T10:00:00Z", "secret_extra": "no"}
            idx.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(archive.append_fetch_index(idx, t / "history", NOW), 1)
            self.assertEqual(archive.append_fetch_index(idx, t / "history", NOW), 0)
            idx.write_text(idx.read_text() + json.dumps({**row, "fetched_at": "2026-11-18T16:00:00Z"}) + "\n")
            self.assertEqual(archive.append_fetch_index(idx, t / "history", NOW), 1)
            lines = (t / "history" / "fetch-index" / "2026-11.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertNotIn("secret_extra", lines[0])
            self.assertEqual(archive.append_fetch_index(t / "none.jsonl", t / "history", NOW), 0)

    def test_vessels_digest_ignores_run_times(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "v.json"
            doc = {"generated_at": "a", "summary": {"checked_at": "a", "n": 1}, "vessels": [{"imo": "1"}]}
            f.write_text(json.dumps(doc))
            d1 = archive.vessels_digest(f)
            doc.update(generated_at="b", summary={"checked_at": "b", "n": 1})
            f.write_text(json.dumps(doc))
            self.assertEqual(archive.vessels_digest(f), d1)
            doc["vessels"].append({"imo": "2"})
            f.write_text(json.dumps(doc))
            self.assertNotEqual(archive.vessels_digest(f), d1)


if __name__ == "__main__":
    unittest.main()
