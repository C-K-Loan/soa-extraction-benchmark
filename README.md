# A Benchmark for Schedule of Activities Extraction from Clinical Trial Protocol PDFs

Data and evaluation artifacts for the paper (CVC 2027). Repository: https://github.com/C-K-Loan/soa-extraction-benchmark

Annotator names and machine paths are not included; annotators appear as `annotator_1` to `annotator_4`.

## What a Schedule of Activities is, as this benchmark models it

A schedule is four kinds of object, not a table:

- **activities** — the rows, what is done to a participant
- **contacts** — the visit columns, with anchor-relative timing, windows, cycles and conditions
- **reference definitions** — the footnotes and legends a schedule depends on
- **cells** — the grid binding an activity to a contact

Markers (`a`, `1)`, `*`) attach a reference definition to an activity, a contact or a cell. Recovering the grid and recovering those attachments are different tasks, which is what this benchmark is built to separate.

## Contents

```
gold/soa_gold.jsonl            the hand-validated gold set
gold/gold_stats.json           unit counts, recomputed
gold/page_labels.jsonl         438 human-reviewed Stage 1 page labels
gold/page_review_events.jsonl  the review log the page labels are derived from
gold/page_label_stats.json
silver/stage1_page_labels.jsonl  unvalidated Stage 1 page labels
silver/silver_stats.json
predictions/<system>/<group_id>.json   Stage 3 output per system and schedule group
predictions/manifest.json      which systems were evaluated and how
results/                       the scored outputs behind every table in the paper
code/score_soa.py              SoA scorer (standard library only)
code/reference_metrics/        reference TEDS / GriTS run behind Tables 4 and 5
code/metrics_teds_grits.py     earlier in-house TEDS / GriTS-style code (see below)
code/run_perturbation.py       earlier perturbation harness (see below)
prompts/                       Stage 3 prompts and SETTINGS.md
docs/gold_record_excerpt_NCT01621737.md  an annotated excerpt of one gold record
evidence/                      alignment, judge, bootstrap, temporal and error-analysis files
protocols/                     NCT identifiers and a fetch script
reproduce.sh                   regenerates every scored CSV from predictions/
verify.py                      recompute every count the paper reports
SHA256SUMS.json
```

## The gold set

6 schedule groups from 5 protocols, **1104 scored units**:

| component | units |
|---|---:|
| activities | 169 |
| contacts | 60 |
| reference definitions | 82 |
| cells | 690 |
| marker attachments | 103 |
| **total** | **1104** |

Every item was confirmed or corrected by a human annotator; no unreviewed model prediction is in it. Each record carries an `annotator` field identifying which of the two annotators was the final authority for that group.

The temporal fields of a contact (target interval and visit window) are filled from its column header only. Timing that a protocol states only in a footnote is kept in the reference definitions and is not copied into those fields.

## The reviewed page labels

`gold/page_labels.jsonl` holds the **438 pages from 99 protocols** whose Stage 1 labels were reviewed and corrected by hand, by four annotators. It is derived from an append-only review log of 591 events: the last decision per page wins, and pages whose final event is an undo are dropped.

Review was concentrated on pages the pipeline had already surfaced as schedule candidates, so 437 of the 438 carry `is_soa_related = true` and 256 carry `has_soa_table`. **This set can speak to precision on positives; it cannot estimate recall, and no corpus-wide false-negative rate is established anywhere in this work.** Eight labels were exercised; `has_soa_text` and `has_soa_footnotes` were not, and are not included. Reviewer notes and internal revision hashes are not shipped.

These 99 protocols are a different and broader set than the 41 in `silver/`; the two overlap on 26 protocols.

## The silver set

3605 pages from 41 protocols, labelled by Stage 1 and **not validated**. 220 pages (6.1%) are predicted schedule-related. These are uncorrected predictions, useful as a distribution over a corpus, not as a label set with characterised quality. No false-negative rate is established for them.

## Protocol PDFs

Not redistributed. They are public documents on ClinicalTrials.gov; fetch them by identifier:

```bash
cd protocols
python3 fetch_protocols.py gold_nct_ids.txt --out pdfs/
```

`gold_nct_ids.txt` holds 5 identifiers, `silver_nct_ids.txt` 41. A `group_id` is `<NCT>__<pdf stem>__g<NNN>`, so it names the document and the schedule within it.

## Results

| file | what it holds |
|---|---|
| `code/metrics_teds_grits.py` | TEDS, TEDS-Struct and GriTS over the serialised grid. |
| `code/run_perturbation.py` | The marker-stripping perturbation harness. |
| `predictions/<system>/<group_id>.json` | Stage 3 output per group per system, the input to every scored CSV. |
| `results/accuracy_micro_t060.csv` | Per-component precision/recall/F1 and the SoA score, micro-pooled over the six gold groups, tolerant matcher at 0.60 (Table 3). |
| `results/accuracy_per_group.csv` | The same scores split by schedule group. |
| `results/soa_score_5component.csv` | Per-component tp/fp/fn feeding the pooled SoA score. |
| `results/attachment_per_group.csv` | Marker-to-owner attachment F1 per group, split by activity/contact/cell scope. |
| `results/matcher_strict_vs_tolerant.csv` | Activity, contact and reference-definition pools under a strict matcher and a tolerant one at 0.75. |
| `results/per_protocol_cost.csv` | Measured cost per gold protocol per system, Stage 1 and Stage 3 separately. |
| `results/stage1_cost.csv` | Stage 1 page-classification cost per protocol. |
| `results/teds_grits_table4.csv` | TEDS, TEDS-Struct, GriTS-Top, GriTS-Con (reference implementations, mean over the six groups) and the SoA score, one row per system (Table 4). |
| `results/perturbation_table.csv` | Perturbed gold scored against unperturbed gold, same metrics (Table 5). The identity row is the positive control and reads 1.000 on every metric. |
| `code/score_soa.py` | Standard-library SoA scorer. See `--validate` and `--help`. |
| `code/reference_metrics/` | Scripts and stored values of the reference TEDS / GriTS run. |
| `reproduce.sh` | Regenerates every scored CSV from `predictions/` and `gold/`. |

