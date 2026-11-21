#!/usr/bin/env python3
"""Score Schedule-of-Activities predictions against the gold set.

The SoA score is a pooled micro-F1 over five components:
    activities + contacts + reference_definitions + cells + attachments

Pair owners under a tolerant matcher at threshold 0.60 (SequenceMatcher ratio
on normalised text; see `_norm`). Attachment units are (owner, marker) pairs
at three scopes: activity, contact, cell. Within a matched owner pair the
marker string must match exactly for a TP; gold markers whose owner does
not match in gold-vs-pred are counted as FN (never dropped).

The scorer is standard-library only — no numpy, no pandas.

Usage:
  python3 score_soa.py --validate                            # reproduce the 4 published rows
  python3 score_soa.py --gold gold/soa_gold.jsonl \
                       --pred predictions/<system>/ \
                       --threshold 0.60 \
                       --out scores.csv
  python3 score_soa.py --pred predictions/<system>/ --normalize           # every component counts equally
  python3 score_soa.py --pred predictions/<system>/ --weights attach=5    # attachments count five-fold

Weighting (optional, the published score uses neither knob):
  The SoA score pools counts, so a component weighs as much as it has units
  (cells 690, activities 169, attachments 103, reference definitions 82,
  contacts 60 in the gold set). Two knobs change that:
    --weights c=w,...  multiplies the TP/FP/FN counts of component c by w
                       (components: act, con, ref, cell, attach; default 1;
                       and temporal, default 0, see below).
    --normalize        first divides each component's counts by its number of
                       gold units, so every component carries the same mass.
  SoA_w = 2*sum_c(k_c*TP_c) / (2*sum_c(k_c*TP_c) + sum_c(k_c*FP_c) + sum_c(k_c*FN_c)),
  k_c = w_c, or w_c / N_c with --normalize, N_c = TP_c + FN_c.
  With all weights 1 and no normalisation this is the published SoA-5 score.

Temporal component (optional, weight 0 by default, so it is off):
  --weights temporal=1 adds a sixth component that scores the structured timing
  of each contact (`contact_interval_relative_from_anchor`). Contacts are paired
  by the same matcher as the contacts component. Units: one per gold contact
  with a target, one per gold contact with a window. A wrong value is one FP
  and one FN; a gold contact without a matched prediction is an FN; a predicted
  value with no gold value (on a matched or an unmatched predicted contact) is
  an FP. Weeks convert to days, a window side of 0 equals an empty side, target
  0 equals 0 in any unit, and a target plus window describing the same allowed
  interval counts as correct ("Days: 3/4" as day 3 +1 or as day 4 -1).

NOTE on reproducibility: Qwen and GPT TP/FP/FN under this scorer are off by
one unit each from the originally published attachment counts (Qwen 50/46/53
vs 50/47/53; GPT 72/26/31 vs 71/27/32). The SoA-5 delta is <0.1 pp for Qwen
(60.81 vs 60.77) and 0.1 pp for GPT (93.45 rounds to 93.5 vs 93.4). Claude
and Gemini reproduce exactly. The paper reports the originally published
values; see the camera-ready caveat note. The original scoring code is no
longer in the repo and five tried variants did not recover the 1-unit drift
without disturbing Claude+Gemini.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path


# ---------- normalisation + fuzzy pairing ----------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _pair_fuzzy(gs: list[str], ps: list[str], threshold: float = 0.60):
    """Return (tp, fp, fn, match_map). Owners are matched greedy-best-ratio
    across the fuzzy threshold, exact matches first."""
    gs_n = [_norm(x) for x in gs]
    ps_n = [_norm(x) for x in ps]
    mg, mp, mapping = set(), set(), {}
    for i, g in enumerate(gs_n):
        for j, p in enumerate(ps_n):
            if j in mp: continue
            if g == p and g:
                mg.add(i); mp.add(j); mapping[i] = j; break
    pairs = []
    for i, g in enumerate(gs_n):
        if i in mg: continue
        for j, p in enumerate(ps_n):
            if j in mp: continue
            r = SequenceMatcher(None, g, p).ratio()
            if r >= threshold:
                pairs.append((r, i, j))
    pairs.sort(reverse=True)
    for _, i, j in pairs:
        if i in mg or j in mp: continue
        mg.add(i); mp.add(j); mapping[i] = j
    tp = len(mg)
    fp = len(ps_n) - len(mp)
    fn = len(gs_n) - len(mg)
    return tp, fp, fn, mapping


# ---------- Axis scoring: activities, contacts, references, cells ----------

def _score_group_axes(gold: dict, pred: dict, threshold: float) -> dict:
    gt_acts = [a.get("text", "") for a in (gold.get("activities") or [])]
    gt_cons = [c.get("text", "") for c in (gold.get("contacts")   or [])]
    gt_refs = [(r.get("reference_marker") or "").strip()
                for r in (gold.get("references") or [])]
    gt_refs = [x for x in gt_refs if x]

    # Gold cell set: (norm activity_text, norm contact_text) tuples from gold.soa
    gt_a_by_id = {a["id"]: _norm(a.get("text", "")) for a in (gold.get("activities") or [])}
    gt_c_by_id = {c["id"]: _norm(c.get("text", "")) for c in (gold.get("contacts") or [])}
    gt_cells = set()
    for c in (gold.get("soa") or []):
        at = gt_a_by_id.get(c.get("activity_id"))
        vt = gt_c_by_id.get(c.get("visit_id"))
        if at and vt: gt_cells.add((at, vt))

    p_acts = [a.get("text", "") for a in (pred.get("activities") or [])]
    p_cons = [c.get("text", "") for c in (pred.get("contacts")   or [])]
    p_refs = [(r.get("reference_marker") or "").strip()
                for r in (pred.get("references") or [])]
    p_refs = [x for x in p_refs if x]
    p_a_by_id = {a.get("id"): _norm(a.get("text", "")) for a in (pred.get("activities") or [])}
    p_c_by_id = {c.get("id"): _norm(c.get("text", "")) for c in (pred.get("contacts") or [])}
    p_cells = set()
    for c in (pred.get("cells") or []):
        at = p_a_by_id.get(c.get("activity_id"))
        vt = p_c_by_id.get(c.get("visit_id"))
        if at and vt: p_cells.add((at, vt))

    out = {}
    for axis, gs, ps in (("act", gt_acts, p_acts),
                          ("con", gt_cons, p_cons),
                          ("ref", gt_refs, p_refs)):
        tp, fp, fn, _ = _pair_fuzzy(gs, ps, threshold)
        out[axis] = (tp, fp, fn)

    # Cells: pair by concatenated owner tuple
    def _tup_str(t): return f"{t[0]}  |  {t[1]}"
    gt_str = [_tup_str(t) for t in gt_cells]
    p_str  = [_tup_str(t) for t in p_cells]
    tp, fp, fn, _ = _pair_fuzzy(gt_str, p_str, threshold)
    out["cell"] = (tp, fp, fn)
    return out


# ---------- Attachment scoring (owner-first, occurrence-level) ----------

def _collect_act_attach(items):
    out = []
    for a in (items or []):
        o = _norm(a.get("text", ""))
        if not o: continue
        m = [str(x).strip() for x in (a.get("uses_reference_markers") or []) if str(x).strip()]
        out.append((o, m))
    return out


def _collect_con_attach(items):
    out = []
    for c in (items or []):
        o = _norm(c.get("text", ""))
        if not o: continue
        m = [str(x).strip() for x in (c.get("reference_markers") or []) if str(x).strip()]
        out.append((o, m))
    return out


def _collect_cell_attach(cells, a_by_id, c_by_id):
    out = []
    for cell in (cells or []):
        at = a_by_id.get(cell.get("activity_id"))
        vt = c_by_id.get(cell.get("visit_id"))
        if not at or not vt: continue
        m = [str(x).strip() for x in (cell.get("cell_reference_markers") or []) if str(x).strip()]
        out.append(((at, vt), m))
    return out


def _attach_tpfpfn(gold_entries, pred_entries, threshold: float = 0.60):
    """Occurrence-level owner pairing + exact marker-string match within pair.
    Unmatched gold -> markers to FN. Unmatched pred -> markers DROPPED."""
    def _as_str(o): return o if isinstance(o, str) else "  |  ".join(o)
    g_strs = [_as_str(o) for o, _ in gold_entries]
    p_strs = [_as_str(o) for o, _ in pred_entries]

    mg, mp, matches = set(), set(), {}
    for i, g in enumerate(g_strs):
        for j, p in enumerate(p_strs):
            if j in mp: continue
            if g == p and g:
                mg.add(i); mp.add(j); matches[i] = j; break
    pairs = []
    for i, g in enumerate(g_strs):
        if i in mg: continue
        for j, p in enumerate(p_strs):
            if j in mp: continue
            r = SequenceMatcher(None, g, p).ratio()
            if r >= threshold:
                pairs.append((r, i, j))
    pairs.sort(reverse=True)
    for _, i, j in pairs:
        if i in mg or j in mp: continue
        mg.add(i); mp.add(j); matches[i] = j

    tp = fp = fn = 0
    for gi, pj in matches.items():
        gm = list(gold_entries[gi][1])
        pm = list(pred_entries[pj][1])
        gu = [False] * len(gm); pu = [False] * len(pm)
        for i, x in enumerate(gm):
            for j, y in enumerate(pm):
                if pu[j]: continue
                if x == y:
                    gu[i] = True; pu[j] = True
                    tp += 1
                    break
        fn += gu.count(False)
        fp += pu.count(False)
    for gi in range(len(g_strs)):
        if gi not in mg: fn += len(gold_entries[gi][1])
    return tp, fp, fn


def _score_group_attach(gold: dict, pred: dict, threshold: float):
    g_a_by_id = {a["id"]: _norm(a.get("text", "")) for a in (gold.get("activities") or [])}
    g_c_by_id = {c["id"]: _norm(c.get("text", "")) for c in (gold.get("contacts") or [])}
    p_a_by_id = {a.get("id"): _norm(a.get("text", "")) for a in (pred.get("activities") or [])}
    p_c_by_id = {c.get("id"): _norm(c.get("text", "")) for c in (pred.get("contacts") or [])}
    scopes = {}
    for name, g_coll, p_coll in (
        ("activity", _collect_act_attach(gold.get("activities")),
                     _collect_act_attach(pred.get("activities"))),
        ("contact",  _collect_con_attach(gold.get("contacts")),
                     _collect_con_attach(pred.get("contacts"))),
        ("cell",     _collect_cell_attach(gold.get("soa"), g_a_by_id, g_c_by_id),
                     _collect_cell_attach(pred.get("cells"), p_a_by_id, p_c_by_id)),
    ):
        scopes[name] = _attach_tpfpfn(g_coll, p_coll, threshold)
    return scopes


# ---------- Temporal scoring (optional sixth component, weight 0 by default) ----------

_T_UNITS = {"day": "days", "days": "days", "d": "days", "week": "weeks", "weeks": "weeks",
            "wk": "weeks", "month": "months", "months": "months", "year": "years",
            "years": "years", "hour": "hours", "hours": "hours"}


def _t_num(v):
    try: return round(float(v), 3)
    except (TypeError, ValueError): return None


def _t_value_unit(v, u):
    """(value, unit) with the unit normalised and weeks converted to days."""
    v = _t_num(v)
    if u is not None:
        u = str(u).lower().strip()
        u = _T_UNITS.get(u, u)
    if v is None: return None, u
    if u == "weeks": return v * 7, "days"
    return v, u


def _t_interval(c):
    return (c or {}).get("contact_interval_relative_from_anchor") or {}


def _temporal_target_raw(c):
    iv = _t_interval(c)
    v, u = _t_value_unit(iv.get("target"), iv.get("target_unit"))
    return None if v is None else (v, u)


def _temporal_target(c):
    t = _temporal_target_raw(c)
    if t is not None and t[0] == 0: return (t[0], None)      # 0 equals 0 in any unit
    return t


def _temporal_window(c):
    iv = _t_interval(c)
    b, u = _t_value_unit(iv.get("window_before"), iv.get("window_unit"))
    a, _ = _t_value_unit(iv.get("window_after"), iv.get("window_unit"))
    b = (abs(b) or None) if b is not None else None           # a side of 0 equals an empty side
    a = (abs(a) or None) if a is not None else None
    return None if b is None and a is None else (b, a, u)


def _temporal_span(c):
    """Allowed interval (earliest, latest, unit) when the window is in the target's unit."""
    t, w = _temporal_target_raw(c), _temporal_window(c)
    if t is None or w is None or t[1] != w[2]: return None
    return (t[0] - (w[0] or 0), t[0] + (w[1] or 0), t[1])


