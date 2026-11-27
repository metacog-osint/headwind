"""SHA-256 manifests of the release files (headwind/manifest.py) and the workflow step that publishes them."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from headwind import ftm, manifest  # noqa: E402


def _asset(name, data: bytes, digest=True):
    return {"name": name, "size": len(data), "updated_at": "2026-11-27T06:00:00Z",
            "digest": ("sha256:" + hashlib.sha256(data).hexdigest()) if digest else None}


class Manifest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.files = {"headwind-state.tar.gz": b"state bytes", "headwind-entities.ftm.gz": b"entities\n",
                      "headwind-state-2026-11-20.tar.gz": b"older"}
        self.assets = [_asset(n, b) for n, b in self.files.items()]

    def test_lists_every_file_but_its_own_two(self):
        assets = self.assets + [_asset(manifest.SUMS, b"x"), _asset(manifest.JSON_NAME, b"y")]
        m = manifest.build("metacog-osint/headwind", "state", assets)
        self.assertEqual([f["name"] for f in m["files"]], sorted(self.files))
        for f in m["files"]:
            self.assertEqual(f["sha256"], hashlib.sha256(self.files[f["name"]]).hexdigest())
            self.assertEqual(f["size"], len(self.files[f["name"]]))
        self.assertEqual(m["format"], "headwind-manifest/1")

    def test_local_copy_is_hashed_and_must_match_the_upload(self):
        (self.tmp / "headwind-state.tar.gz").write_bytes(b"state bytes")
        m = manifest.build("r", "state", self.assets, self.tmp)
        self.assertEqual(len(m["files"]), 3)
        (self.tmp / "headwind-state.tar.gz").write_bytes(b"other bytes")
        with self.assertRaises(manifest.Mismatch):
            manifest.build("r", "state", self.assets, self.tmp)

    def test_no_digest_needs_a_local_copy(self):
        assets = [_asset("a.bin", b"abc", digest=False)]
        with self.assertRaises(manifest.Mismatch):
            manifest.build("r", "t", assets)
        (self.tmp / "a.bin").write_bytes(b"abc")
        m = manifest.build("r", "t", assets, self.tmp)
        self.assertEqual(m["files"][0]["sha256"], hashlib.sha256(b"abc").hexdigest())

    def test_sums_file_is_what_sha256sum_reads(self):
        m = manifest.build("r", "state", self.assets)
        text = manifest.sums_text(m)
        for line in text.splitlines():
            self.assertRegex(line, r"^[0-9a-f]{64}  \S+$")
        for name, data in self.files.items():
            (self.tmp / name).write_bytes(data)
        (self.tmp / manifest.SUMS).write_text(text, encoding="utf-8", newline="\n")
        tool = shutil.which("sha256sum")
        if tool:
            r = subprocess.run([tool, "-c", manifest.SUMS], cwd=self.tmp, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(manifest.verify(m, self.tmp), [])
        (self.tmp / "headwind-state.tar.gz").write_bytes(b"tampered")
        self.assertEqual(len(manifest.verify(m, self.tmp)), 1)

    def test_same_release_gives_the_same_bytes_and_is_not_uploaded_again(self):
        out = self.tmp / "out"
        self.assertTrue(manifest.release("r", "state", out, None, assets=self.assets))
        body, sums = (out / manifest.JSON_NAME).read_bytes(), (out / manifest.SUMS).read_bytes()
        held = self.assets + [_asset(manifest.JSON_NAME, body), _asset(manifest.SUMS, sums)]
        self.assertFalse(manifest.release("r", "state", out, None, assets=held))
        self.assertEqual((out / manifest.JSON_NAME).read_bytes(), body)
        changed = [a if a["name"] != "headwind-state.tar.gz" else _asset(a["name"], b"new state") for a in held]
        self.assertTrue(manifest.release("r", "state", out, None, assets=changed))

    def test_verify_command(self):
        m = manifest.build("r", "state", self.assets)
        for name, data in self.files.items():
            (self.tmp / name).write_bytes(data)
        mp = self.tmp / manifest.JSON_NAME
        mp.write_bytes(manifest.manifest_bytes(m))
        self.assertEqual(manifest.main(["verify", str(mp), "--dir", str(self.tmp)]), 0)
        (self.tmp / "headwind-state-2026-11-20.tar.gz").write_bytes(b"changed")
        self.assertEqual(manifest.main(["verify", str(mp), "--dir", str(self.tmp)]), 1)


class Workflow(unittest.TestCase):
    """The update workflow builds the entity export, uploads it, and writes the manifests after every upload."""

    def setUp(self):
        self.wf = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
        m = re.search(r"- name: Entities \(FollowTheMoney\) and release checksums\n(.*?)(?=\n      - name: |\Z)",
                      self.wf, re.S)
        self.assertIsNotNone(m, "the entities and checksums step is missing")
        self.step = m.group(1)

    def test_step_comes_after_the_state_upload_and_before_the_private_archive(self):
        i = self.wf.index("- name: Entities (FollowTheMoney) and release checksums")
        self.assertLess(self.wf.index("- name: Second copy of the state in the release"), i)
        self.assertLess(i, self.wf.index("- name: Private archive (raw replies, to tic-archive)"))

    def test_export_is_checked_before_upload_and_every_release_gets_a_manifest(self):
        s = self.step
        self.assertIn("python -m headwind.ftm --state data/state", s)
        self.assertLess(s.index("python -m headwind.ftm"), s.index(f"gh release upload {ftm.RELEASE}"))
        self.assertIn(ftm.OUT_NAME, s)
        self.assertIn(ftm.ABOUT_NAME, s)
        self.assertIn("gh release list", s)
        self.assertIn("python -m headwind.manifest release", s)
        self.assertIn("--local-dir .", s)
        self.assertIn(manifest.SUMS, s)
        self.assertIn(manifest.JSON_NAME, s)
        self.assertNotIn("gh release delete", s)
        self.assertNotIn("delete-asset", s)


FAKE_GH = r"""#!/usr/bin/env bash
# A stand-in for gh: releases are folders under $STORE; every call is logged.
echo "gh $*" >> "$STORE/calls.log"
case "$1 $2" in
  "release view") [ -d "$STORE/$3" ] && exit 0 || exit 1 ;;
  "release create"|"release edit") mkdir -p "$STORE/$3"; exit 0 ;;
  "release list") ls -1 "$STORE" | grep -v calls.log; exit 0 ;;
  "release upload") tag="$3"; shift 3
    for f in "$@"; do case "$f" in --*) ;; *) cp "$f" "$STORE/$tag/";; esac; done; exit 0 ;;
  "api repos/"*) tag="${2##*/}"
    python3 - "$STORE/$tag" <<'PY'
