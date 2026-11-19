"""Durable archives (retention-2026-11): nothing Headwind has measured is lost, whatever the live view keeps.

* `history/deltas/YYYY-MM.jsonl.gz`: every sanctions and screening-list change in full (`sanctions.roll` drops them
  from the snapshot after KEEP_DAYS = 30; the feed text names at most 25). One JSON object per change, the delta as
  `collect` made it, plus `"kind"` ("sanctions" or "screening").
* `history/fetch-index/YYYY-MM.jsonl`: the rows of the fetch index (source, url, sha256, bytes, fetched_at) of each
  run. Raw bodies are not kept (licences; see the report): the hash shows which file was read.

Both are append-only and idempotent. The snapshot holds the last 30 days of changes, so every run offers all of
them again and only ids not yet archived are written: a run that missed the history commit is healed by the next.
The file is named for the month the run archives in (UTC), so a month's file is never opened again once the month
is over; a change found late goes into the open month's file with its own `detected_at`.

Gzip files are written by appending one gzip member per run (`ab`), which is valid gzip and rewrites no byte.

Standard library only."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Privacy switch. Tom, 19 Nov 2026: removed individuals are retained in full (government lists, publicly
# released). False: an individual removed from a list is archived as a count plus
# the list id only, as the published history log already does. True: the full record (name, type, programs, address
# countries, listing date) is archived too. Entries of unstated type count as individuals, as in
# names.person_data. Organizations, ships, and individuals added or changed are always archived in full.
ARCHIVE_REMOVED_INDIVIDUALS = True

NOT_INDIVIDUAL = ("entity", "vessel", "aircraft")


def _is_individual(rec: dict) -> bool:
    return rec.get("type") not in NOT_INDIVIDUAL


def prepare(delta: dict, kind: str, archive_removed_individuals: bool | None = None) -> dict:
    """The delta as archived: a copy, with removed individuals reduced to list ids unless the flag is on."""
    keep = ARCHIVE_REMOVED_INDIVIDUALS if archive_removed_individuals is None else archive_removed_individuals
    rec = {"kind": kind, **json.loads(json.dumps(delta))}
    removed = rec.get("named_removed")
    if removed is not None and not keep:
        people = [r for r in removed if _is_individual(r)]
        rec["named_removed"] = [r for r in removed if not _is_individual(r)]
        rec["removed_individuals"] = len(people)
        rec["removed_individuals_list_ids"] = sorted(r.get("list_id") for r in people if r.get("list_id"))
    return rec


def _read_gz_lines(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield line


def archived_ids(deltas_dir: Path) -> set[str]:
    out = set()
    for p in sorted(deltas_dir.glob("*.jsonl.gz")):
        for line in _read_gz_lines(p):
            try:
                out.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue
    return out


def append_deltas(snapshot: dict, history_dir: Path, now: datetime | None = None,
                  archive_removed_individuals: bool | None = None) -> int:
    """Append the snapshot's changes not yet archived to this month's file; returns the number written."""
    now = now or datetime.now(timezone.utc)
    d = Path(history_dir) / "deltas"
    seen = archived_ids(d) if d.exists() else set()
    lines = []
    for kind in ("sanctions", "screening"):
        for delta in sorted(snapshot.get(kind) or [], key=lambda x: x.get("detected_at", "")):
            if not delta.get("id") or delta["id"] in seen:
                continue
            seen.add(delta["id"])
            lines.append(json.dumps(prepare(delta, kind, archive_removed_individuals), ensure_ascii=False,
                                    separators=(",", ":"), sort_keys=True) + "\n")
    if not lines:
        return 0
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{now:%Y-%m}.jsonl.gz", "ab") as fh:
        fh.write(gzip.compress("".join(lines).encode("utf-8"), 9, mtime=0))
    return len(lines)


def append_fetch_index(index_path: Path, history_dir: Path, now: datetime | None = None) -> int:
    """Append fetch-index rows not yet in this month's file. Only the metadata, never a body."""
    index_path = Path(index_path)
    if not index_path.exists():
        return 0
    now = now or datetime.now(timezone.utc)
    d = Path(history_dir) / "fetch-index"
    target = d / f"{now:%Y-%m}.jsonl"
    seen = set(target.read_text(encoding="utf-8").splitlines()) if target.exists() else set()
    rows = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        row = json.dumps({k: r.get(k) for k in ("source_id", "url", "sha256", "bytes", "fetched_at")},
                         ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if row not in seen:
            seen.add(row)
            rows.append(row + "\n")
    if not rows:
        return 0
    d.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(rows))
    return len(rows)


def vessels_digest(path: Path) -> str:
    """12-hex digest of data/vessels.json without its run times, so a run that changed no ship has the same digest."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    doc.pop("generated_at", None)
    (doc.get("summary") or {}).pop("checked_at", None)
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headwind retention archives")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append", help="archive deltas and fetch-index rows into history/")
    a.add_argument("--snapshot", default="data/snapshot.json")
    a.add_argument("--raw-index", default="data/raw/index.jsonl")
    a.add_argument("--history", default="history")
    v = sub.add_parser("vessels-digest", help="print the digest of data/vessels.json")
    v.add_argument("path")
    args = ap.parse_args(argv)
    if args.cmd == "vessels-digest":
        print(vessels_digest(Path(args.path)))
        return 0
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    n = append_deltas(snap, Path(args.history))
    m = append_fetch_index(Path(args.raw_index), Path(args.history))
    print(f"archive: {n} list change(s) and {m} fetch-index row(s) appended to {args.history}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