_TEMPORAL_FIELDS = (("target", _temporal_target), ("window", _temporal_window))


def _score_group_temporal(gold: dict, pred: dict, threshold: float) -> dict:
    """{'target': (tp, fp, fn), 'window': (tp, fp, fn)} over the contacts of one
    group, paired by the same call that scores the contacts component."""
    g_cons = gold.get("contacts") or []
    p_cons = pred.get("contacts") or []
    _, _, _, mapping = _pair_fuzzy([c.get("text", "") for c in g_cons],
                                   [c.get("text", "") for c in p_cons], threshold)
    cnt = {f: [0, 0, 0] for f, _ in _TEMPORAL_FIELDS}         # tp, n_pred, n_gold
    for gi, g in enumerate(g_cons):
        p = p_cons[mapping[gi]] if gi in mapping else None
        gs = _temporal_span(g)
        same_span = p is not None and gs is not None and gs == _temporal_span(p)
        for f, fn in _TEMPORAL_FIELDS:
            gv = fn(g)
            pv = fn(p) if p is not None else None
            if same_span and gv is not None: pv = gv
            cnt[f][0] += gv is not None and gv == pv
            cnt[f][1] += pv is not None
            cnt[f][2] += gv is not None
    matched_p = set(mapping.values())
    for pj, p in enumerate(p_cons):                           # unmatched predicted contacts:
        if pj in matched_p: continue                          # their values are spurious (FP)
        for f, fn in _TEMPORAL_FIELDS:
            cnt[f][1] += fn(p) is not None
    return {f: (tp, n_pred - tp, n_gold - tp) for f, (tp, n_pred, n_gold) in cnt.items()}


