"""usage: summarise.py <results_json> <bundle_root>"""
import sys, json, copy, importlib.util
sys.dont_write_bytecode = True
res = json.load(open(sys.argv[1])); ROOT = sys.argv[2]
R = ROOT
spec = importlib.util.spec_from_file_location('m', R + '/code/metrics_teds_grits.py')
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
gold = {}
for l in open(R + '/gold/soa_gold.jsonl'):
    if l.strip():
        d = json.loads(l)
        if d['group_id'] not in gold or len(d.get('soa') or []) > len(gold[d['group_id']].get('soa') or []):
            gold[d['group_id']] = d
# our GriTS (cheap, from JSON), exactly as a2.py
for r in res:
    if r['set'] == 'table4':
        p = json.load(open(f"{R}/predictions/{r['system']}/{r['gid']}.json"))
        gr = B.compute_grits(gold[r['gid']], {'activities': copy.deepcopy(p.get('activities') or []),
                                              'visits': copy.deepcopy(p.get('contacts') or []),
                                              'cells': p.get('cells') or []})
        r['our_top'], r['our_con'] = gr['grits_top'], gr['grits_con']
cols = [('oT.ship', lambda r: r['ours']['teds_shipped']), ('oT.fix', lambda r: r['ours']['teds_fixed']),
        ('rT.th', lambda r: r['teds_th']), ('rT.td', lambda r: r['teds_td']),
        ('oTS', lambda r: r['ours']['tedss']), ('rTS.th', lambda r: r['tedss_th']), ('rTS.td', lambda r: r['tedss_td']),
        ('oGTop', lambda r: r.get('our_top', float('nan'))), ('rGTop', lambda r: r['grits']['grits_top']),
        ('oGCon', lambda r: r.get('our_con', float('nan'))), ('rGCon', lambda r: r['grits']['grits_con']),
        ('rTop.ub', lambda r: r['grits']['grits_top_upper_bound']), ('rCon.ub', lambda r: r['grits']['grits_con_upper_bound'])]
print(' ' * 30 + ' '.join(f'{c:>8s}' for c, _ in cols))
means = {}
for key in dict.fromkeys((r['set'], r['system']) for r in res):
    rows = [r for r in res if (r['set'], r['system']) == key]
    assert len(rows) == 6
    print(key[0], key[1])
    for r in rows:
        print(f"   {r['gid'][:26]:27s}" + ' '.join(f'{f(r):8.4f}' for _, f in cols), r['shape_gold'], r['shape_pred'])
    means[key] = [sum(f(r) for r in rows) / 6 for _, f in cols]
    print(f"   {'MEAN':27s}" + ' '.join(f'{x:8.4f}' for x in means[key]))
print('\nOrder of systems per metric (best first) and range, table4:')
t4 = {k[1]: v for k, v in means.items() if k[0] == 'table4'}
for j, (c, _) in enumerate(cols):
    o = sorted(t4, key=lambda s: -t4[s][j])
    vals = [t4[s][j] for s in t4]
    print(f'{c:8s} range {min(vals):.4f}-{max(vals):.4f} (width {max(vals)-min(vals):.4f})  ' + ' > '.join(f'{s[:10]}({t4[s][j]:.4f})' for s in o))
