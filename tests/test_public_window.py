"""Public window for history/: the committed copy keeps dated files for PUBLIC_DAYS, from PUBLIC_WINDOW_FROM on, and a
file leaves main only after the private archive's history lane holds the same bytes. Files committed before the
window starts never leave. New dated release assets (state-YYYY-qN) stop; release `state` keeps the newest state.

The step test runs the workflow's own shell for the step against a local bare repository as `origin`, after the
workflow's own history-lane command has put history/ into a local DirStore. Nothing reaches GitHub."""
from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from headwind import archive  # noqa: E402
from test_archive_lanes import (STEPS, arg, put_calls, run_archive, step, tree)  # noqa: E402

WINDOW_STEP = "Public window for history/ (older files stay in the private archive)"
NOW = "2027-02-20T06:00:00Z"            # cutoff 2027-01-06 with the 45-day window


def at(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def touch(root: Path, rel: str, data: bytes = b'{"x":1}\n') -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(data, 9, mtime=0) if rel.endswith(".gz") else data)


class TestOutsideWindow(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.h = Path(self.td.name)
        for rel in ("state.json", "log/2026/11/20.jsonl.gz", "deltas/2026-11.jsonl.gz", "fetch-index/2026-11.jsonl",
                    "log/2026/12/01.jsonl.gz", "log/2026/12/31.jsonl.gz", "deltas/2026-12.jsonl.gz",
                    "fetch-index/2026-12.jsonl", "log/2027/01/10.jsonl.gz", "log/2027/02/20.jsonl",
                    "notes.txt", "log/2027/01/xx.jsonl"):
            touch(self.h, rel)

    def tearDown(self):
        self.td.cleanup()

    def test_files_before_the_window_starts_never_leave(self):
        for now in (NOW, "2030-01-01T00:00:00Z"):
            out = archive.outside_window(self.h, at(now))
            self.assertFalse([r for r in out if "2026/11" in r or "2026-11" in r], out)

    def test_undated_files_never_leave(self):
        out = archive.outside_window(self.h, at("2030-01-01T00:00:00Z"))
        for rel in ("state.json", "notes.txt", "log/2027/01/xx.jsonl"):
            self.assertNotIn(rel, out)

    def test_cutoff(self):
        self.assertEqual(archive.outside_window(self.h, at(NOW)),
                         ["deltas/2026-12.jsonl.gz", "fetch-index/2026-12.jsonl", "log/2026/12/01.jsonl.gz",
                          "log/2026/12/31.jsonl.gz"])
        self.assertEqual(archive.outside_window(self.h, at("2026-12-31T23:00:00Z")), [])

    def test_the_log_days_ended_geojson_reads_stay(self):
        # ended_collection reads the last ENDED_DAYS + 1 days of the log.
        from tic_doctrine import history as kit
        self.assertGreater(archive.PUBLIC_DAYS, kit.ENDED_DAYS + 1)

    def test_a_month_of_list_changes_stays_while_the_snapshot_offers_them_again(self):
        # sanctions.roll keeps 30 days of changes in the snapshot; append_deltas skips ids found in history/deltas.
        # A change detected on the month's last day is offered again for 30 days, so the month's file stays.
        from headwind import sanctions
        keep = getattr(sanctions, "KEEP_DAYS", 30)
        self.assertGreater(archive.PUBLIC_DAYS, keep)
        out = archive.outside_window(self.h, at("2027-01-30T23:59:00Z"))
        self.assertNotIn("deltas/2026-12.jsonl.gz", out)
        self.assertNotIn("fetch-index/2026-12.jsonl", out)

    def test_month_spans(self):
        self.assertEqual(archive.file_days("deltas/2026-12.jsonl.gz"), ("2026-12-01", "2026-12-31"))
        self.assertEqual(archive.file_days("fetch-index/2027-02.jsonl"), ("2027-02-01", "2027-02-28"))
        self.assertEqual(archive.file_days("log/2026/12/05.jsonl"), ("2026-12-05", "2026-12-05"))
        self.assertIsNone(archive.file_days("state.json"))

    def test_cli(self):
        r = subprocess.run([sys.executable, "-m", "headwind.archive", "outside-window", "--history", str(self.h),
                            "--now", NOW], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), archive.outside_window(self.h, at(NOW)))


