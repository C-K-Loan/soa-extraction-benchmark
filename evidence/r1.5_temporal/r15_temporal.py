"""R1.5 probe: score the temporal fields of contacts on the hand-labelled column
alignment (read-only input from evidence/r1.4_alignment_and_judge). No model calls.

Fields:  TARGET = (target, target_unit), weeks converted to days
         WINDOW = (window_before, window_after, window_unit), weeks converted to days
         ANCHOR = anchor string, lowercased, non-alphanumerics collapsed
         CONDITION = present / absent only (free text)
Per field: TP gold and prediction both filled and equal; a wrong value is one FP and one FN;
gold filled / prediction empty (or contact not aligned) = FN; gold empty / prediction filled = FP.
"""
import json, re, sys, collections
from pathlib import Path
R = Path(__file__).resolve().parents[2]; JD = R / 'evidence/r1.4_alignment_and_judge'
T = json.load(open(JD / 'tasks.json'))['tasks']; KEY = json.load(open(JD / 'tasks_key.json'))['task_system']
H = json.load(open(JD / 'human/human_alignment.json'))['alignments']
GOLD = {g['group_id']: g for g in map(json.loads, open(R / 'gold/soa_gold.jsonl'))}
ARGS = [a for a in sys.argv[1:] if a.startswith('--')]; sys.argv = [a for a in sys.argv if not a.startswith('--')]
PATCHED = False; ZERO_EMPTY = '--zero-is-empty' in ARGS; RULES = '--agreed-rules' in ARGS
ZERO_EMPTY = ZERO_EMPTY or RULES
print('gold:', 'PATCHED (NCT01667081 footnote window)' if PATCHED else 'as released', '| window side 0 == empty:', ZERO_EMPTY)
NAME = {'gemini_38_flash': 'Gemini-3.8-Flash', 'gpt_56_terra': 'GPT-5.6-terra', 'claude_sonnet_55': 'Claude-Sonnet-5.5',
        'medical_llm_medium_schema_constrained': 'Medical LLM Medium'}
U = {'day': 'days', 'days': 'days', 'd': 'days', 'week': 'weeks', 'weeks': 'weeks', 'wk': 'weeks', 'month': 'months', 'months': 'months',
     'year': 'years', 'years': 'years', 'hour': 'hours', 'hours': 'hours'}
def num(v):
    try: return round(float(v), 3)
    except (TypeError, ValueError): return None
def vu(v, u):
    v = num(v); u = U.get(str(u).lower().strip(), str(u).lower().strip()) if u is not None else None
    if v is None: return None, u
    if u == 'weeks': return v * 7, 'days'
    return v, u
def target(c):
    iv = c.get('contact_interval_relative_from_anchor') or {}
    v, u = vu(iv.get('target'), iv.get('target_unit'))
    if v == 0 and RULES: u = None          # "0" equals "0 days"
    return None if v is None else (v, u)
def window(c):
    iv = c.get('contact_interval_relative_from_anchor') or {}
    b, u = vu(iv.get('window_before'), iv.get('window_unit')); a, _ = vu(iv.get('window_after'), iv.get('window_unit'))
    b = abs(b) if b is not None else None; a = abs(a) if a is not None else None
    if ZERO_EMPTY: b = b or None; a = a or None
    return None if b is None and a is None else (b, a, u)
def span(c):
    """Allowed interval (earliest, latest, unit) when the window is in the target's unit."""
    t, w = target_raw(c), window(c)
    if t is None or w is None or t[1] != w[2]: return None
    return (t[0] - (w[0] or 0), t[0] + (w[1] or 0), t[1])
def target_raw(c):
    iv = c.get('contact_interval_relative_from_anchor') or {}
    v, u = vu(iv.get('target'), iv.get('target_unit')); return None if v is None else (v, u)
def anchor(c):
    s = re.sub(r'[^a-z0-9]+', ' ', (c.get('anchor') or '').lower()).strip(); return s or None
def cond(c): return True if (c.get('condition') or '').strip() else None
FIELDS = {'TARGET': target, 'WINDOW': window, 'ANCHOR': anchor, 'CONDITION': cond}
raw = lambda c: {k: v for k, v in (c.get('contact_interval_relative_from_anchor') or {}).items() if v is not None}

