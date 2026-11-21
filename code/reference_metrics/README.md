# Reference TEDS and GriTS (Tables 4 and 5)

The TEDS and GriTS values in Tables 4 and 5 of the paper come from the reference
implementations, run on a flat HTML rendering of each schedule (header cells as `td`):

- TEDS and TEDS-Struct: `metric.py` and `parallel.py` from the PubTabNet repository
  (sha256 of the `metric.py` we used starts `a9aedd31`).
- GriTS-Top and GriTS-Con: `grits.py` from the table-transformer repository
  (sha256 starts `75c13031`).

Those three files are not redistributed here. To re-run, download them from their
repositories into `<vendor_dir>/pubtabnet/` and `<vendor_dir>/tatr/`.

Files
- `build_pairs_v2.py <bundle_root> <pairs.json>`: renders gold, predictions and perturbed gold.
- `run_ref.py <pairs.json> <vendor_dir> <results.json>`: runs the reference implementations.
- `results_v2.json`: the stored per-schedule values of our run (60 pairs).
- `pairs_v2_meta.json`: what each perturbation changed.
- `make_tables.py <bundle_root>`: writes `results/teds_grits_table4.csv` and
  `results/perturbation_table.csv` from the stored values.
- `summarise.py`, `replacement_tables.txt`: per-schedule listing and the table values as text.

`code/metrics_teds_grits.py` and `code/run_perturbation.py` are our earlier in-house
implementation. They are kept for the record and for the flat renderer, which
`build_pairs_v2.py` reuses; they no longer produce any number printed in the paper.
