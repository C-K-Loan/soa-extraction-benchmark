# Stage 4.b — visits extraction (v2, contact-inference)

Text-only. Input: merged HTML from Stage 3.b (+ optional footnote block). Output: one entry per visit column with header path, reference markers, temporal anchor, contact interval, and condition. Note: "visit" is retained as the JSON key for downstream compat, but the concept is really a *contact* — the column may be a phone call, a remote check-in, or any protocol-defined interaction, not just an in-person visit.

**Schema change (2026-09-28):** dropped `resolved_text`, `visit_number`, `visit_window_start/end`, `is_before/during/after_treatment`. New shape captures full header path + a structured `contact_interval_relative_from_anchor` object with cycle handling.

- **Schema version**: `soa_schedule_v2 (visits)`

## Prompt

```prompt
You are given an HTML SOA table (Schedule of Activities) from a clinical
trial protocol, plus an optional footnote block that defines short
reference markers.

Return ONE ENTRY PER VISIT COLUMN of the table, left to right. A visit
column is any column after the first (activity-label) column. Do not merge
columns and do not split them. Return a column even if it has no marks.

For each column, emit:

- `text`: every header cell above this column, top row to bottom row,
  joined with " > ". Resolve merged/spanning header cells so each column
  gets the full path. Whitespace-normalized, otherwise exactly as written,
  including footnote markers.
  When a header row is a label-value pair — the leftmost cell in the row
  names the axis (e.g. `Visit`, `Week`, `Day`, `Cycle`) and each column
  gives the value for that axis — join the label and value with `": "`
  in the same segment, do NOT split them into two `>`-separated segments.
  Positive examples:
    * "Visit: Screen > Week: -1 > Days: -7 to -1"
    * "Cycle: 2 > Day: 8"
    * "Treatment Period (21-day cycles) > Combination Therapy > Cycle: 2 > Day: 8"
  Negative example (wrong — this dilutes the row label into an extra `>`):
    * ✗ "Visit > Screen > Week > -1 > Days > -7 to -1"

- `reference_markers`: footnote markers that appear in this column's header
  path, exactly as written (e.g. "a", "1)", "*"). Empty list if none.

- `anchor`: the moment time is counted from, in the protocol's own words.
  Read the header path from the BOTTOM row upward and take the first
  phrase that names one: "prior to X", "after X", "post-X", "from X",
  "since X". Examples: "randomization", "last dose", "discontinuation".
  If the column is part of a cycle, or no anchor is named anywhere,
  use "study start".

- `contact_interval_relative_from_anchor`:
  - `target`: planned distance from the anchor as a number. Negative if
    before the anchor. If the column is a cycle day, `target` is the day
    within the cycle (e.g. Cycle 2 Day 8 → 8).
    For a range like "Day -28 to -1", set `target` to the later end (-1)
    and put the remaining span in `window_before` (27).
    For "≤21 days prior to X", set `target` 0 and `window_before` 21.
    For a compound target like "Month 2, Week 1", convert to the smallest
    printed unit (→ 5 weeks).
  - `target_unit`: "hours" | "days" | "weeks" | "months", as printed.
  - `window_before`, `window_after`: allowed deviation as positive
    numbers. "±3d" → 3 and 3. "0 to +7d" → 0 and 7. "-3/+2" → 3 and 2.
  - `window_unit`: unit of the windows.
  - `cycle_length_days`: length of one cycle in days, if the column
    belongs to a cycle (often stated in a higher header row, e.g.
    "21-day cycles"). Also use it for any fixed repeat:
    "every 90 days" → 90, "every 12 weeks" → 84.
  - `cycles`: [first, last] cycle numbers this column covers.
    "Cycle 2" → [2, 2]. "Cycles 4-12" → [4, 12].
    "5 to X", "until progression" (open-ended) → [first, null].
    For a plain repeat ("every 90 days"), use [1, null].

- `condition`: an "only if" rule that decides WHETHER the visit happens,
  in the protocol's words (e.g. "if maintenance therapy applied",
  "Arm B only", "if progression occurs", "unscheduled"). null if none.

Rules:
- Use only what is printed in the table headers or the footnote block.
  Anything not stated → null. Never guess or fill in typical values.
- Use a footnote only when its marker appears in this column's header
  path.
- Copy numbers as printed. Do not compute study days, and do not expand
  cycle ranges into separate entries.

Output JSON only, matching the schema.
```


## Schema (xgrammar-pinned)

```schema
{
  "type": "object",
  "additionalProperties": false,
  "required": ["visits"],
  "properties": {
    "visits": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "text",
          "reference_markers",
          "anchor",
          "contact_interval_relative_from_anchor",
          "condition"
        ],
        "properties": {
          "text": {
            "type": "string"
          },
          "reference_markers": {
            "type": "array",
            "items": { "type": "string" }
          },
          "anchor": {
            "type": "string"
          },
          "contact_interval_relative_from_anchor": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "target",
              "target_unit",
              "window_before",
              "window_after",
              "window_unit",
              "cycle_length_days",
              "cycles"
            ],
            "properties": {
              "target": {
                "type": ["number", "null"]
              },
              "target_unit": {
                "anyOf": [
                  {"type": "string", "enum": ["hours", "days", "weeks", "months"]},
                  {"type": "null"}
                ]
              },
              "window_before": {
                "type": ["number", "null"]
              },
              "window_after": {
                "type": ["number", "null"]
              },
              "window_unit": {
                "anyOf": [
                  {"type": "string", "enum": ["hours", "days", "weeks", "months"]},
                  {"type": "null"}
                ]
              },
              "cycle_length_days": {
                "type": ["number", "null"]
              },
              "cycles": {
                "type": ["array", "null"],
                "items": { "type": ["integer", "null"] },
                "minItems": 2,
                "maxItems": 2
              }
            }
          },
          "condition": {
            "type": ["string", "null"]
          }
        }
      }
    }
  }
}
```

## User prompt

```user
Classify this page. Return JSON only.
```

## Inference params

```params
{
  "sampling": {
    "temperature": 0.0,
    "top_p": 1.0,
    "top_k": 1,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repetition_penalty": 1.0,
    "seed": 42,
    "n": 1
  },
  "max_tokens_first": 4096,
  "max_tokens_retry": 8192,
  "image_dpi": 150
}
```
