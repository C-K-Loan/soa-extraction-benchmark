#!/usr/bin/env python3
"""Download the protocol PDFs this benchmark annotates.

The PDFs are not redistributed here. They are public documents hosted by
ClinicalTrials.gov and are fetched by NCT identifier, so the bundle stays small
and carries no third-party content.

    python3 fetch_protocols.py gold_nct_ids.txt   --out pdfs/
    python3 fetch_protocols.py silver_nct_ids.txt --out pdfs/
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies/{nct}?fields=DocumentSection"
DOC = "https://cdn.clinicaltrials.gov/large-docs/{tail}"


def documents(nct):
    with urllib.request.urlopen(API.format(nct=nct), timeout=60) as r:
        body = json.load(r)
    section = (body.get("documentSection") or {}).get("largeDocumentModule") or {}
    return section.get("largeDocs") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", help="a file of NCT identifiers, one per line")
    ap.add_argument("--out", default="pdfs", help="destination directory")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between requests")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ncts = [x.strip() for x in Path(a.ids).read_text().split() if x.strip()]
    ok = failed = 0
    for i, nct in enumerate(ncts, 1):
        try:
            docs = documents(nct)
        except urllib.error.URLError as e:
            print(f"[{i}/{len(ncts)}] {nct}: index failed, {e}", file=sys.stderr)
            failed += 1
            continue
        if not docs:
            print(f"[{i}/{len(ncts)}] {nct}: no documents listed", file=sys.stderr)
            failed += 1
            continue
        for d in docs:
            tail = f"{nct[-2:]}/{nct}/{d['filename']}"
            dest = out / nct / d["filename"]
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(DOC.format(tail=tail), dest)
                ok += 1
                print(f"[{i}/{len(ncts)}] {nct}/{d['filename']}")
            except urllib.error.URLError as e:
                print(f"[{i}/{len(ncts)}] {nct}/{d['filename']}: {e}", file=sys.stderr)
                failed += 1
        time.sleep(a.sleep)
    print(f"\ndownloaded {ok}, failed {failed}, into {out}/")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
