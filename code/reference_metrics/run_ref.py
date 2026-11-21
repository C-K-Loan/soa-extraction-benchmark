"""Score HTML pairs with the unmodified reference implementations.
usage: run_ref.py <pairs_json> <vendor_dir> <out_json> [n_workers] [audit_dir_for_ours]"""
import sys, json, time, importlib.util
sys.dont_write_bytecode = True
PAIRS, VENDOR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
NW = int(sys.argv[4]) if len(sys.argv) > 4 else 8
OURS = sys.argv[5] if len(sys.argv) > 5 else None

sys.path.insert(0, VENDOR + '/pubtabnet')   # metric.py does `from parallel import parallel_process`
sys.path.insert(1, VENDOR + '/tatr')
from metric import TEDS                       # PubTabNet reference
from grits import grits_from_html             # table-transformer reference


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def wrap(h):          # PubTabNet input convention: full document, evaluate() looks up body/table
    return '<html><body>' + h + '</body></html>'


def th2td(h):         # PubTabNet convention: header cells are <td> inside <thead>
    return h.replace('<th>', '<td>').replace('</th>', '</td>')


def score(job):
    kind, i, g, p = job
    t = time.time()
    if kind == 'teds_th':
        v = TEDS(structure_only=False, n_jobs=1).evaluate(wrap(p), wrap(g))
    elif kind == 'teds_td':
        v = TEDS(structure_only=False, n_jobs=1).evaluate(wrap(th2td(p)), wrap(th2td(g)))
    elif kind == 'tedss_th':
        v = TEDS(structure_only=True, n_jobs=1).evaluate(wrap(p), wrap(g))
    elif kind == 'tedss_td':
        v = TEDS(structure_only=True, n_jobs=1).evaluate(wrap(th2td(p)), wrap(th2td(g)))
    elif kind == 'grits':
        m = grits_from_html(g, p)
        v = {k: float(x) for k, x in m.items()}
    elif kind == 'ours':
        B = load('metrics_shipped', OURS + '/metrics_buggy.py'); F = load('metrics_fixed', OURS + '/metrics_fixed.py')
        v = {'teds_shipped': B.compute_teds(g, p), 'teds_fixed': F.compute_teds(g, p),
             'tedss': B.compute_teds(g, p, True)}
    return kind, i, v, time.time() - t


if __name__ == '__main__':
    from concurrent.futures import ProcessPoolExecutor, as_completed
    pairs = json.load(open(PAIRS))
    kinds = ['teds_th', 'teds_td', 'tedss_th', 'tedss_td', 'grits'] + (['ours'] if OURS else [])
    jobs = [(k, i, p['gold'], p['pred']) for i, p in enumerate(pairs) for k in kinds]
    res = [dict(set=p['set'], system=p['system'], gid=p['gid'], shape_gold=p['shape_gold'],
                shape_pred=p['shape_pred']) for p in pairs]
    with ProcessPoolExecutor(max_workers=NW) as pool:
        futs = [pool.submit(score, j) for j in jobs]
        for n, f in enumerate(as_completed(futs)):
            k, i, v, dt = f.result()
            res[i][k] = v
            print(f'{n+1}/{len(jobs)} {k} {res[i]["system"][:20]} {res[i]["gid"][:16]} {dt:.0f}s', flush=True)
            json.dump(res, open(OUT, 'w'))
