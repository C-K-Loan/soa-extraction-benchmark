"""SoA score (pooled micro-F1 over the 5 components) under the adjudicated human alignment.
Activities / contacts: a gold unit is recovered when the human aligned a predicted unit to it.
Cells: both axes must be aligned. Reference definitions and marker attachments: published
counts unchanged (release/results), since the alignment does not cover them.
Variant 'sem': an aligned row/column with an adjudicated semantic error does not count as recovered."""
import json, glob, sys, csv, collections
sys.path.insert(0, '../../code'); import score_soa as S
from pathlib import Path
R = Path('../..'); gold = S.load_gold(R / 'gold/soa_gold.jsonl')
T = json.load(open('tasks.json'))['tasks']; KEY = json.load(open('tasks_key.json'))['task_system']
H = json.load(open('human/human_alignment.json'))['alignments']
A = json.load(open('human/adjudication.final.json'))
J = json.load(open(sorted(glob.glob('judge_runs_v5/*gemini*/alignments.json'))[0]))['alignments']
for k, pick in A['alignment'].items():
    if pick == 'judge':
        t, g = k.split('|'); H[t][g] = J[t].get(g)
SEM = {k for k, v in A['content'].items() if v['semantic']}
NAME = [('gemini_38_flash', 'Gemini-3.8-Flash'), ('gpt_56_terra', 'GPT-5.6-terra'), ('claude_sonnet_55', 'Claude-Sonnet-5.5'), ('medical_llm_medium_schema_constrained', 'Medical LLM Medium')]
pub = collections.defaultdict(lambda: collections.Counter())
for r in csv.DictReader(open(R / 'results/accuracy_per_group.csv')):
    for c in ('act', 'con', 'ref', 'cell'):
        for x in ('tp', 'fp', 'fn'): pub[r['system']][f'{c}_{x}'] += int(r[f'{c}_{x}'])
att = list(csv.DictReader(open(R / 'results/attachment_per_group.csv')))
ak = [k for k in att[0] if k.endswith(('tp', 'fp', 'fn'))]
for r in att:
    for k in ak: pub[r['system']]['atch_' + k.split('_')[-1]] += int(r[k])
F = lambda c: 100 * S.f1(*c)
print(f"{'':20}{'SoA pub':>8}{'SoA new':>8}{'SoA sem':>8} |{'act':>6}{'con':>6}{'cell':>6}{'ref':>6}{'atch':>6} | cell P/R")
for s, n in NAME:
    preds = S.load_pred_dir(R / 'predictions' / s)
    c = {v: [0, 0, 0] for v in ('act', 'con', 'cell', 'act_s', 'con_s')}
    for gid, gt in gold.items():
        tk = {t['axis']: t for t in T if t['group_id'] == gid and KEY[t['task_id']] == s}
        for ax, key in (('rows', 'act'), ('columns', 'con')):
            t = tk[ax]; m = H[t['task_id']]; al = [g for g, p in m.items() if p]
            bad = sum(f"{t['task_id']}|{g}" in SEM for g in al)
            c[key][0] += len(al); c[key][1] += len(t['pred']) - len(al); c[key][2] += len(t['gold']) - len(al)
            c[key + '_s'][0] += len(al) - bad; c[key + '_s'][1] += len(t['pred']) - len(al) + bad; c[key + '_s'][2] += len(t['gold']) - len(al) + bad
        p2a = {v: k for k, v in H[tk['rows']['task_id']].items() if v}; p2c = {v: k for k, v in H[tk['columns']['task_id']].items() if v}
        G = {(x['activity_id'], x['visit_id']) for x in gt['soa']}; P = set(); bad = 0
        for x in preds[gid].get('cells') or []:
            k = (p2a.get(x.get('activity_id')), p2c.get(x.get('visit_id')))
            if None in k or k in P: bad += 1
            else: P.add(k)
        c['cell'][0] += len(G & P); c['cell'][1] += len(P - G) + bad; c['cell'][2] += len(G - P)
    p = pub[s]; g3 = lambda k: [p[f'{k}_tp'], p[f'{k}_fp'], p[f'{k}_fn']]
    pool = lambda parts: F([sum(x[i] for x in parts) for i in range(3)])
    soa_pub = pool([g3(k) for k in ('act', 'con', 'cell', 'ref', 'atch')])
    soa_new = pool([c['act'], c['con'], c['cell'], g3('ref'), g3('atch')])
    soa_sem = pool([c['act_s'], c['con_s'], c['cell'], g3('ref'), g3('atch')])
    tp, fp, fn = c['cell']
    print(f"{n:20}{soa_pub:8.1f}{soa_new:8.1f}{soa_sem:8.1f} |{F(c['act']):6.1f}{F(c['con']):6.1f}{F(c['cell']):6.1f}{F(g3('ref')):6.1f}{F(g3('atch')):6.1f} | {100*tp/(tp+fp):.1f}/{100*tp/(tp+fn):.1f}   act_sem {F(c['act_s']):.1f} con_sem {F(c['con_s']):.1f}")
