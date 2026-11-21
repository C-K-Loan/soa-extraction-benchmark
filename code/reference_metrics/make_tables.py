#!/usr/bin/env python3
"""Write results/teds_grits_table4.csv and results/perturbation_table.csv (Tables 4 and 5 of the
paper) from the stored reference-implementation run, results_v2.json. No model calls and no
third-party code: this only averages stored per-schedule values.

usage: make_tables.py <bundle_root>
TEDS and GriTS are means over the six schedule groups (header cells rendered as td). The SoA
column is pooled over units: Table 4 from results/accuracy_micro_t060.csv, Table 5 from the
perturbation metadata, and for the two marker rows from the gold unit counts (all 103
attachments become false negatives, everything else is unchanged)."""
import csv, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1]
res = json.load(open(HERE / 'results_v2.json'))
meta = json.load(open(HERE / 'pairs_v2_meta.json'))
stats = json.load(open(ROOT / 'gold' / 'gold_stats.json'))
N, A = stats['total_scored_units'], stats['attachments']


def mean(rows, f):
    assert len(rows) == 6, len(rows)
    return sum(f(r) for r in rows) / 6


def metrics(set_, name):
    rows = [r for r in res if r['set'] == set_ and r['system'] == name]
    return [mean(rows, lambda r: r['teds_td']), mean(rows, lambda r: r['tedss_td']),
            mean(rows, lambda r: r['grits']['grits_top']), mean(rows, lambda r: r['grits']['grits_con'])]


soa = {r['system']: float(r['soa5']) for r in csv.DictReader(open(ROOT / 'results' / 'accuracy_micro_t060.csv'))}
T4 = [('medical_llm_medium_schema_constrained', 'Medical LLM Medium'), ('gpt_56_terra', 'GPT-5.6-terra'),
      ('gemini_38_flash', 'Gemini-3.8-Flash'), ('claude_sonnet_55', 'Claude-Sonnet-5.5')]
with open(ROOT / 'results' / 'teds_grits_table4.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['system', 'teds', 'teds_struct', 'grits_top', 'grits_con', 'soa_score', 'source'])
    for key, label in T4:
        w.writerow([label] + [f'{x:.3f}' for x in metrics('table4', key)] + [f'{soa[key]:.3f}',
                   'reference implementations (PubTabNet TEDS, table-transformer GriTS), '
                   'code/reference_metrics/results_v2.json'])

marker_soa = 2 * (N - A) / (2 * (N - A) + A)
T5 = [('identity', 'none', 'no change (positive control)', 1.0),
      ('delete_one_cell', 'delete one cell per schedule', '6 of 690 cells, one per group', meta['delete_one_cell']['soa']),
      ('delete_10pct', 'delete 10% of cells', '69 of 690 cells across the six groups (seed 1337)', meta['delete_10pct']['soa']),
      ('clear_marker_fields', 'clear marker fields only',
       'clears the 103 structured marker fields; marker characters remain in the text', marker_soa),
      ('strip_shipped', 'remove every reference marker',
       'clears the 103 structured marker fields and strips the marker characters from the text', marker_soa)]
with open(ROOT / 'results' / 'perturbation_table.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['perturbation', 'reach', 'TEDS', 'TEDS_Struct', 'GriTS_Top', 'GriTS_Con', 'SoA_5comp', 'source'])
    for key, label, reach, s in T5:
        m = metrics('table5', key)
        if key == 'identity':
            w.writerow([label, reach] + ['1.0'] * 5 + ['code/reference_metrics/results_v2.json'])
            assert all(abs(x - 1) < 1e-12 for x in m)
        else:
            w.writerow([label, reach] + [f'{x:.4f}' for x in m] + [f'{s:.4f}', 'code/reference_metrics/results_v2.json'])
print('wrote results/teds_grits_table4.csv and results/perturbation_table.csv')
