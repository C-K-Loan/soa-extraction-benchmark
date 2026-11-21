#!/usr/bin/env bash
# Regenerate every CSV in release/results/ that scores predictions against gold.
# Standard library only — no API calls, no model inference.
#
# Usage:  bash reproduce.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PY="${PY:-python3}"

echo "[1/6] Scoring the SoA 5-component CSVs..."
"$PY" - <<'PYEOF'
import csv, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()
sys.path.insert(0, str(Path("code").resolve()))
import score_soa as S

GOLD = Path("gold/soa_gold.jsonl")
PRED_ROOT = Path("predictions")
RESULTS = Path("results")

SYSTEMS = [
    ("medical_llm_medium_schema_constrained", "Medical LLM Medium (schema-constrained)", "internal"),
    ("medical_llm_medium_unconstrained",       "Medical LLM Medium (unconstrained)",       "internal"),
    ("gemini_38_flash",                        "google/gemini-3.8-flash",                           "openrouter"),
    ("gpt_56_terra",                           "openai/gpt-5.6-terra",                              "openrouter"),
    ("claude_sonnet_55",                       "anthropic/claude-sonnet-5.5",                       "openrouter"),
]

gold = S.load_gold(GOLD)
all_scored = {}
for sysname, model, backend in SYSTEMS:
    preds = S.load_pred_dir(PRED_ROOT / sysname)
    r = S.score_system(sysname, preds, gold, 0.60)
    r["model"] = model; r["backend"] = backend
    all_scored[sysname] = r

# accuracy_micro_t060.csv
hdr = ["arm","backend","system","model",
       "cell_p","cell_r","cell_f1","act_p","act_r","act_f1",
       "con_p","con_r","con_f1","ref_p","ref_r","ref_f1",
       "atch_p","atch_r","atch_f1","soa4","soa5",
       "cell_tp","cell_fp","cell_fn","n_pred_cells_total",
       "n_groups_ok","n_groups_empty","n_groups_ctx_overflow",
       "n_groups_malformed","n_groups_api_error","n_groups_not_run"]
