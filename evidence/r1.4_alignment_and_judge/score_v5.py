"""Score the two-flag judge run (judge_runs_v5) against the human reference.

Reference per aligned header pair:
  content  = the two strings differ after whitespace collapsing (string rule)
  semantic = the adjudicated answer if the pair was on the adjudication page,
             else False (pairs nobody flagged, and format-only / dropped-marker pairs)
Without --adjudication the page's SUGGESTED answers are used (provisional).

usage: python3 score_v5.py [--adjudication path/to/adjudication.json] [--runs judge_runs_v5]
"""
import json, glob, argparse, itertools, collections, re

ap = argparse.ArgumentParser()
ap.add_argument('--adjudication'); ap.add_argument('--runs', default='judge_runs_v5')
a = ap.parse_args()
T = {t['task_id']: t for t in json.load(open('tasks.json'))['tasks']}
KEY = json.load(open('tasks_key.json'))['task_system']
NAME = {'gemini_38_flash': 'Gemini-3.8-Flash', 'gpt_56_terra': 'GPT-5.6-terra', 'claude_sonnet_55': 'Claude-Sonnet-5.5',
        'medical_llm_medium_schema_constrained': 'Medical LLM Medium'}
H = json.load(open('human/human_alignment.json'))
ITEMS = json.load(open('adjudicate_items.json'))
J = {f.split('/')[1].split('__')[1]: json.load(open(f)) for f in sorted(glob.glob(f'{a.runs}/*/alignments.json'))}
txt = lambda tid, side, i: next(x['text'] for x in T[tid][side] if x['id'] == i)
ws = lambda s: re.sub(r'\s+', ' ', s).strip()

align = {tid: dict(v) for tid, v in H['alignments'].items()}
sem = {i['id']: i['suggest']['semantic'] for i in ITEMS['content']}
if a.adjudication:
    A = json.load(open(a.adjudication))
    assert A['tasks_hash'] == ITEMS['tasks_hash']
    sem.update({k: v['semantic'] for k, v in A['content'].items()})
    jal = next(iter(J.values()))['alignments']
    for k, pick in A['alignment'].items():
        if pick == 'judge':
            tid, g = k.split('|'); align[tid][g] = jal[tid].get(g)
    print('reference: ADJUDICATED', a.adjudication)
else:
    print('reference: PROVISIONAL (page suggestions, not yet adjudicated)')


def kappa(x, y):
    n = len(x); po = sum(p == q for p, q in zip(x, y)) / n; pa, pb = sum(x) / n, sum(y) / n
    pe = pa * pb + (1 - pa) * (1 - pb); return (po - pe) / (1 - pe) if pe < 1 else 1.0


def prf(ref, pred):
    tp = sum(r and p for r, p in zip(ref, pred)); fp = sum(p and not r for r, p in zip(ref, pred)); fn = sum(r and not p for r, p in zip(ref, pred))
    P = tp / (tp + fp) if tp + fp else 0; R = tp / (tp + fn) if tp + fn else 0
    return tp, fp, fn, P, R, 2 * P * R / (P + R) if P + R else 0


print('\n== coverage / cost')
for n, j in J.items():
    cost = sum((i.get('usage') or {}).get('cost', 0) for i in j['info'].values())
    prob = sum(bool(i.get('problems')) for i in j['info'].values())
    print(f' {n}: {len(j["alignments"])}/48 tasks, {prob} with recorded problems, ${cost:.2f}')

print('\n== alignment vs human (all gold labels / non-prefilled)')
tot = [(tid, g) for tid in T for g in align[tid]]
npf = [(tid, g) for tid, g in tot if g not in T[tid]['prefill']]
maj_al = {}
for tid, g in tot:
    c = collections.Counter(j['alignments'][tid].get(g) for j in J.values() if tid in j['alignments'])
    maj_al[(tid, g)] = c.most_common(1)[0][0] if c else None
