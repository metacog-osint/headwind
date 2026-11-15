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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = os.environ.get("HEADWIND_UA", "Mozilla/5.0 (compatible; research-collector/1.0)")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


RETRY_WAIT = 10   # seconds before the one retry


def _retryable(exc: Exception) -> bool:
    """A timeout, a dropped connection or a server error is tried once more; a refusal (4xx) is not."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def get(url: str, timeout: int = 60, wait: float = RETRY_WAIT) -> bytes:
    """Fetch a URL, trying once more after a short wait when the failure looks passing (EIA timed out on
    13 and 14 Nov 2026 and answered on the next try)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        if not _retryable(exc):
            raise
    time.sleep(wait)
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
