"""Private archive (19 Nov 2026, retention rule): update.yml sends the raw replies to the PRIVATE repo
metacog-osint/tic-archive after the deploy (tools/tic_archive.py). Live views are untouched: no program code changed."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "tools"))   # after ROOT: tools/<program>.py must not shadow the package
import tic_archive as ta  # noqa: E402

NOW = datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
PROGRAM = "headwind"
WF = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
STEP = WF[WF.index("- name: Private archive (raw replies, to tic-archive)"):]


def put(files: dict, **kw):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw"
        for rel, text in files.items():
            (raw / rel).parent.mkdir(parents=True, exist_ok=True)
            (raw / rel).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        store = ta.DirStore(Path(td) / "store")
        arch = ta.Archive(store, PROGRAM, "raw")
        doc = arch.put(raw, now=NOW, **kw)["doc"]
        arch.restore(Path(td) / "out")
        out = {p.relative_to(Path(td) / "out").as_posix(): p.read_bytes()
               for p in (Path(td) / "out").rglob("*") if p.is_file()}
        return doc, out


def step_args(flag):
    """Values given to one tic_archive.py flag in the workflow step."""
    toks = STEP.replace("\\n", " ").split()
    return [toks[i + 1].strip("'\"") for i, t in enumerate(toks) if t == flag]


class Workflow(unittest.TestCase):
    def test_step_after_deploy_with_private_token_and_loud_failure(self):
        self.assertLess(WF.index("- name: Deploy site/ to Cloudflare Pages"), WF.index(STEP[:40]))
        self.assertIn("GH_TOKEN: ${{ secrets.TIC_ARCHIVE_TOKEN }}", STEP)
        self.assertNotIn("github.token", STEP)
        self.assertIn(f"--program {PROGRAM} --lane raw --src data/raw", STEP)
        self.assertIn("exit 1", STEP)
        self.assertNotIn("|| true", STEP)

    def test_raw_never_published_by_this_repo(self):
        for chunk in WF.split("uses: actions/upload-artifact")[1:]:
            self.assertNotIn("data/raw", chunk.split("path:", 1)[1].split("\n", 1)[0])
        self.assertNotIn("data/raw", WF.split("cache/save", 1)[1].split("- name:", 1)[0] if "cache/save" in WF else "")


class Keys(unittest.TestCase):
    @mock.patch.dict(os.environ)
    def test_api_keys_removed_if_echoed(self):
        self.assertEqual(step_args("--redact-env-if-set"), ["EIA_API_KEY", "CENSUS_API_KEY"])
        self.assertIn("EIA_API_KEY: ${{ secrets.EIA_API_KEY }}", STEP)
        self.assertIn("CENSUS_API_KEY: ${{ secrets.CENSUS_API_KEY }}", STEP)
        os.environ["EIA_API_KEY"] = "TESTKEY0123456789"
        os.environ.pop("CENSUS_API_KEY", None)
        try:
            red = ta.Redactor([], [], step_args("--redact-env-if-set"))
            doc, out = put({"eia/a.json": '{"request":{"params":{"api_key":"TESTKEY0123456789"}},"data":[1]}',
                            "ofac-sdn/b.csv": "1,NAME,individual\n"}, redactor=red)
        finally:
            del os.environ["EIA_API_KEY"]
        self.assertNotIn(b"TESTKEY0123456789", out["eia/a.json"])
        self.assertIn(b'"data":[1]', out["eia/a.json"])
        self.assertEqual(out["ofac-sdn/b.csv"], b"1,NAME,individual\n")


if __name__ == "__main__":
    unittest.main()
