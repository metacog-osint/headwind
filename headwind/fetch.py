"""Fetch a source, hash it, and keep the raw copy before anything is derived from it.

Collection order (suite rule): fetch, hash, store the raw copy, record the times, then derive.
Raw copies go under data/raw/<source>/<sha12>.<ext> (git-ignored), and every fetch adds one line
to data/raw/index.jsonl, so a later reader can tell which bytes a number came from.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = os.environ.get("HEADWIND_UA", "Mozilla/5.0 (compatible; research-collector/1.0)")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch(source_id: str, url: str, raw_dir: Path | None, ext: str, timeout: int = 60, getter=None,
          gz: bool = False) -> tuple[bytes, dict]:
    """Return (bytes, record). The record carries the URL, SHA-256, size and fetch time.

    gz stores the raw copy gzipped (for large files); the hash and size are of the bytes as fetched."""
    body = (getter or get)(url, timeout)
    sha = hashlib.sha256(body).hexdigest()
    rec = {"source_id": source_id, "url": url, "sha256": sha, "bytes": len(body), "fetched_at": now_utc()}
    if raw_dir is not None:
        dest = Path(raw_dir) / source_id
        dest.mkdir(parents=True, exist_ok=True)
        f = dest / (f"{sha[:12]}.{ext}" + (".gz" if gz else ""))
        if not f.exists():
            f.write_bytes(gzip.compress(body, 6) if gz else body)
        with (Path(raw_dir) / "index.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec) + "\n")
    return body, rec