class TestWorkflow(unittest.TestCase):
    def test_window_step_is_last_and_only_after_the_history_lane_reached_the_archive(self):
        names = list(STEPS)
        self.assertEqual(names[-1], WINDOW_STEP)
        text = STEPS[WINDOW_STEP]
        self.assertIn("if: ${{ !cancelled() && steps.archive.outputs.history_archived == 'true' }}", text)
        arch = step("Private archive (history")
        self.assertIn("id: archive", arch)
        flat = arch.replace("\\\n", " ")
        self.assertRegex(flat, r"if python tools/tic_archive\.py put --program headwind --lane history --src history;"
                               r" then\s+echo \"history_archived=true\" >> \"\$GITHUB_OUTPUT\"")
        self.assertEqual(flat.count("history_archived=true"), 1)

    def test_window_step_removes_only_history_and_only_archived_bytes(self):
        text = STEPS[WINDOW_STEP]
        self.assertIn("python -m headwind.archive outside-window --history history", text)
        self.assertIn('git rm -q --cached -- "$f"', text)
        self.assertIn('"$(git hash-object "$f")"', text)
        self.assertNotIn("git add", text)
        self.assertNotIn("rm -r", text)
        self.assertNotIn("--force", text)
        self.assertIn("git diff --cached --quiet -- history", text)

    def test_no_new_dated_release_assets(self):
        text = step("Second copy of the state in the release")
        self.assertIn("gh release upload state headwind-state.tar.gz --clobber", text)
        self.assertEqual(text.count("gh release upload"), 1)
        for gone in ("state-$(date", "headwind-vessels-", "gh release create \"$q\""):
            self.assertNotIn(gone, text)
        self.assertNotIn("gh release delete", "".join(STEPS.values()))
        # The restore still reads release `state` first.
        self.assertIn("gh release download state --pattern headwind-state.tar.gz",
                      step("No cache entry, so the state from the release"))


def _git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash and git")
class TestWindowStepRuns(unittest.TestCase):
    """The step's own shell, against a bare repository as origin."""

    def test_removed_files_are_in_the_archive_and_the_rest_stay(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            origin, work, other, store = td / "origin.git", td / "work", td / "other", td / "store"
            _git(td, "init", "-q", "--bare", "-b", "main", str(origin))
            _git(td, "clone", "-q", str(origin), str(work))
            for c in (work,):
                _git(c, "config", "user.name", "t")
                _git(c, "config", "user.email", "t@example.invalid")
                _git(c, "config", "core.autocrlf", "false")
            h = work / "history"
            files = ("state.json", "log/2026/11/20.jsonl.gz", "deltas/2026-11.jsonl.gz", "log/2026/12/01.jsonl.gz",
                     "log/2026/12/02.jsonl.gz", "deltas/2026-12.jsonl.gz", "fetch-index/2026-12.jsonl",
                     "log/2027/01/30.jsonl.gz")
            for i, rel in enumerate(files):
                touch(h, rel, b'{"n":%d}\n' % i)
            _git(work, "add", "history")
            _git(work, "commit", "-q", "-m", "history")
            _git(work, "push", "-q", "origin", "HEAD:main")
            # The run archives history/ with the workflow's own command.
            (put,) = [c for c in put_calls() if arg(c, "--lane") == ["history"]]
            self.assertEqual(run_archive(put, work, store), 0)
            archived = tree(h)
            # Another run changes one old file on main after this run's snapshot: it must stay.
            _git(td, "clone", "-q", str(origin), str(other))
            _git(other, "config", "user.name", "t")
            _git(other, "config", "user.email", "t@example.invalid")
            touch(other / "history", "log/2026/12/02.jsonl.gz", b'{"n":"changed"}\n')
            _git(other, "commit", "-q", "-am", "later run")
            _git(other, "push", "-q", "origin", "HEAD:main")

            script = STEPS[WINDOW_STEP].split("run: |\n", 1)[1]
            script = "\n".join(line[10:] if line.startswith(" " * 10) else line for line in script.splitlines())
            script = script.replace("outside-window --history history",
                                    f"outside-window --history history --now {NOW}")
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            r = subprocess.run(["bash", "-e", "-c", script], cwd=work, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            on_main = set(_git(origin, "ls-tree", "-r", "--name-only", "main").split())
            self.assertEqual(on_main, {"history/state.json", "history/log/2026/11/20.jsonl.gz",
                                       "history/deltas/2026-11.jsonl.gz", "history/log/2026/12/02.jsonl.gz",
                                       "history/log/2027/01/30.jsonl.gz"})
            self.assertIn("differs from the archived copy", r.stdout + r.stderr)
            removed = {f"history/{rel}" for rel in files} - on_main
            self.assertEqual(removed, {"history/log/2026/12/01.jsonl.gz", "history/deltas/2026-12.jsonl.gz",
                                       "history/fetch-index/2026-12.jsonl"})
            # Every removed file restores from the archive with the bytes main had.
            dest = td / "restored"
            self.assertEqual(run_archive(["restore", "--program", "headwind", "--lane", "history",
                                          "--dest", str(dest)], work, store), 0)
            got = tree(dest)
            for path in removed:
                rel = path[len("history/"):]
                blob = subprocess.run(["git", "show", f"main~1:{path}"], cwd=origin, capture_output=True).stdout
                self.assertEqual(got[rel], hashlib.sha256(blob).hexdigest(), path)
                self.assertEqual(got[rel], archived[rel], path)
            # Only history/ changed, in one commit on top of the later run's.
            log = _git(origin, "log", "--format=%s", "main").splitlines()
            self.assertTrue(log[0].startswith("history: public window "), log)
            self.assertEqual(log[1:], ["later run", "history"])


if __name__ == "__main__":
    unittest.main()