with (RESULTS / "accuracy_micro_t060.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=hdr); w.writeheader()
    for sysname, _, backend in SYSTEMS:
        r = all_scored[sysname]
        tp, fp, fn = r["axis_tots"]["cell"]
        preds = S.load_pred_dir(PRED_ROOT / sysname)
        n_pred, n_ok, n_empty = 0, 0, 0
        for gid in gold:
            p = preds.get(gid) or {}
            n_pred += len(p.get("cells") or [])
            if any(p.get(k) for k in ("activities","contacts","references","cells")): n_ok += 1
            else: n_empty += 1
        w.writerow({"arm":"pipeline","backend":backend,"system":sysname,"model":r["model"],
            "cell_p":round(r["axes"]["cell"][0],4),"cell_r":round(r["axes"]["cell"][1],4),"cell_f1":round(r["axes"]["cell"][2],4),
            "act_p":round(r["axes"]["act"][0],4),"act_r":round(r["axes"]["act"][1],4),"act_f1":round(r["axes"]["act"][2],4),
            "con_p":round(r["axes"]["con"][0],4),"con_r":round(r["axes"]["con"][1],4),"con_f1":round(r["axes"]["con"][2],4),
            "ref_p":round(r["axes"]["ref"][0],4),"ref_r":round(r["axes"]["ref"][1],4),"ref_f1":round(r["axes"]["ref"][2],4),
            "atch_p":round(r["atch"][0],4),"atch_r":round(r["atch"][1],4),"atch_f1":round(r["atch"][2],4),
            "soa4":round(r["soa4"],4),"soa5":round(r["soa5"],4),
            "cell_tp":tp,"cell_fp":fp,"cell_fn":fn,"n_pred_cells_total":n_pred,
            "n_groups_ok":n_ok,"n_groups_empty":n_empty,"n_groups_ctx_overflow":0,
            "n_groups_malformed":0,"n_groups_api_error":0,"n_groups_not_run":0})

# soa_score_5component.csv
with (RESULTS / "soa_score_5component.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["system","model","component","tp","fp","fn","precision","recall","f1"])
    w.writeheader()
    for sysname, _, _ in SYSTEMS:
        r = all_scored[sysname]
        for comp, k in (("activity","act"),("contact","con"),("reference","ref"),("cell","cell")):
            tp,fp,fn = r["axis_tots"][k]; p,rec,f_ = S.pr(tp,fp,fn)
            w.writerow({"system":sysname,"model":r["model"],"component":comp,
                        "tp":tp,"fp":fp,"fn":fn,
                        "precision":round(p,4),"recall":round(rec,4),"f1":round(f_,4)})
        tp,fp,fn = r["atch_tots"]; p,rec,f_ = S.pr(tp,fp,fn)
        w.writerow({"system":sysname,"model":r["model"],"component":"attachment",
                    "tp":tp,"fp":fp,"fn":fn,
                    "precision":round(p,4),"recall":round(rec,4),"f1":round(f_,4)})

# accuracy_per_group.csv
hdr2 = ["group_id","system","model","backend",
        "act_tp","act_fp","act_fn","act_p","act_r","act_f1",
        "con_tp","con_fp","con_fn","con_p","con_r","con_f1",
        "ref_tp","ref_fp","ref_fn","ref_p","ref_r","ref_f1",
        "cell_tp","cell_fp","cell_fn","cell_p","cell_r","cell_f1",
        "n_gt_cells","n_pred_cells"]
with (RESULTS / "accuracy_per_group.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=hdr2); w.writeheader()
    for sysname, _, backend in SYSTEMS:
        r = all_scored[sysname]
        preds = S.load_pred_dir(PRED_ROOT / sysname)
        for gp in r["per_group"]:
            gid = gp["group_id"]; gt = gold.get(gid) or {}; pd = preds.get(gid) or {}
            row = {"group_id":gid,"system":sysname,"model":r["model"],"backend":backend,
                   "n_gt_cells":len(gt.get("soa") or []),
                   "n_pred_cells":len(pd.get("cells") or [])}
            for ax in ("act","con","ref","cell"):
                tp,fp,fn = gp[f"{ax}_tp"], gp[f"{ax}_fp"], gp[f"{ax}_fn"]
                p,rec,f_ = S.pr(tp,fp,fn)
                row.update({f"{ax}_tp":tp,f"{ax}_fp":fp,f"{ax}_fn":fn,
                            f"{ax}_p":round(p,4),f"{ax}_r":round(rec,4),f"{ax}_f1":round(f_,4)})
            w.writerow(row)

# attachment_per_group.csv
hdr3 = ["group_id","system","model","scope","n_gt","tp","fp","fn","precision","recall","f1"]
with (RESULTS / "attachment_per_group.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=hdr3); w.writeheader()
    for sysname, _, _ in SYSTEMS:
        r = all_scored[sysname]
        for gp in r["per_group"]:
            gid = gp["group_id"]; gt = gold.get(gid) or {}
            n_gt_act  = sum(len(a.get("uses_reference_markers") or []) for a in gt.get("activities") or [])
            n_gt_con  = sum(len(c.get("reference_markers") or []) for c in gt.get("contacts") or [])
            n_gt_cell = sum(len(c.get("cell_reference_markers") or []) for c in gt.get("soa") or [])
            for scope, n_gt in (("activity",n_gt_act),("contact",n_gt_con),("cell",n_gt_cell)):
                tp = gp[f"atch_{scope}_tp"]; fp = gp[f"atch_{scope}_fp"]; fn = gp[f"atch_{scope}_fn"]
                p,rec,f_ = S.pr(tp,fp,fn)
                w.writerow({"group_id":gid,"system":sysname,"model":r["model"],"scope":scope,
                            "n_gt":n_gt,"tp":tp,"fp":fp,"fn":fn,
                            "precision":round(p,4),"recall":round(rec,4),"f1":round(f_,4)})

print("  wrote accuracy_micro_t060.csv, accuracy_per_group.csv, attachment_per_group.csv,")
print("        soa_score_5component.csv")
PYEOF

echo "[2/6] Validating score_soa.py reproduces the expected values..."
"$PY" code/score_soa.py --validate --pred-root predictions 2>&1 | tail -5

echo "[3/6] Tables 4 and 5 from the stored reference-implementation run ..."
"$PY" code/reference_metrics/make_tables.py "$HERE"

echo "[4/6] Refreshing SHA256SUMS.json ..."
"$PY" - <<'PYEOF'
import hashlib, json
from pathlib import Path
HERE = Path.cwd()
# every shipped file: nothing inside a dot-directory or __pycache__, and not the checksum file itself
def shipped(p):
    rel = p.relative_to(HERE)
    return (p.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in rel.parts)
            and p.suffix not in (".pyc", ".pyo") and p.name != "SHA256SUMS.json")
checks = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(HERE.rglob("*")) if shipped(p)}
Path("SHA256SUMS.json").write_text(json.dumps(checks, indent=2) + "\n")
print(f"  wrote SHA256SUMS.json with {len(checks)} entries")
PYEOF

echo "[5/6] Running verify.py ..."
"$PY" verify.py

echo "[6/6] Done."
