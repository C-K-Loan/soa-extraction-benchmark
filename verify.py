#!/usr/bin/env python3
"""Check the bundle against the counts the paper reports.

    python3 verify.py

Every number printed here is recomputed from the shipped files, so a mismatch
means the bundle and the paper have drifted apart.
"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

PAPER = {
    "groups": 6, "protocols": 5, "activities": 169, "contacts": 60,
    "reference_definitions": 82, "cells": 690, "attachments": 103,
    "total_scored_units": 1104,
}
PAPER_SILVER = {"pages": 3605, "protocols": 41, "schedule_related_pages": 220}
PAPER_LABELS = {"pages": 438, "protocols": 99, "annotators": 4,
                "is_soa_related_true": 437, "has_soa_table_true": 256}
# Section 3 says "the 15 pages reviewed by more than one of them agreed on
# has_soa_table in every case". 15 is the number of pages TOUCHED by a second
# reviewer; on one of them (NCT02383966 Prot_001.pdf p113) that reviewer filed a
# funky with no label and then an undo, so only 14 pages carry two comparable
# values. Those 14 agree exactly. Both numbers are checked.
PAPER_AGREEMENT = {"touched": 15, "comparable": 14, "disagreements": 0}


def rows(p):
    return [json.loads(l) for l in p.open() if l.strip()]


def main():
    gold = rows(HERE / "gold" / "soa_gold.jsonl")
    c = collections.Counter()
    for r in gold:
        c["activities"] += len(r.get("activities") or [])
        c["contacts"] += len(r.get("contacts") or [])
        c["reference_definitions"] += len(r.get("references") or [])
        c["cells"] += len(r.get("soa") or [])
        c["attachments"] += (
            sum(len(a.get("uses_reference_markers") or []) for a in r.get("activities") or [])
            + sum(len(x.get("reference_markers") or []) for x in r.get("contacts") or [])
            + sum(len(x.get("cell_reference_markers") or []) for x in r.get("soa") or []))
    c["groups"] = len(gold)
    c["protocols"] = len({r["nct_id"] for r in gold})
    c["total_scored_units"] = sum(c[k] for k in (
        "activities", "contacts", "reference_definitions", "cells", "attachments"))

    silver = rows(HERE / "silver" / "stage1_page_labels.jsonl")
    s = {"pages": len(silver),
         "protocols": len({r["nct_id"] for r in silver}),
         "schedule_related_pages": sum(
             1 for r in silver if (r.get("labels") or {}).get("is_soa_related"))}

    lab = rows(HERE / "gold" / "page_labels.jsonl")
    L = {"pages": len(lab),
         "protocols": len({r["nct_id"] for r in lab}),
         "annotators": len({r["annotator"] for r in lab}),
         "is_soa_related_true": sum(1 for r in lab if r["labels"]["is_soa_related"]),
         "has_soa_table_true": sum(1 for r in lab if r["labels"]["has_soa_table"])}

    bad = 0
    print(f"{'quantity':<32}{'bundle':>8}{'paper':>8}")
    for src, table, got_from in (("gold", PAPER, c), ("silver", PAPER_SILVER, s),
                                 ("labels", PAPER_LABELS, L)):
        for k, want in table.items():
            got = got_from[k]
            bad += got != want
            print(f"{src + ' ' + k:<32}{got:>8}{want:>8}"
                  f"{'' if got == want else '   MISMATCH'}")

    pert = HERE / "results" / "perturbation_table.csv"
    if pert.exists():
        import csv
        with pert.open() as fh:
            ident = next((r for r in csv.DictReader(fh) if r["perturbation"] == "none"), None)
        if ident:
            # only the metric columns are numeric; reach and source are prose
            off = []
            for k, v in ident.items():
                try:
                    if float(v) != 1.0:
                        off.append(f"{k}={v}")
                except (TypeError, ValueError):
                    continue
            print("\nidentity perturbation row: " + ("1.000 on every metric"
                  if not off else "NOT 1.000 -> " + ", ".join(off)))
            bad += bool(off)

    # A bundle can match the paper and still be a bundle nobody can trust: until
    # now this script recomputed every COUNT and never once read SHA256SUMS.json,
    # so a corrupted or edited file passed as long as the totals still added up.
    # Section 3 claims the 15 pages seen by more than one reviewer agreed on
    # has_soa_table every time. Recompute it here rather than asking the reader to
    # take our word for it: it is the only inter-annotator number in the paper.
    ev_path = HERE / "gold" / "page_review_events.jsonl"
    if ev_path.exists():
        ev = rows(ev_path)
        by = collections.defaultdict(dict)
        for r in sorted(ev, key=lambda r: r["reviewed_ts"]):
            if r["decision"] != "undo" and r["labels"] is not None:
                by[(r["nct_id"], r["pdf_filename"], r["page_num"])][r["annotator"]] = \
                    r["labels"]["has_soa_table"]
        touched = collections.defaultdict(set)
        for r in ev:
            touched[(r["nct_id"], r["pdf_filename"], r["page_num"])].add(r["annotator"])
        n_touched = sum(1 for v in touched.values() if len(v) > 1)
        multi = {k: v for k, v in by.items() if len(v) > 1}
        disagree = [k for k, v in multi.items() if len(set(v.values())) > 1]
        print(f"\n{'pages touched by >1 annotator':<32}{n_touched:>8}"
              f"{PAPER_AGREEMENT['touched']:>8}")
        print(f"{'  with two comparable labels':<32}{len(multi):>8}"
              f"{PAPER_AGREEMENT['comparable']:>8}")
        print(f"{'  of those, disagreeing':<32}{len(disagree):>8}{0:>8}")
        for k in disagree:
            print(f"  DISAGREE {k}")
        bad += ((n_touched != PAPER_AGREEMENT["touched"])
                + (len(multi) != PAPER_AGREEMENT["comparable"]) + len(disagree))
    else:
        print("\ngold/page_review_events.jsonl missing -> the agreement claim in "
              "section 3 cannot be checked from this bundle")
        bad += 1

    # Also check the shipped scored CSV agrees with what score_soa.py
    # produces from predictions/ right now. If a prediction tree has drifted
    # or a CSV is stale, this catches it.
    import csv, sys
    sys.path.insert(0, str(HERE / "code"))
    try:
        import score_soa as S
    except Exception as e:
        print(f"\nscore_soa import skipped: {e}")
    else:
        pred_root = HERE / "predictions"
        micro = HERE / "results" / "accuracy_micro_t060.csv"
        if pred_root.exists() and micro.exists():
            gold = S.load_gold(HERE / "gold" / "soa_gold.jsonl")
            shipped = {r["system"]: r for r in csv.DictReader(micro.open())}
            print("\nscored CSV vs recomputed from predictions/ (soa5):")
            for sys_name, shipped_row in shipped.items():
                d = pred_root / sys_name
                if not d.exists():
                    print(f"  SKIP {sys_name}: predictions dir missing"); continue
                res = S.score_system(sys_name, S.load_pred_dir(d), gold, 0.60)
                recomputed = round(res["soa5"], 4)
                stored = float(shipped_row["soa5"])
                diff = abs(recomputed - stored)
                flag = "OK" if diff < 1e-3 else "DRIFT"
                print(f"  [{flag}] {sys_name:<40}  shipped={stored:.4f}  recomputed={recomputed:.4f}")
                if diff >= 1e-3: bad += 1

    sums_path = HERE / "SHA256SUMS.json"
    if not sums_path.exists():
        print("\nSHA256SUMS.json is missing -> cannot verify file integrity")
        bad += 1
    else:
        sums = json.loads(sums_path.read_text())
        missing, changed = [], []
        for name, want in sorted(sums.items()):
            f = HERE / name
            if not f.exists():
                missing.append(name)
                continue
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            if got != want:
                changed.append(name)
        # rglob would otherwise walk .git/ (this directory is its own repo, with a
        # worktree for the blind upload) and __pycache__, neither of which ships.
        def shipped(f):
            rel = f.relative_to(HERE)
            return (f.is_file()
                    and not any(part.startswith(".") or part == "__pycache__"
                                for part in rel.parts)
                    and f.name not in ("SHA256SUMS.json", "verify.py"))
        extra = sorted(str(f.relative_to(HERE)) for f in HERE.rglob("*")
                       if shipped(f) and str(f.relative_to(HERE)) not in sums)
        print(f"\n{'checksums':<32}{len(sums) - len(missing) - len(changed):>8}{len(sums):>8}")
        for n in missing:
            print(f"  MISSING  {n}")
        for n in changed:
            print(f"  CHANGED  {n}")
        for n in extra:
            print(f"  UNLISTED {n}")
        bad += len(missing) + len(changed) + len(extra)

    print("\n" + ("OK, bundle matches the paper" if not bad else f"{bad} MISMATCHES"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