## Scoring

Components are matched with a tolerant matcher: `difflib.SequenceMatcher` over case-folded, punctuation-stripped text, accepting at a ratio of **0.60**, fixed for every system.

`results/matcher_strict_vs_tolerant.csv` contrasts a strict matcher with a tolerant one at 0.75. The SoA score at thresholds 0.50 to 0.70 is in `evidence/threshold_sweep/`.

Cells are paired on the concatenated activity and contact text, so a cell can be credited when only one of its two axes is right. `evidence/r1.4_alignment_and_judge/` holds a manual alignment of every row and column and the scores recomputed on it.

The **SoA score** is micro-F1 pooled over all five components:

```
SoA = 2 * sum_c TP_c / (2 * sum_c TP_c + sum_c FP_c + sum_c FN_c)
      c in {activities, contacts, reference definitions, cells, attachments}
```

Pooling rather than averaging component F1s is deliberate: cells are 690 of the 1104 units, so the score is dominated by the grid, with the other four components able to move it.

An attachment is an `(owner, marker)` pair at activity, contact or cell scope. When the owner itself does not match, its gold attachments are counted as false negatives rather than dropped.

### Scorer options

`code/score_soa.py` prints the published score by default. Options: `--weights activities=1,contacts=1,references=1,cells=1,attachments=1` sets a weight per component; `--normalize` divides each component's counts by its number of gold units, so that every component counts equally; `--weights temporal=1` adds an optional sixth component that scores the visit target and window of each contact (default weight 0). With the defaults the output is unchanged.

The optional temporal component pairs contacts with the scorer's own string matching. The target-interval F1 printed in the paper uses the manual column alignment instead (`evidence/r1.5_temporal/`), so the two can differ: for Medical LLM Medium the built-in component is about 13 F1 points lower.

### Scorer caveat

`code/score_soa.py` reproduces the published TP/FP/FN of Claude-Sonnet-5.5 and Gemini-3.8-Flash exactly and differs by one attachment unit for GPT-5.6-terra, which moves its SoA score by less than 0.1 points (93.5 here against the paper's 93.4). The original scoring code is no longer available.

## Prompts and settings

`prompts/` holds the five Stage 3 prompts and `SETTINGS.md`, which lists the decoding settings and where they differed between systems (cells prompt version, output budget on retry, chunking of the cells call, hidden reasoning).

## The two Medical LLM Medium runs

`predictions/medical_llm_medium_schema_constrained/` is the run in Table 3 (output constrained to the JSON schema, SoA score 81.4). `predictions/medical_llm_medium_unconstrained/` names the schema in the prompt and parses the reply instead (SoA score 87.1); it is not in Table 3.

## Evidence folders

| folder | what it holds |
|---|---|
| `evidence/r1.4_alignment_and_judge/` | The blind manual alignment of gold and predicted row and column labels, its adjudication, the three-model judge prompt and raw replies, and the scripts and outputs that re-score the systems on the alignment. `tasks_key.json` maps the blinded tasks to systems. |
| `evidence/r2.2_bootstrap/` | Cluster bootstrap over the six schedules (10,000 resamples) and its output. |
| `evidence/r1.5_temporal/` | Probe that scores target interval and visit window on the manual alignment, and its output on this gold set. Only the target scores are printed in the paper; see the note on window scores in the paper's appendix. |
| `evidence/r2.7_error_analysis/` | The 74 header errors with their outcome, and scored errors per schedule. |
| `evidence/threshold_sweep/` | SoA score at matcher thresholds 0.50 to 0.70. |

The judge and alignment files were produced with paid model calls; nothing in `reproduce.sh` or `verify.py` calls a model.

## TEDS and GriTS

The TEDS and GriTS values in Tables 4 and 5 come from the reference implementations (PubTabNet TEDS, table-transformer GriTS), run on a flat rendering of each schedule. The stored per-schedule values and the scripts are in `code/reference_metrics/`; its README names the three upstream files to download for a re-run, which are not redistributed here.

`code/metrics_teds_grits.py` and `code/run_perturbation.py` are our earlier in-house implementation. Its TEDS compares leaf text exactly and its GriTS-style score matches rows and columns greedily on header text, so it is not the published metric. It is kept for the record and for the flat renderer; it no longer produces any number printed in the paper.

## Verifying the bundle

```bash
python3 verify.py
```

It recomputes every count above from the shipped files, checks the page-label agreement figures, re-scores `predictions/` against the shipped scores, checks that the identity row of the perturbation table reads 1.000 on every metric, and checks every file against `SHA256SUMS.json`.

To regenerate every scored CSV from `predictions/` and `gold/`:

```bash
bash reproduce.sh
```

Standard library only; no API calls and no model inference.

## Licence

Annotations and code are released for research use. The protocol PDFs are not included and remain subject to their own terms at the source.
