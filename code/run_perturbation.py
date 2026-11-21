"""Marker perturbation done properly: strip the marker characters from the serialised table."""
import json, re, sys, copy
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from metrics_teds_grits import render_table_html, compute_teds, compute_grits

G={}
for ln in open(_HERE.parent / "gold" / "soa_gold.jsonl"):
    if ln.strip():
        d=json.loads(ln)
        if d.get("soa"): G[d["group_id"]]=d

def strip_token(text, marks):
    """Remove each marker where it stands as its own token, then tidy separators."""
    t=text
    for m in sorted({str(x) for x in marks}, key=len, reverse=True):
        if not m: continue
        t=re.sub(r'(?<![A-Za-z0-9])'+re.escape(m)+r'(?![A-Za-z0-9])', '', t)
    t=re.sub(r'\s*,\s*(?=,)', '', t)          # collapse ", ,"
    t=re.sub(r'\s*,\s*(?=$|>)', '', t)        # trailing comma before end or separator
    t=re.sub(r'\s{2,}', ' ', t)
    t=re.sub(r'\s+([,/])', r'\1', t)
    return t.strip().strip(',').strip()

def perturb(d, strip_text):
    g=copy.deepcopy(d)
    for a in g["activities"]:
        mk=a.get("uses_reference_markers") or []
        if strip_text and mk: a["text"]=strip_token(a.get("text",""), mk)
        a["uses_reference_markers"]=[]
    for c in g["contacts"]:
        mk=c.get("reference_markers") or []
        if strip_text and mk: c["text"]=strip_token(c.get("text",""), mk)
        c["reference_markers"]=[]
    for cell in g["soa"]:
        mk=cell.get("cell_reference_markers") or []
        if strip_text and mk:
            cell["cell_content"]=strip_token(cell.get("cell_content",""), mk)
        cell["cell_reference_markers"]=[]
    return g

def html_of(d):
    return render_table_html(d["activities"], d["contacts"], d["soa"])

rows={}
for label, strip_text in (("identity (control)", None), ("clear_marker_fields", False), ("strip_markers_everywhere", True)):
    teds=[]; tedss=[]; gt=[]; gc=[]; gl=[]; changed=0; bytes_delta=0
    for gid,d in G.items():
        h0=html_of(d)
        p = copy.deepcopy(d) if strip_text is None else perturb(d, strip_text)
        h1=html_of(p)
        if h0!=h1: changed+=1
        bytes_delta+=abs(len(h0)-len(h1))
        teds.append(compute_teds(h0,h1)); tedss.append(compute_teds(h0,h1,struct_only=True))
        gr=compute_grits(d, {"activities":p["activities"],"visits":p["contacts"],"cells":p["soa"]})
        gt.append(gr.get("grits_top",0)); gc.append(gr.get("grits_con",0)); gl.append(gr.get("grits_loc",0))
    m=lambda v: sum(v)/len(v)
    rows[label]=(m(teds),m(tedss),m(gt),m(gc),m(gl),changed,bytes_delta)
    print(f"{label:26s} TEDS={m(teds):.4f} TEDS-S={m(tedss):.4f} GriTS-Top={m(gt):.4f} "
          f"GriTS-Con={m(gc):.4f} GriTS-Loc={m(gl):.4f}  groups whose HTML changed: {changed}/6  "
          f"chars removed: {bytes_delta}")
print()
print("per group, strip_markers_everywhere:")
for gid,d in G.items():
    h0=html_of(d); h1=html_of(perturb(d, True))
    print(f"   {gid[:34]:36s} TEDS={compute_teds(h0,h1):.4f}  chars removed={len(h0)-len(h1):4d}")
