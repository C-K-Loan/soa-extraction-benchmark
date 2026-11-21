# Stage 4.d — SOA cell binding (schedule creation)

Text-only. Input: merged HTML from Stage 3.b + activities (with ids `act_XX`) + contacts (with ids `con_XX`) previously extracted by 4.a / 4.b. Output: the SOA matrix — every non-empty cell as `{visit_id, activity_id, cell_content, cell_reference_markers}`.

- **Schema version**: `soa_schedule_v2 (cells)`

## Prompt

```prompt
You are given an HTML SOA table (Schedule of Activities) from a
clinical trial protocol. Alongside the table you get two JSON lists:
`activities` (row labels, each with an `id` like "act_01", "act_02")
and `contacts` (visit column headers, each with an `id` like
"con_01", "con_02"). Both lists are in the SAME ORDER as the table:
activities[0] is the first data row of the table, activities[1] is
the second, etc. Same for contacts vs visit columns from left to right.

Your job: emit every FILLED cell of the table.

Traverse the table row by row, top to bottom:
- The i-th data row's cells belong to activity_id = activities[i].id
  (i.e. activities[0] → act_01, activities[1] → act_02).
- The j-th visit column corresponds to visit_id = contacts[j].id
  (contacts[0] → con_01, ...).
- For each non-empty cell, emit one entry:

  * `visit_id`: the contact id for the column.
  * `activity_id`: the activity id for the row.
  * `cell_content`: the mark inside the cell EXACTLY as written,
    whitespace-normalized. Typical: "x", "X", "xx", "•", digits, or
    short text like "Day 1". Include any footnote markers.
  * `cell_reference_markers`: markers appearing inside the cell,
    as written ("a", "1)", "*"). Empty array if none.

Do not emit rows for empty cells (blank / whitespace / "-" / "—").
For colspan / rowspan cells: emit one entry per covered id, all with
the same cell_content.

Use ids EXACTLY as they appear in the lists — do not invent, rename,
or drop leading zeros.

Output JSON only, matching the schema.
```


## Schema (xgrammar-pinned)

```schema
{
  "type": "object",
  "additionalProperties": false,
  "required": ["cells"],
  "properties": {
    "cells": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "visit_id",
          "activity_id",
          "cell_content",
          "cell_reference_markers"
        ],
        "properties": {
          "visit_id":     { "type": "string" },
          "activity_id":  { "type": "string" },
          "cell_content": { "type": "string" },
          "cell_reference_markers": {
            "type": "array",
            "items": { "type": "string" }
          }
        }
      }
    }
  }
}
```

## User prompt

```user
Extract every filled cell of this SOA table. Return JSON only.
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
