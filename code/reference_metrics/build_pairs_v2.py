"""Pairs for the replacement Tables 4 and 5 (reference TEDS / GriTS). Read-only on the project.
usage: build_pairs_v2.py <bundle_root> <out_json>

Table 4: gold vs each system's prediction, rendered with the shipped flat renderer.
Table 5 rows (perturbed gold vs gold):
  identity
  delete_one_cell      one cell per schedule: the first cell in gold file order (6 cells in total)
  delete_10pct         69 of the 690 cells, random.Random(1337).sample over the list of
                       (group, cell index) in gold file order
  clear_marker_fields  structured marker fields emptied, text untouched
  strip_shipped        the shipped strip_token (removes every standalone occurrence of a marker string)
  strip_exact          removes only the marker itself: where a marker string occurs twice in a
                       label, the occurrence listed in MARKER_OCCURRENCE is removed (five labels)
The cell-deletion rows are a re-creation: the original script for them was not found."""
import sys, json, copy, re, random, importlib.util
sys.dont_write_bytecode = True
ROOT, OUT = sys.argv[1], sys.argv[2]
R = ROOT
spec = importlib.util.spec_from_file_location('metrics_shipped', R + '/code/metrics_teds_grits.py')
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)

gold = {}
for l in open(R + '/gold/soa_gold.jsonl'):
    if l.strip():
        d = json.loads(l)
        if d['group_id'] not in gold or len(d.get('soa') or []) > len(gold[d['group_id']].get('soa') or []):
            gold[d['group_id']] = d
assert len(gold) == 6 and sum(len(d['soa']) for d in gold.values()) == 690
html_of = lambda d: B.render_table_html(d['activities'], d['contacts'], d['soa'])
pairs = []

SY = ['medical_llm_medium_schema_constrained', 'gpt_56_terra', 'gemini_38_flash', 'claude_sonnet_55']
for s in SY:
    for gid, g in gold.items():
        p = json.load(open(f'{R}/predictions/{s}/{gid}.json'))
        acts = copy.deepcopy(p.get('activities') or []); cons = copy.deepcopy(p.get('contacts') or []); cells = p.get('cells') or []
        for i, a in enumerate(acts): a['_pred_id'] = a.get('id') or f'act_{i+1:02d}'
        for i, c in enumerate(cons): c['_pred_id'] = c.get('id') or f'con_{i+1:02d}'
        pairs.append({'set': 'table4', 'system': s, 'gid': gid, 'gold': html_of(g),
                      'pred': B.render_table_html(acts, cons, cells, act_id_key='_pred_id', con_id_key='_pred_id'),
                      'shape_gold': [len(g['activities']) + 1, len(g['contacts']) + 1], 'shape_pred': [len(acts) + 1, len(cons) + 1]})

src = open(R + '/code/run_perturbation.py').read()
ns = {}
exec('import re,copy\n' + src[src.index('def strip_token'):src.index('def html_of')], ns)
perturb_shipped, tidy_src = ns['perturb'], ns['strip_token']

# (label text prefix, marker) -> index of the standalone occurrence that IS the marker
MARKER_OCCURRENCE = {
    ('Visit No.: 11 13 > Year 5 > Mo. 60 11', '11'): 1,
    ('Visit No.: 7 > Year 3 > Mo. 36 7', '7'): 1,
    ('Period/Phase: Screening Period a,b,c,d', 'a'): 0,
    ('Trial Periods: Screening 1 > Visit number: 1', '1'): 0,
    ('Trial Periods: End-of-trial – premature discontinuation 3', '3'): 0,
}


def strip_exact(text, marks):
    t = text
    for m in sorted({str(x) for x in marks}, key=len, reverse=True):
        if not m: continue
        pat = r'(?<![A-Za-z0-9])' + re.escape(m) + r'(?![A-Za-z0-9])'
        occ = [x.span() for x in re.finditer(pat, t)]
        if len(occ) > 1:
            key = next((k for k in MARKER_OCCURRENCE if text.startswith(k[0]) and k[1] == m), None)
            assert key, (text, m)
            occ = [occ[MARKER_OCCURRENCE[key]]]
        for a, b in reversed(occ):
            t = t[:a] + t[b:]
    t = re.sub(r'\s*,\s*(?=,)', '', t); t = re.sub(r'\s*,\s*(?=$|>)', '', t)
    t = re.sub(r'\s{2,}', ' ', t); t = re.sub(r'\s+([,/])', r'\1', t)
    return t.strip().strip(',').strip()


def perturb_exact(d):
    g = copy.deepcopy(d)
    for a in g['activities']:
        mk = a.get('uses_reference_markers') or []
        if mk: a['text'] = strip_exact(a.get('text', ''), mk)
        a['uses_reference_markers'] = []
    for c in g['contacts']:
        mk = c.get('reference_markers') or []
        if mk: c['text'] = strip_exact(c.get('text', ''), mk)
        c['reference_markers'] = []
    for cell in g['soa']:
        mk = cell.get('cell_reference_markers') or []
        if mk: cell['cell_content'] = strip_exact(cell.get('cell_content', ''), mk)
        cell['cell_reference_markers'] = []
    return g


allcells = [(gid, i) for gid, d in gold.items() for i in range(len(d['soa']))]
ten = set(random.Random(1337).sample(allcells, 69))
one = {(gid, 0) for gid in gold}


def drop(d, gid, which):
    g = copy.deepcopy(d); g['soa'] = [c for i, c in enumerate(g['soa']) if (gid, i) not in which]; return g


meta = {}
for label, fn in (('identity', lambda d, gid: copy.deepcopy(d)),
                  ('delete_one_cell', lambda d, gid: drop(d, gid, one)),
                  ('delete_10pct', lambda d, gid: drop(d, gid, ten)),
                  ('clear_marker_fields', lambda d, gid: perturb_shipped(d, False)),
                  ('strip_shipped', lambda d, gid: perturb_shipped(d, True)),
                  ('strip_exact', lambda d, gid: perturb_exact(d))):
    chars = changed = 0
    for gid, d in gold.items():
        p = fn(d, gid); h0, h1 = html_of(d), html_of(p)
        chars += sum(len(u.get('text', '')) for u in d['activities'] + d['contacts']) - sum(len(u.get('text', '')) for u in p['activities'] + p['contacts'])
        changed += h0 != h1
        pairs.append({'set': 'table5', 'system': label, 'gid': gid, 'gold': h0, 'pred': h1,
                      'shape_gold': [len(d['activities']) + 1, len(d['contacts']) + 1], 'shape_pred': [len(p['activities']) + 1, len(p['contacts']) + 1]})
    meta[label] = {'groups_changed': changed, 'label_chars_removed': chars}
# SoA score of the deletion rows, analytically: deleted cells and the attachments on them become misses
for label, which in (('delete_one_cell', one), ('delete_10pct', ten)):
    k = len(which); a = sum(len(gold[g]['soa'][i].get('cell_reference_markers') or []) for g, i in which)
    tp = 1104 - k - a; meta[label].update(cells_deleted=k, attachments_lost=a, soa=2 * tp / (2 * tp + k + a),
                                          groups_touched=len({g for g, _ in which}))
json.dump({'pairs': pairs, 'meta': meta}, open(OUT, 'w'))
print(json.dumps(meta, indent=1))
