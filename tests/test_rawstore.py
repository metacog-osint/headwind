"""Raw copies: a reply whose data did not change is stored once, and every reply can still be rebuilt byte for byte.

Fixture raw_volatile.json holds, per source, two real replies cut small that differ only in the values the source
changes on every request (import stamps, counters, nonces, a server clock, row order)."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/<program>.py must not shadow the package

from headwind import archive, fetch, rawstore  # noqa: E402
import tic_archive as ta  # noqa: E402

REPLIES = json.loads((ROOT / "tests" / "fixtures" / "raw_volatile.json").read_text(encoding="utf-8"))
GZ = {"trade-gov-csl", "supremecourt-uk"}     # sources the collector stores gzipped
NOW = datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)


def run(raw: Path, replies: dict[str, bytes]) -> list[dict]:
    """One collection run into a fresh raw folder, as on a runner: each source fetched once."""
    recs = []
    for src, body in replies.items():
        ext = REPLIES[src]["ext"] if src in REPLIES else "bin"
        _, rec = fetch.fetch(src, f"https://example.test/{src}", raw, ext, getter=lambda u, t, b=body: b,
                             gz=src in GZ)
        recs.append(rec)
    return recs


def stored_files(raw: Path) -> dict[str, bytes]:
    return {p.relative_to(raw).as_posix(): p.read_bytes() for p in sorted(raw.rglob("*"))
            if p.is_file() and p.name != "index.jsonl"}


class Split(unittest.TestCase):
    def test_each_source_stores_one_copy_for_both_replies(self):
        for src, case in REPLIES.items():
            with self.subTest(src):
                a, b = case["a"].encode("utf-8"), case["b"].encode("utf-8")
                self.assertNotEqual(a, b)
                sa, ra = rawstore.split(src, case["ext"], a)
                sb, rb = rawstore.split(src, case["ext"], b)
                self.assertIsNotNone(ra)
                self.assertEqual(sa, sb)                       # one stored copy for both replies
                self.assertEqual(rawstore.rebuild(sa, ra), a)  # and each reply back exactly
                self.assertEqual(rawstore.rebuild(sb, rb), b)

    def test_values_taken_out_are_in_the_recipe(self):
        a = REPLIES["trade-gov-csl"]["a"].encode("utf-8")
        stored, recipe = rawstore.split("trade-gov-csl", "json", a)
        values = [v for _, v in recipe["at"]]
        self.assertTrue(values and all(v.startswith("2026-11-27T") for v in values))
        self.assertNotIn(b"2026-11-27T04:15", stored)
        self.assertIn(b'"source_last_updated": "2026-11-23T17:32:53+00:00"', stored)   # data stays in the copy

    def test_dates_that_are_data_stay_in_the_stored_copy(self):
        feed = REPLIES["supremecourt-gov"]["a"].encode("utf-8")
        stored, recipe = rawstore.split("supremecourt-gov", "xml", feed)
        self.assertEqual(len(recipe["at"]), 1)               # the channel's date only
        self.assertEqual(stored.count(b"<pubDate>"), feed.count(b"<pubDate>"))
        self.assertIn(b"<item>", stored)
        item = feed[feed.index(b"<item>"):]
        self.assertIn(item, stored)                          # the opinion's own date is untouched
        sitemap = REPLIES["supremecourt-uk"]["a"].encode("utf-8")
        stored, recipe = rawstore.split("supremecourt-uk", "xml", sitemap)
        self.assertIn(b"<priority>", stored)
        self.assertRegex(stored.decode("utf-8"), r"<lastmod>20\d\d-[^<]+</lastmod>\s*<changefreq>hourly</changefreq>"
                                                 r"\s*<priority>")

    def test_census_rows_in_any_order_store_one_copy(self):
        case = REPLIES["census-trade"]
        a, b = case["a"].encode("utf-8"), case["b"].encode("utf-8")
        self.assertEqual(sorted(map(json.dumps, json.loads(a))), sorted(map(json.dumps, json.loads(b))))  # same rows
        sa, ra = rawstore.split("census-trade", "json", a)
        self.assertEqual(ra["kind"], "rows")
        self.assertEqual(json.loads(sa)[0], json.loads(a)[0])          # header first, still a valid table
        self.assertEqual(sorted(map(json.dumps, json.loads(sa))), sorted(map(json.dumps, json.loads(a))))
        rev = a.split(b"\n")
        header, rows = rev[0], [r.rstrip(b",") for r in rev[1:]]
        rows[-1] = rows[-1][:-1]
        shuffled = header + b"\n" + b",\n".join(reversed(rows)) + b"]"
        ss, rs = rawstore.split("census-trade", "json", shuffled)
        self.assertEqual(ss, sa)
        self.assertEqual(rawstore.rebuild(ss, rs), shuffled)

    def test_other_sources_and_failed_round_trips_are_stored_as_fetched(self):
        body = b'{"search_performed_at": "2026-11-27T04:15:00Z"}'
        self.assertEqual(rawstore.split("ofac-sdn", "csv", body), (body, None))     # no rule for the source
        self.assertEqual(rawstore.split("census-trade", "json", b'{"a": 1}'), (b'{"a": 1}', None))  # not a table
        self.assertEqual(rawstore.split("trade-gov-csl", "json", b"[]"), (b"[]", None))             # nothing to take
        many = b"".join(b'"last_imported": "x%d", ' % i for i in range(rawstore.MAX_SPANS + 1))
        self.assertEqual(rawstore.split("trade-gov-csl", "json", many), (many, None))

    def test_page_noise_applies_to_every_html_page(self):
        fomc = REPLIES["fed-fomc-calendar"]["a"].encode("utf-8")
        stored, recipe = rawstore.split("some-new-page", "html", fomc)
        self.assertIsNotNone(recipe)
        self.assertEqual(rawstore.rebuild(stored, recipe), fomc)


class Collector(unittest.TestCase):
    """fetch.fetch as the collector calls it: what lands in data/raw across two runs."""

    def replies(self, which):
        return {src: case[which].encode("utf-8") for src, case in REPLIES.items()}

    def test_second_run_with_only_changing_values_writes_the_same_files(self):
        with tempfile.TemporaryDirectory() as td:
            r1, r2 = Path(td) / "run1", Path(td) / "run2"
            run(r1, self.replies("a"))
            recs = run(r2, self.replies("b"))
            self.assertEqual(stored_files(r1), stored_files(r2))   # same names, same bytes
            for rec in recs:
                self.assertEqual(hashlib.sha256(rawstore.read_fetched(r2, rec)).hexdigest(), rec["sha256"])
                self.assertEqual(rawstore.read_fetched(r2, rec), REPLIES[rec["source_id"]]["b"].encode("utf-8"))

    def test_gzip_copy_has_no_time_in_its_header(self):
        body = b"<export>list</export>" * 50
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td)
            for i, d in enumerate(("one", "two")):
                fetch.fetch("eu-fsf", "https://example.test/eu", raw / d, "xml", getter=lambda u, t: body, gz=True)
            a, b = (next((raw / d / "eu-fsf").glob("*.xml.gz")).read_bytes() for d in ("one", "two"))
            self.assertEqual(a[4:8], b"\0\0\0\0")      # gzip MTIME field
            self.assertEqual(a, b)
            self.assertEqual(gzip.decompress(a), body)

    def test_reply_without_changing_values_keeps_the_old_layout(self):
        body = b"id,name\n1,A\n"
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td)
            _, rec = fetch.fetch("ofac-sdn", "https://example.test/sdn", raw, "csv", getter=lambda u, t: body)
            self.assertNotIn("stored", rec)
            self.assertNotIn("rebuild", rec)
            self.assertTrue((raw / "ofac-sdn" / f"{rec['sha256'][:12]}.csv").exists())
            self.assertEqual(rawstore.read_fetched(raw, rec), body)

    def test_public_fetch_index_keeps_its_fields(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw"
            run(raw, self.replies("a"))
            archive.append_fetch_index(raw / "index.jsonl", Path(td) / "history", now=NOW)
            rows = (Path(td) / "history" / "fetch-index" / "2026-11.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(rows)
            for line in rows:
                self.assertEqual(set(json.loads(line)), {"source_id", "url", "sha256", "bytes", "fetched_at"})


class Archive(unittest.TestCase):
    """The private archive's raw lane over two runs whose replies differ only in the changing values."""

    def test_unchanged_data_is_uploaded_once_and_every_reply_restores(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            store = ta.DirStore(td / "store")
            arch = ta.Archive(store, "headwind", "raw")
            body = {"eu-fsf": b"<export>" + b"<entity/>" * 400 + b"</export>"}
            docs, recs = [], []
            for i, which in enumerate(("a", "b")):
                raw = td / f"run{i}"
                replies = self.replies(which)
                recs.append(run(raw, replies))
                for src, b in body.items():
                    _, rec = fetch.fetch(src, "https://example.test/eu", raw, "xml", getter=lambda u, t, b=b: b, gz=True)
                    recs[-1].append(rec)
                docs.append(arch.put(raw, now=NOW + timedelta(hours=2 * i))["doc"])
            second = docs[1]
            self.assertEqual(second["new_files"], 1)      # only this run's index.jsonl, which holds the values
            self.assertEqual({f["path"] for f in second["files"] if f["asset"].startswith(second["stamp"])},
                             {"index.jsonl"})
            for doc, run_recs in zip(docs, recs):
                dest = td / f"restored-{doc['stamp']}"
                arch.restore(dest, snapshot=f"{doc['stamp']}-{doc['snapshot_sha256'][:12]}.files.json")
                lines = [json.loads(x) for x in (dest / "index.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(lines), len(run_recs))
                for rec in lines:
                    data = rawstore.read_fetched(dest, rec)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), rec["sha256"])

    def replies(self, which):
        return {src: case[which].encode("utf-8") for src, case in REPLIES.items()}


if __name__ == "__main__":
    unittest.main()
