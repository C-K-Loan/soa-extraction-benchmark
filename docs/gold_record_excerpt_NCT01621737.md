# Annotated gold record excerpt, NCT01621737

An excerpt of the gold record for one schedule, by object kind: the page group, activities,
reference definitions, contacts and cells. Lists are shortened; the complete record is the
`NCT01621737` entry in `gold/soa_gold.jsonl`.

In the source protocol this schedule runs over pages 9 to 11 and continues onto the next page
without repeating the visit, week and day headers, which is the case the page-grouping stage
has to recover. The protocol PDF is not redistributed; `protocols/` holds the script that
fetches it from ClinicalTrials.gov.

**GROUPS**
```python
{
groups: {
 {pages: [9,10,11], group_name: 'Main Study'},
}

```


**ACTIVITIES**
```json
    {"id": "act_01", "text": "Informed Consent", "uses_reference_markers": []},
    {"id": "act_02", "text": "Assess Inclusion/Exclusion", "uses_reference_markers": []},
    {"id": "act_03", "text": "Medical History", "uses_reference_markers": []},
    {"id": "act_04", "text": "Physical Exam", "uses_reference_markers": []},
    {"id": "act_05", "text": "SCID/Psychiatric History", "uses_reference_markers": []},
    {"id": "act_06", "text": "Urine Drug Screen b", "uses_reference_markers": ["b"]},
  ... 17 further activities omitted, full record in the supplementary material
```

**REFERENCES**
```json
{
  "references": [
    {
      "id": "ref_a",
      "text": "a Screening procedures can be done over a week period if needed to complete all procedures such as confirmation of diagnosis. The screening and baseline visits can occur on the same day.",
      "reference_marker": "a"
    },
    {
      "id": "ref_b",
      "text": "b In addition to Visit 1, an optional urine drug screen or blood chemistry may be performed at any point during the study at the discretion of the Principal Investigator or study coordinators if it is suspected the subject is not abstaining from illegal substances or have general health concerns.",
      "reference_marker": "b"
    },
    {
      "id": "ref_c",
  ... 45 further lines omitted, full record in the supplementary material
```

**CONTACTS**
```json
{
  "contacts": [
    {
      "id": "con_01",
      "text": "Visit: Screen a > Week: -1 > Days: -7 to -1",
      "reference_markers": ["a"],
      "anchor": "study start",
      "contact_interval_relative_from_anchor": {
        "target": -1,
        "target_unit": "days",
        "window_before": 6,
        "window_after": 0,
        "window_unit": "days",
        "cycle_length_days": null,
        "cycles": null
      },
      "condition": null
    },
         
    
    {
      "id": "con_02",
  ... 128 further lines omitted, full record in the supplementary material
```


**CELLS**
```json
    {"visit_id": "con_01", "activity_id": "act_01", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_02", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_03", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_04", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_05", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_06", "cell_content": "x", "cell_reference_markers": []},
    {"visit_id": "con_01", "activity_id": "act_11", "cell_content": "xx", "cell_reference_markers": []},
  ... 80 further cells omitted, full record in the supplementary material
```