stats = {s: {f: collections.Counter() for f in FIELDS} for s in NAME}; ex = collections.defaultdict(list)
for t in T:
    if t['axis'] != 'columns' or KEY[t['task_id']] not in NAME: continue
    s = KEY[t['task_id']]; gid = t['group_id']
    G = {c['id']: c for c in GOLD[gid]['contacts']}
    P = {c['id']: c for c in json.load(open(R / 'predictions' / s / f'{gid}.json'))['contacts']}
    al = H[t['task_id']]; used = set()
    for g, c in G.items():
        p = P.get(al.get(g)) if al.get(g) else None
        if p is not None: used.add(al[g])
        same_span = RULES and p is not None and span(c) is not None and span(c) == span(p)
        for f, fn in FIELDS.items():
            gv, pv = fn(c), (fn(p) if p is not None else None); st = stats[s][f]
            if same_span and f in ('TARGET', 'WINDOW') and gv is not None: pv = gv
            st['gold'] += gv is not None; st['pred'] += pv is not None
            if gv is not None and gv == pv: st['tp'] += 1; kind = 'ok'
            elif gv is None and pv is None: kind = None
            else:
                kind = 'wrong' if gv is not None and pv is not None else 'missed' if gv is not None else 'extra'
            if kind and kind != 'ok':
                ex[(s, f, kind)].append((gid.split('__')[0], c['text'], p['text'] if p else None,
                                         c.get('anchor') if f == 'ANCHOR' else c.get('condition') if f == 'CONDITION' else raw(c),
                                         (p.get('anchor') if f == 'ANCHOR' else p.get('condition') if f == 'CONDITION' else raw(p)) if p else None))
    for pid, p in P.items():
        if pid not in used:
            for f, fn in FIELDS.items(): stats[s][f]['pred'] += fn(p) is not None

print(f'{"system":20} ' + ' '.join(f'| {f:>9} P / R / F1 (gold n)  ' for f in FIELDS))
for s, nm in NAME.items():
    row = f'{nm:20} '
    for f in FIELDS:
        st = stats[s][f]; P_ = st['tp'] / st['pred'] if st['pred'] else 0; R_ = st['tp'] / st['gold'] if st['gold'] else 0
        row += f'| {100*P_:5.1f} / {100*R_:5.1f} / {100*(2*P_*R_/(P_+R_) if P_+R_ else 0):5.1f} ({st["gold"]:2}) pred {st["pred"]:2} '
    print(row)
def pooled(s, fields):
    tp = sum(stats[s][f]['tp'] for f in fields); pr = sum(stats[s][f]['pred'] for f in fields); go = sum(stats[s][f]['gold'] for f in fields)
    P_, R_ = tp / pr, tp / go; return f'{100*P_:5.1f} / {100*R_:5.1f} / {100*2*P_*R_/(P_+R_):5.1f} (gold {go})'
print('\npooled micro P / R / F1 over temporal units:')
for s, nm in NAME.items():
    print(f' {nm:20} target+window: {pooled(s, ("TARGET", "WINDOW"))}   all four fields: {pooled(s, tuple(FIELDS))}')
print('\nerror kinds per system and field (wrong / missed / extra):')
for s, nm in NAME.items():
    print(f' {nm:20} ' + '  '.join(f'{f}: {len(ex[(s,f,"wrong")])}/{len(ex[(s,f,"missed")])}/{len(ex[(s,f,"extra")])}' for f in FIELDS))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
for f in ('TARGET', 'WINDOW', 'ANCHOR'):
    for kind in ('wrong', 'missed', 'extra'):
        print(f'\n===== {f} {kind} =====')
        for s, nm in NAME.items():
            for e in ex[(s, f, kind)][:n]:
                print(f' [{nm}] {e[0]}\n    gold header: {e[1][-95:]}\n    pred header: {(e[2] or "(not aligned)")[-95:]}\n    gold {f}: {e[3]}\n    pred {f}: {e[4]}')