import hashlib, json, os, sys
d = sys.argv[1]
out = []
for n in sorted(os.listdir(d)):
    b = open(os.path.join(d, n), "rb").read()
    out.append({"name": n, "size": len(b), "digest": "sha256:" + hashlib.sha256(b).hexdigest(),
                "updated_at": "2026-11-27T06:00:00Z"})
print(json.dumps(out))
PY
    exit 0 ;;
esac
echo "fake gh: unexpected call: $*" >&2; exit 2
"""


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bash") and shutil.which("python3"),
                     "runs the workflow step's own shell with a stand-in gh (Linux, as on the runner)")
class WorkflowStepRun(unittest.TestCase):
    def test_step_uploads_the_export_and_a_manifest_per_release(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_ftm import _state
        wf = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
        body = re.search(r"- name: Entities \(FollowTheMoney\) and release checksums\n(.*?)(?=\n      # Private archive)",
                         wf, re.S).group(1)
        script = "\n".join(l[10:] for l in body.split("run: |\n", 1)[1].splitlines()) + "\n"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            work, store, bin_ = d / "work", d / "store", d / "bin"
            for x in (work / "data" / "state", store / "state", bin_):
                x.mkdir(parents=True)
            s, c = _state()
            (work / "data" / "state" / "sanctions_index.json").write_text(json.dumps(s), encoding="utf-8")
            (work / "data" / "state" / "screening_index.json").write_text(json.dumps(c), encoding="utf-8")
            (work / "headwind-state.tar.gz").write_bytes(b"this run's state")
            (store / "state" / "headwind-state.tar.gz").write_bytes(b"this run's state")   # uploaded by the step before
            (store / "state" / "headwind-state-2026-11-15.tar.gz").write_bytes(b"an older copy")
            gh = bin_ / "gh"
            gh.write_text(FAKE_GH, encoding="utf-8")
            gh.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}",
                   "STORE": str(store), "RUNNER_TEMP": str(d / "tmp"), "GITHUB_REPOSITORY": "example/headwind",
                   "PYTHONPATH": str(ROOT)}
            run = lambda: subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True)
            r = run()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((store / "entities" / ftm.OUT_NAME).is_file())
            # The release notes are the exporter's, with every list's credit.
            made = [x for x in (store / "calls.log").read_text().splitlines() if x.startswith("gh release create entities")]
            self.assertTrue(made and "--notes-file " in made[0], made)
            notes = Path(made[0].split("--notes-file ", 1)[1].split()[0]).read_text(encoding="utf-8")
            self.assertIn(ftm.CC_BY_4_URL, notes)
            self.assertIn(ftm.OGL3_URL, notes)
            for tag in ("state", "entities"):
                m = json.loads((store / tag / manifest.JSON_NAME).read_text(encoding="utf-8"))
                self.assertEqual(manifest.verify(m, store / tag), [])
                names = {f["name"] for f in m["files"]}
                self.assertEqual(names, set(p.name for p in (store / tag).iterdir()) - set(manifest.OWN))
            self.assertIn("headwind-state-2026-11-15.tar.gz", (store / "state" / manifest.SUMS).read_text())
            # A second run with nothing changed uploads the export again but no manifest.
            (store / "calls.log").unlink()
            r = run()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            uploads = [x for x in (store / "calls.log").read_text().splitlines() if x.startswith("gh release upload")]
            self.assertTrue(uploads)
            self.assertFalse([x for x in uploads if manifest.SUMS in x], uploads)
            self.assertIn("checksums unchanged", r.stdout)
            # A local copy that is not what the release holds stops the step.
            (work / "headwind-state.tar.gz").write_bytes(b"something else")
            r = run()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("checksums not written", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
