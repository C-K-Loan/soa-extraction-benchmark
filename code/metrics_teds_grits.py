"""
TEDS + GRITS metrics for our Stage 4 ablations.

Renders (activities × contacts → cells) as an HTML table and computes:

- **TEDS** (Tree Edit Distance-based Similarity, PubTabNet)
  1.0 - ted(pred, gt) / max(nodes(pred), nodes(gt))
  where ted() is the classical Zhang-Shasha tree edit distance on the
  <table> DOM, with leaf-string cost = 1 - Levenshtein-like ratio.
- **TEDS-Struct** (structure-only): same as TEDS but leaf strings are
  ignored so only tag structure counts.
- **GRITS-Con** (content grid similarity, Microsoft TabRecSet): bipartite
  match predicted rows to GT rows on row-label text similarity, same
  for cols, then measure cell-content agreement over the matched grid.
- **GRITS-Top** (topology): fraction of GT (row, col) positions that are
  covered by the matched pred grid — measures how well the model
  reproduces the structural axes independent of content.
- **GRITS-Loc** (location): row+col header text agreement.

Everything is computable directly from the JSON we already emit
(4a activities, 4b contacts, 4d cells). The gold records have the same shape
under `activities` / `contacts` / `soa`.

Usage:
    python3 scripts/metrics_teds_grits.py --experiment ab003_prompt_tweaks \
        --repo-root . --out reports/metrics_ab003.csv

Row shape of the CSV:
    experiment, mode, group_id, teds, teds_struct, grits_con, grits_top, grits_loc
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path


try:
    from apted import APTED, Config  # type: ignore
    from apted.helpers import Tree   # type: ignore
    _HAVE_APTED = True
except ImportError:
    _HAVE_APTED = False


# ── shared utilities ──────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _sim(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _iter(p: Path):
    if not p.exists():
        return
    for line in p.open():
        if line.strip():
            yield json.loads(line)


# ── JSON → HTML renderer ──────────────────────────────────────────────────────

def render_table_html(activities: list, contacts: list, cells: list,
                       act_id_key: str = "id",
                       con_id_key: str = "id",
                       cell_act_key: str = "activity_id",
                       cell_con_key: str = "visit_id") -> str:
    """Render (activities × contacts → cells) as a single HTML <table>.

    Cells are looked up by (activity_id, visit_id). Missing cells render
    as empty <td>."""
    cell_by = {(c.get(cell_act_key), c.get(cell_con_key)):
                    (c.get("cell_content") or "").strip()
                for c in (cells or [])}
    out = ["<table>", "<thead><tr><th></th>"]
    for con in (contacts or []):
        out.append(f"<th>{html.escape(con.get('text', '').strip())}</th>")
    out.append("</tr></thead><tbody>")
    for act in (activities or []):
        out.append(f"<tr><td>{html.escape(act.get('text', '').strip())}</td>")
        for con in (contacts or []):
            v = cell_by.get((act.get(act_id_key), con.get(con_id_key)), "")
            out.append(f"<td>{html.escape(v)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ── GRITS on the JSON directly ───────────────────────────────────────────────

def _bipartite_match(gt_labels: list[str], pred_labels: list[str],
                       threshold: float = 0.60) -> dict[int, int]:
    """Greedy best-similarity matcher. Returns {pred_idx: gt_idx}."""
    if not gt_labels or not pred_labels:
        return {}
    pairs = []
    for pi, pl in enumerate(pred_labels):
        for gi, gl in enumerate(gt_labels):
            pairs.append((_sim(pl, gl), pi, gi))
    pairs.sort(reverse=True)
    used_p, used_g = set(), set()
    out = {}
    for ratio, pi, gi in pairs:
        if ratio < threshold:
            break
        if pi in used_p or gi in used_g:
            continue
        out[pi] = gi
        used_p.add(pi); used_g.add(gi)
    return out


def compute_grits(gt_row: dict, m_row: dict | None) -> dict:
    """GRITS-Con, GRITS-Top, GRITS-Loc per group.

    - Con: 2 * |matched cells with same content| / (|GT cells| + |pred cells|)
    - Top: 2 * |matched (row,col) positions| / (|GT positions| + |pred positions|)
    - Loc: geometric mean of header-similarity for matched rows and cols."""
    gt_acts = gt_row.get("activities") or []
    gt_cons = gt_row.get("contacts")   or []
    gt_cells = gt_row.get("soa")        or []
    m_row = m_row or {}
    m_acts = m_row.get("activities") or []
    m_cons = m_row.get("visits")     or []
    m_cells = m_row.get("cells")     or []

    # Attach synthetic sequential ids to model outputs (stage4a/4b don't
    # necessarily match GT id namespace but the stage4d cells reference
    # act_XX/con_XX indices built by stage4d_ml_schedule._with_ids). Here
    # we simply match on text.
    for i, a in enumerate(m_acts):
        a["_pred_id"] = f"act_{i+1:02d}"
    for i, c in enumerate(m_cons):
        c["_pred_id"] = f"con_{i+1:02d}"

    # bipartite match on labels
    act_map = _bipartite_match([a.get("text", "") for a in gt_acts],
                                [a.get("text", "") for a in m_acts])
    con_map = _bipartite_match([c.get("text", "") for c in gt_cons],
                                [c.get("text", "") for c in m_cons])

    # invert: predicted -> gt
    gt_acts_by_id = {a.get("id", f"act_{i+1:02d}"): i
                      for i, a in enumerate(gt_acts)}
    gt_cons_by_id = {c.get("id", f"con_{i+1:02d}"): i
                      for i, c in enumerate(gt_cons)}
    m_acts_by_id  = {m_acts[i]["_pred_id"]: i for i in range(len(m_acts))}
    m_cons_by_id  = {m_cons[i]["_pred_id"]: i for i in range(len(m_cons))}

    # Build GT and pred cell dicts keyed by *row_index, col_index* in each
    # side's own space.
    gt_cell_by_pos = {}
    for cell in gt_cells:
        ri = gt_acts_by_id.get(cell.get("activity_id"))
        ci = gt_cons_by_id.get(cell.get("visit_id"))
        if ri is None or ci is None:
            continue
        gt_cell_by_pos[(ri, ci)] = (cell.get("cell_content") or "").strip()

    m_cell_by_pos = {}
    for cell in m_cells:
        ri = m_acts_by_id.get(cell.get("activity_id"))
        ci = m_cons_by_id.get(cell.get("visit_id"))
        if ri is None or ci is None:
            continue
        m_cell_by_pos[(ri, ci)] = (cell.get("cell_content") or "").strip()

    # Now count cells that map to the SAME GT position
    m_at_gt_pos = {}
    for (pri, pci), content in m_cell_by_pos.items():
        gri = act_map.get(pri); gci = con_map.get(pci)
        if gri is None or gci is None:
            continue
        m_at_gt_pos[(gri, gci)] = content

    common = set(gt_cell_by_pos) & set(m_at_gt_pos)
    con_matches = sum(1 for k in common
                       if _sim(gt_cell_by_pos[k], m_at_gt_pos[k]) >= 0.90)
    denom_con = len(gt_cell_by_pos) + len(m_cell_by_pos)
    grits_con = (2 * con_matches / denom_con) if denom_con else 0.0

    top_denom = len(gt_cell_by_pos) + len(m_cell_by_pos)
    grits_top = (2 * len(common) / top_denom) if top_denom else 0.0

    # location: mean sim of matched row-header pairs × col-header pairs
    row_sims = [_sim(m_acts[pi].get("text", ""), gt_acts[gi].get("text", ""))
                 for pi, gi in act_map.items()]
    col_sims = [_sim(m_cons[pi].get("text", ""), gt_cons[gi].get("text", ""))
                 for pi, gi in con_map.items()]
    loc_row = sum(row_sims) / max(1, len(gt_acts))
    loc_col = sum(col_sims) / max(1, len(gt_cons))
    grits_loc = (loc_row * loc_col) ** 0.5

    return {
        "grits_con": grits_con,
        "grits_top": grits_top,
        "grits_loc": grits_loc,
        "n_gt_cells":   len(gt_cell_by_pos),
        "n_pred_cells": len(m_cell_by_pos),
        "n_common":     len(common),
        "n_row_matched": len(act_map),
        "n_col_matched": len(con_map),
    }


# ── TEDS via apted ────────────────────────────────────────────────────────────

def _html_to_apted_tree(html_str: str):
    """Turn our rendered HTML table into an apted bracketed tree.
    Tag = node label. Leaves are text nodes labelled `txt=<content>`.
    Format apted expects: `{label{child1}{child2}...}`

    Robust for OUR renderer's output (well-formed, no attributes).
    """
    import re as _re
    tag_re = _re.compile(r"</?([a-zA-Z0-9]+)>")

    # Token stream: ('open', tag) / ('close', tag) / ('text', txt)
    tokens = []
    i = 0
    while True:
        m = tag_re.search(html_str, i)
        if not m:
            break
        if m.start() > i:
            t = html_str[i:m.start()].strip()
            if t:
                tokens.append(("text", t))
        tag = m.group(1).lower()
        tokens.append(("close" if m.group(0).startswith("</") else "open", tag))
        i = m.end()

    def _safe(s: str) -> str:
        # apted parses {label{...}}; brackets in text nodes break it
        return s.replace("{", "(").replace("}", ")")

    # stack items: [label, children_list_of_strings]
    stack = [[None, []]]
    for kind, val in tokens:
        if kind == "open":
            stack.append([val, []])
        elif kind == "close":
            label, children = stack.pop()
            s = "{" + _safe(label) + "".join(children) + "}"
            stack[-1][1].append(s)
        elif kind == "text":
            stack[-1][1].append("{txt=" + _safe(val) + "}")

    return "".join(stack[0][1])


class _StrConfig(Config):  # type: ignore
    """apted config with leaf-string cost = 1 - similarity."""
    def rename(self, node1, node2):
        n1, n2 = node1.name, node2.name
        if n1 == n2:
            return 0
        # text leaves prefixed "txt#" — soft rename
        if n1.startswith("txt#") and n2.startswith("txt#"):
            a = n1[4:]; b = n2[4:]
            return 1 - _sim(a, b)
        return 1


def compute_teds(gt_html: str, pred_html: str, struct_only: bool = False) -> float:
    if not _HAVE_APTED:
        return float("nan")
    if struct_only:
        # drop all text nodes before parsing
        gt_html   = re.sub(r">([^<]+)<", "><", gt_html)
        pred_html = re.sub(r">([^<]+)<", "><", pred_html)
    gt_tree   = Tree.from_text(_html_to_apted_tree(gt_html))
    pred_tree = Tree.from_text(_html_to_apted_tree(pred_html))
    dist = APTED(gt_tree, pred_tree, _StrConfig()).compute_edit_distance()

    def _node_count(node):
        return 1 + sum(_node_count(c) for c in node.children)

    n = max(_node_count(gt_tree), _node_count(pred_tree))
    if n == 0:
        return 1.0
    return max(0.0, 1.0 - dist / n)


# ── driver ────────────────────────────────────────────────────────────────────

STAGE_FILES = {
    "4a_activities": "stage4a_ml_activities.jsonl",
    "4b_visits":     "stage4b_ml_visits.jsonl",
    "4c_references": "stage4c_ml_references.jsonl",
    "4d_cells":      "stage4d_ml_schedule.jsonl",
}


def load_pred(exp_mode_path: Path) -> dict[str, dict]:
    """Combine 4a + 4b + 4d rows per group_id into one dict shaped like
    a GT row (activities/contacts/soa keys)."""
    acts = {r["group_id"]: r for r in _iter(exp_mode_path / STAGE_FILES["4a_activities"])}
    vis  = {r["group_id"]: r for r in _iter(exp_mode_path / STAGE_FILES["4b_visits"])}
    cells = {r["group_id"]: r for r in _iter(exp_mode_path / STAGE_FILES["4d_cells"])}
    out = {}
    for gid in set(acts) | set(vis) | set(cells):
        a = acts.get(gid, {}); v = vis.get(gid, {}); c = cells.get(gid, {})
        out[gid] = {
            "group_id":    gid,
            "activities":  a.get("activities") or [],
            "visits":      v.get("visits")     or [],
            "cells":       c.get("cells")      or [],
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--registry", type=Path, default=None)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, required=True,
                    help="CSV output path.")
    args = ap.parse_args()

    reg_path = args.registry or (args.repo_root / "data" / "ablations.json")
    reg = json.loads(reg_path.read_text())
    exp = next((e for e in reg["experiments"] if e["id"] == args.experiment), None)
    if exp is None:
        sys.exit(f"experiment '{args.experiment}' not in {reg_path}")

    gt = {r["group_id"]: r for r in _iter(args.repo_root / exp["gt_source"])}

    rows = [["experiment", "mode", "group_id",
             "teds", "teds_struct",
             "grits_con", "grits_top", "grits_loc",
             "n_gt_cells", "n_pred_cells", "n_common"]]

    print(f"\n=== TEDS + GRITS · experiment={exp['id']} · N_groups={len(gt)} ===")
    print(f"apted available: {_HAVE_APTED}")

    for m in exp["modes"]:
        mode_path = args.repo_root / m["path"]
        pred = load_pred(mode_path)
        agg = {k: [] for k in ("teds", "teds_struct",
                                "grits_con", "grits_top", "grits_loc")}
        for gid in sorted(gt.keys()):
            g_row = gt[gid]
            p_row = pred.get(gid, {})
            # For the renderer we need id + text on both sides.
            gt_acts = g_row.get("activities") or []
            gt_cons = g_row.get("contacts")   or []
            gt_cells_ = g_row.get("soa")       or []
            m_acts = p_row.get("activities") or []
            m_cons = p_row.get("visits")     or []
            m_cells = p_row.get("cells")     or []
            # give synthetic ids where absent
            for i, a in enumerate(m_acts):
                a.setdefault("_pred_id", f"act_{i+1:02d}")
            for i, c in enumerate(m_cons):
                c.setdefault("_pred_id", f"con_{i+1:02d}")

            gt_html = render_table_html(gt_acts, gt_cons, gt_cells_,
                                          act_id_key="id", con_id_key="id",
                                          cell_act_key="activity_id",
                                          cell_con_key="visit_id")
            pred_html = render_table_html(m_acts, m_cons, m_cells,
                                            act_id_key="_pred_id",
                                            con_id_key="_pred_id",
                                            cell_act_key="activity_id",
                                            cell_con_key="visit_id")

            teds  = compute_teds(gt_html, pred_html, struct_only=False)
            tstr  = compute_teds(gt_html, pred_html, struct_only=True)
            grits = compute_grits(g_row, p_row)
            for k in ("teds", "teds_struct"):
                pass
            agg["teds"].append(teds); agg["teds_struct"].append(tstr)
            agg["grits_con"].append(grits["grits_con"])
            agg["grits_top"].append(grits["grits_top"])
            agg["grits_loc"].append(grits["grits_loc"])

            rows.append([exp["id"], m["id"], gid,
                          f"{teds:.3f}", f"{tstr:.3f}",
                          f"{grits['grits_con']:.3f}",
                          f"{grits['grits_top']:.3f}",
                          f"{grits['grits_loc']:.3f}",
                          grits["n_gt_cells"], grits["n_pred_cells"], grits["n_common"]])

        def _mean(xs):
            xs = [x for x in xs if x == x]  # drop nan
            return sum(xs) / max(1, len(xs))

        print(f"\n  {m['id']:24s}", end="")
        for k in ("teds", "teds_struct", "grits_con", "grits_top", "grits_loc"):
            print(f"  {k}={_mean(agg[k]):.3f}", end="")
        print()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)
    print(f"\n[csv] {args.out}")


if __name__ == "__main__":
    main()
