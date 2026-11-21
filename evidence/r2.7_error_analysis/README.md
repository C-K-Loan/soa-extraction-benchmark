# Error analysis (Conclusion, human-review paragraph)

`r27_errors_resolved.csv` lists the 74 header errors found when the gold and predicted row and
column labels were aligned by hand (see `../r1.4_alignment_and_judge/`). One row per error.

How each error was classed
- Timing errors (24) are judged on the structured fields of the contact (visit time and
  window), not on the header string.
- Marker errors (30) were checked against the gold; five on NCT02791490 were also checked
  against the protocol PDF (page 37), where the markers j, k and m are printed on cells, as in
  the gold.
- Wording errors (20) are not classed by rule.

| Kind | Outcome | Errors |
|---|---|---:|
| timing | visit time in weeks written as days (Medical LLM Medium, one schedule, one call; one also has no window) | 10 |
| timing | visit time wrong otherwise | 3 |
| timing | window wrong, visit time right | 2 |
| timing | no error in the structured fields; only the header text is shorter | 9 |
| marker | wrong marker on a header | 24 |
| marker | right footnote, moved from the cell to the row name | 3 |
| marker | wrong marker, placed on the row name | 2 |
| marker | no error in the structured field | 1 |
| text | wording changed | 20 |

Scored errors per schedule (false positives plus false negatives over all five components,
published matcher), from `results/accuracy_per_group.csv` and `results/attachment_per_group.csv`,
six schedules in file order:

| System | Scored errors per schedule |
|---|---|
| Gemini-3.8-Flash | 0, 11, 0, 97, 10, 2 |
| GPT-5.6-terra | 0, 18, 9, 10, 98, 5 |
| Claude-Sonnet-5.5 | 0, 0, 0, 3, 245, 0 |
| Medical LLM Medium (schema-constrained) | 6, 82, 20, 92, 152, 84 |

Gemini's 97 and Claude's 245 are the two failed cells calls described in the paper.

Limits: no clinician rated these errors; the counts are headers, not independent mistakes
(the ten weeks-as-days columns come from one call); nothing here measures harm or cost.