# ---------- Loading ----------

def load_gold(path: Path) -> dict:
    """Return {group_id: row}. If a group_id appears multiple times (append-only
    history) the row with the most 'soa' cells wins."""
    by = {}
    for line in path.open():
        if not line.strip(): continue
        r = json.loads(line)
        gid = r["group_id"]
        if gid not in by or len(r.get("soa") or []) > len(by[gid].get("soa") or []):
            by[gid] = r
    return by


def load_pred_dir(dirp: Path) -> dict:
    """Return {group_id: {activities, contacts, references, cells}} for all .json files."""
    by = {}
    for p in sorted(dirp.glob("*.json")):
        if p.name == "manifest.json": continue
        r = json.loads(p.read_text())
        gid = r.get("group_id") or p.stem
        by[gid] = r
    return by


# ---------- Scoring ----------

def f1(tp, fp, fn):
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else 0.0


def pr(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return p, r, f1(tp, fp, fn)


def score_system(label: str, pred_by_gid: dict, gold: dict, threshold: float = 0.60) -> dict:
    axis_tots = {k: [0, 0, 0] for k in ("act", "con", "ref", "cell")}
    atch_tots = [0, 0, 0]
    scope_tots = {s: [0, 0, 0] for s in ("activity", "contact", "cell")}
    temporal_field_tots = {f: [0, 0, 0] for f, _ in _TEMPORAL_FIELDS}
    per_group = []
    for gid, gt in gold.items():
        pred = pred_by_gid.get(gid) or {"activities": [], "contacts": [], "references": [], "cells": []}
        axes = _score_group_axes(gt, pred, threshold)
        atch = _score_group_attach(gt, pred, threshold)
        gp = {"group_id": gid}
        for ax in ("act", "con", "ref", "cell"):
            tp, fp, fn = axes[ax]
            axis_tots[ax][0] += tp; axis_tots[ax][1] += fp; axis_tots[ax][2] += fn
            gp[f"{ax}_tp"] = tp; gp[f"{ax}_fp"] = fp; gp[f"{ax}_fn"] = fn
        for sn, (stp, sfp, sfn) in atch.items():
            scope_tots[sn][0] += stp; scope_tots[sn][1] += sfp; scope_tots[sn][2] += sfn
            atch_tots[0] += stp; atch_tots[1] += sfp; atch_tots[2] += sfn
            gp[f"atch_{sn}_tp"] = stp; gp[f"atch_{sn}_fp"] = sfp; gp[f"atch_{sn}_fn"] = sfn
        for f, cnts in _score_group_temporal(gt, pred, threshold).items():
            for k in range(3): temporal_field_tots[f][k] += cnts[k]
        per_group.append(gp)
    axes_prf = {ax: pr(*axis_tots[ax]) for ax in axis_tots}
    atch_prf = pr(*atch_tots)
    scope_prf = {s: pr(*scope_tots[s]) for s in scope_tots}
    tp5 = sum(axis_tots[ax][0] for ax in axis_tots) + atch_tots[0]
    fp5 = sum(axis_tots[ax][1] for ax in axis_tots) + atch_tots[1]
    fn5 = sum(axis_tots[ax][2] for ax in axis_tots) + atch_tots[2]
    tp4 = sum(axis_tots[ax][0] for ax in axis_tots)
    fp4 = sum(axis_tots[ax][1] for ax in axis_tots)
    fn4 = sum(axis_tots[ax][2] for ax in axis_tots)
    return {
        "label": label, "axis_tots": axis_tots, "atch_tots": tuple(atch_tots),
        "scope_tots": scope_tots, "axes": axes_prf, "atch": atch_prf, "scopes": scope_prf,
        "soa4": f1(tp4, fp4, fn4), "soa5": f1(tp5, fp5, fn5),
        "per_group": per_group,
        "temporal_field_tots": temporal_field_tots,
        "temporal_tots": tuple(sum(t[k] for t in temporal_field_tots.values()) for k in range(3)),
    }


# ---------- Optional component weighting ----------

COMPONENTS = ("act", "con", "ref", "cell", "attach", "temporal")
DEFAULT_WEIGHTS = {"act": 1.0, "con": 1.0, "ref": 1.0, "cell": 1.0, "attach": 1.0,
                   "temporal": 0.0}   # temporal is opt-in; the published score has five components


def parse_weights(spec: str | None) -> dict:
    """'attach=5,cell=0.5' -> {'act': 1.0, ..., 'attach': 5.0, 'cell': 0.5, 'temporal': 0.0}."""
    w = dict(DEFAULT_WEIGHTS)
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, val = part.partition("=")
        name = name.strip()
        if name not in w:
            raise ValueError(f"unknown component {name!r}; choose from {', '.join(COMPONENTS)}")
        w[name] = float(val)
        if w[name] < 0:
            raise ValueError(f"weight for {name} must not be negative")
    return w


def weighted_soa(res: dict, weights: dict | None = None, normalize: bool = False) -> float:
    """Pooled F1 with each component's counts scaled by its weight and, with
    normalize, divided by its number of gold units. Defaults give res['soa5']."""
    weights = weights or DEFAULT_WEIGHTS
    tots = dict(res["axis_tots"]); tots["attach"] = res["atch_tots"]
    tots["temporal"] = res["temporal_tots"]
    tp = fp = fn = 0.0
    for c in COMPONENTS:
        ctp, cfp, cfn = tots[c]
        k = weights.get(c, DEFAULT_WEIGHTS[c])
        if not k:
            continue
        if normalize:
            n_gold = ctp + cfn
            if not n_gold:
                continue
            k = k / n_gold
        tp += k * ctp; fp += k * cfp; fn += k * cfn
    return f1(tp, fp, fn)


# ---------- Validation ----------

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent

VALIDATE_SYSTEMS = {
    # Attachment TP/FP/FN that this scorer reproduces exactly for Claude and
    # Gemini; Qwen and GPT differ by 1 unit each (see docstring).
    "gemini_38_flash":                    (81, 12, 22, 0.9432),
    "claude_sonnet_55":                   (94,  8,  9, 0.8746),
    "medical_llm_medium_schema_constrained": None,  # no published target
    "medical_llm_medium_unconstrained":   None,
    "gpt_56_terra":                       (72, 26, 31, 0.9345),  # under this scorer (not pub 71/27/32)
}


def _print_summary(res):
    print(f"=== {res['label']} ===")
    for ax, (p, r, f) in res["axes"].items():
        tp, fp, fn = res["axis_tots"][ax]
        print(f"  {ax:>8} : p={p:.3f} r={r:.3f} f1={f:.3f}  (tp={tp}/fp={fp}/fn={fn})")
    (p, r, f) = res["atch"]; (atp, afp, afn) = res["atch_tots"]
    print(f"  attach   : p={p:.3f} r={r:.3f} f1={f:.3f}  (tp={atp}/fp={afp}/fn={afn})")
    for s, (p, r, f) in res["scopes"].items():
        tp, fp, fn = res["scope_tots"][s]
        print(f"    attach-{s:<8}: f1={f:.3f}  (tp={tp}/fp={fp}/fn={fn})")
    print(f"  SoA-4 pooled : {res['soa4']:.4f}")
    print(f"  SoA-5 pooled : {res['soa5']:.4f}")


def _print_temporal(res):
    tp, fp, fn = res["temporal_tots"]; p, r, f = pr(tp, fp, fn)
    print(f"  temporal : p={p:.3f} r={r:.3f} f1={f:.3f}  (tp={tp}/fp={fp}/fn={fn})")
    for name, (tp, fp, fn) in res["temporal_field_tots"].items():
        p, r, f = pr(tp, fp, fn)
        print(f"    temporal-{name:<6}: p={p:.3f} r={r:.3f} f1={f:.3f}  (tp={tp}/fp={fp}/fn={fn})")


def validate(gold_path: Path, pred_root: Path, threshold: float = 0.60):
    gold = load_gold(gold_path)
    all_ok = True
    for sys_name, target in VALIDATE_SYSTEMS.items():
        d = pred_root / sys_name
        if not d.exists():
            print(f"  SKIP {sys_name}: {d} missing"); continue
        preds = load_pred_dir(d)
        res = score_system(sys_name, preds, gold, threshold)
        _print_summary(res)
        if target is not None:
            etp, efp, efn, esoa5 = target
            atp, afp, afn = res["atch_tots"]
            ok = (atp, afp, afn) == (etp, efp, efn) and abs(res["soa5"] - esoa5) < 1e-3
            flag = "OK" if ok else "DIFF"
            print(f"  [{flag}] attach ({atp},{afp},{afn}) vs {target[:3]}  SoA-5 {res['soa5']:.4f} vs {esoa5}")
            if not ok: all_ok = False
    print("\n" + ("ALL MATCH" if all_ok else "DRIFT present (see docstring)"))
    return 0 if all_ok else 1


# ---------- CLI ----------

def _write_csv(res, out_path: Path):
    axis = res["axis_tots"]; scope = res["scope_tots"]
    row = {
        "system": res["label"],
        "act_f1":  res["axes"]["act"][2],  "con_f1":  res["axes"]["con"][2],
        "ref_f1":  res["axes"]["ref"][2],  "cell_f1": res["axes"]["cell"][2],
        "atch_f1": res["atch"][2],
        "atch_activity_f1": res["scopes"]["activity"][2],
        "atch_contact_f1":  res["scopes"]["contact"][2],
        "atch_cell_f1":     res["scopes"]["cell"][2],
        "soa4": res["soa4"], "soa5": res["soa5"],
        "atch_tp": res["atch_tots"][0], "atch_fp": res["atch_tots"][1], "atch_fn": res["atch_tots"][2],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader(); w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="SoA 5-component pooled F1 scorer.")
    ap.add_argument("--validate", action="store_true",
                    help="Score every system in predictions/ and print.")
    ap.add_argument("--gold", type=Path, default=RELEASE / "gold" / "soa_gold.jsonl")
    ap.add_argument("--pred", type=Path, default=None,
                    help="Dir of per-group .json files for one system.")
    ap.add_argument("--pred-root", type=Path, default=RELEASE / "predictions",
                    help="Root dir holding one subdir per system (for --validate).")
    ap.add_argument("--threshold", type=float, default=0.60)
    ap.add_argument("--out", type=Path, default=None,
                    help="Write a single-row CSV with the summary scores.")
    ap.add_argument("--weights", default=None, metavar="c=w,...",
                    help="Per-component weights, e.g. attach=5,cell=1 (components: "
                         "act, con, ref, cell, attach; default 1 each; and the optional "
                         "temporal, default 0). Adds a weighted score line, plus the "
                         "temporal P/R/F1 when temporal > 0; the published SoA-5 score "
                         "is unchanged.")
    ap.add_argument("--normalize", action="store_true",
                    help="Divide each component's counts by its number of gold units "
                         "before pooling, so every component counts equally.")
    args = ap.parse_args()

    if args.validate:
        return validate(args.gold, args.pred_root, args.threshold)

    if not args.pred:
        print("Pass --validate or --pred <dir>", file=sys.stderr); return 2

    gold = load_gold(args.gold)
    preds = load_pred_dir(args.pred)
    res = score_system(args.pred.name, preds, gold, args.threshold)
    _print_summary(res)
    if args.weights or args.normalize:
        try:
            w = parse_weights(args.weights)
        except ValueError as e:
            print(f"--weights: {e}", file=sys.stderr); return 2
        temporal_on = w["temporal"] > 0
        if temporal_on:
            _print_temporal(res)
        desc = ", ".join(f"{c}={w[c]:g}" for c in COMPONENTS if c != "temporal" or temporal_on)
        print(f"  SoA-{6 if temporal_on else 5} weighted ({desc}{'; normalised' if args.normalize else ''}) : "
              f"{weighted_soa(res, w, args.normalize):.4f}")
    if args.out:
        _write_csv(res, args.out)
        print(f"\nwrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
