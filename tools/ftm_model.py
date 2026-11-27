"""Write headwind/ftm_model.json: the part of the FollowTheMoney data model that Headwind's entity export uses.

FollowTheMoney (FtM) publishes its whole model as JSON in its repository (js/src/defaultModel.json, built from the
YAML schema files by its own `make default-model`). This keeps, for the schemata the export writes and every
schema they extend, the properties with their types, which schemata are abstract and which properties are
required, and the values the `country` and `topic` types accept. headwind/ftm.py checks every line it writes
against it, so the export uses FtM's own names and values exactly.

    python tools/ftm_model.py                       # fetch the pinned tag from GitHub
    python tools/ftm_model.py --model defaultModel.json

FollowTheMoney is MIT-licensed (Copyright (c) 2017-2024 Journalism Development Network, Inc.; Copyright (c) 2025
OpenSanctions Datenbanken GmbH); the extract keeps that notice. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

TAG = "v4.11.3"
URL = f"https://raw.githubusercontent.com/opensanctions/followthemoney/{TAG}/js/src/defaultModel.json"
OUT = Path(__file__).resolve().parent.parent / "headwind" / "ftm_model.json"
# The schemata headwind/ftm.py writes; their parents are added.
USED = ("Person", "Organization", "LegalEntity", "Vessel", "Airplane", "Sanction")
NOTICE = ("Extract of the FollowTheMoney data model (js/src/defaultModel.json), MIT License. Copyright (c) "
          "2017-2024 Journalism Development Network, Inc.; Copyright (c) 2025 OpenSanctions Datenbanken GmbH.")


def extract(model: dict, tag: str = TAG) -> dict:
    schemata = model["schemata"]
    keep: list[str] = []

    def add(name: str) -> None:
        if name not in keep:
            keep.append(name)
            for parent in schemata[name].get("extends") or []:
                add(parent)
    for name in USED:
        add(name)
    out = {"source": f"https://github.com/opensanctions/followthemoney/blob/{tag}/js/src/defaultModel.json",
           "version": model.get("version"), "licence": NOTICE, "schemata": {}, "types": {}}
    for name in sorted(keep):
        s = schemata[name]
        out["schemata"][name] = {
            "extends": list(s.get("extends") or []), "abstract": bool(s.get("abstract")),
            "required": list(s.get("required") or []),
            "properties": {p: {k: v for k, v in d.items() if k in ("type", "maxLength", "range")}
                           for p, d in sorted(s.get("properties", {}).items())}}
    types = model["types"]
    out["types"] = {
        "country": {"values": dict(sorted(types["country"]["values"].items()))},
        "topic": {"values": dict(sorted(types["topic"]["values"].items()))},
        "maxLength": {t: d.get("maxLength") for t, d in sorted(types.items()) if d.get("maxLength")}}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="a local copy of defaultModel.json (default: fetch the pinned tag)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    if args.model:
        model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:
            model = json.loads(r.read())
    if model.get("version") != TAG.lstrip("v"):
        print(f"model version {model.get('version')} is not {TAG}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(extract(model), ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                              newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