for n, f in list((n, (lambda tid, g, j=j: j['alignments'].get(tid, {}).get(g))) for n, j in J.items()) + [('majority', lambda tid, g: maj_al[(tid, g)])]:
    print(f' {n}: {100*sum(f(*k)==align[k[0]][k[1]] for k in tot)/len(tot):.2f}% of {len(tot)}; '
          f'{100*sum(f(*k)==align[k[0]][k[1]] for k in npf)/len(npf):.2f}% of {len(npf)} ({sum(f(*k)!=align[k[0]][k[1]] for k in npf)} differ)')
for x, y in itertools.combinations(J, 2):
    print(f' {x} vs {y}: {100*sum(J[x]["alignments"][t].get(g)==J[y]["alignments"][t].get(g) for t, g in tot)/len(tot):.2f}%')

# pairs: human-aligned, and aligned identically by every judge, with valid flags
pairs = []
for tid, g in tot:
    p = align[tid][g]
    if not p: continue
    fl = [(j['flags'].get(tid) or {}).get(g) if j['alignments'].get(tid, {}).get(g) == p else None for j in J.values()]
    pairs.append((tid, g, p, fl))
full = [x for x in pairs if all(x[3])]
print(f'\n== content / semantic over {len(full)} of {len(pairs)} human-aligned pairs graded by all judges')
ref_c = [ws(txt(t, 'gold', g)) != ws(txt(t, 'pred', p)) for t, g, p, _ in full]
ref_s = [bool(sem.get(f'{t}|{g}', False)) for t, g, p, _ in full]
print(f' reference yes: content {sum(ref_c)}, semantic {sum(ref_s)}')
names = list(J)
for k, ref in (('content', ref_c), ('semantic', ref_s)):
    print(f' -- {k}')
    cols = {n: [x[3][i][k] for x in full] for i, n in enumerate(names)}
    cols['majority'] = [sum(f[k] for f in x[3]) >= 2 for x in full]
    for n, v in cols.items():
        tp, fp, fn, P, R, F = prf(ref, v)
        print(f'   {n:28} yes {sum(v):4}  acc {100*sum(p==q for p,q in zip(ref,v))/len(ref):.2f}%  kappa {kappa(ref,v):.2f}  P {P:.2f} R {R:.2f} F1 {F:.2f}  (TP {tp} FP {fp} FN {fn})')
    ks = [kappa(cols[x], cols[y]) for x, y in itertools.combinations(names, 2)]
    print(f'   inter-judge: all three agree {100*sum(len({f[k] for f in x[3]})==1 for x in full)/len(full):.1f}%, pairwise kappa {[round(z,2) for z in ks]}')

print('\n== semantic disagreements, majority vs reference')
for (t, g, p, fl), r in zip(full, ref_s):
    m = sum(f['semantic'] for f in fl) >= 2
    if m != r:
        why = next((J[n]['reasons'].get(t, {}).get(g) for n in names if J[n]['reasons'].get(t, {}).get(g)), '')
        print(f' ref {"YES" if r else "no "} judges {"".join("Y" if f["semantic"] else "-" for f in fl)} {T[t]["axis"][:3]} | {txt(t,"gold",g)[-70:]!r} | {txt(t,"pred",p)[-70:]!r} | {why}')

print('\n== per system (reference labels | judge majority), aligned pairs')
for axis in ('rows', 'columns'):
    print(f' {axis}:')
    for s, nm in NAME.items():
        idx = [i for i, x in enumerate(full) if KEY[x[0]] == s and T[x[0]]['axis'] == axis]
        gold_n = sum(len(T[t]['gold']) for t in T if KEY[t] == s and T[t]['axis'] == axis)
        al = sum(1 for x in pairs if KEY[x[0]] == s and T[x[0]]['axis'] == axis)
        mc = sum(sum(f['content'] for f in full[i][3]) >= 2 for i in idx); ms = sum(sum(f['semantic'] for f in full[i][3]) >= 2 for i in idx)
        print(f'   {nm:20} gold {gold_n:3} aligned {al:3} | content {sum(ref_c[i] for i in idx):3} semantic {sum(ref_s[i] for i in idx):3} | judges: content {mc:3} semantic {ms:3}')
