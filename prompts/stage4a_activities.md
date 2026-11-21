# Stage 4.a — activities extraction (v2)

Text-only. Input: merged HTML from Stage 3.b (+ optional footnote block). Output: list of `{text, uses_reference_markers}` for every activity row.

**Schema change (2026-09-28):** dropped `resolved_text`. The model no longer inlines footnote definitions — it just tags which markers a row cites. Stage 4.c (references) is the source of truth for what each marker means; the SPA and Stage 4.d compose the display string on demand. This decouples ref-editing from activity-extraction and gets the model out of the copy-a-long-definition-verbatim business.

- **Schema version**: `soa_schedule_v2 (activities)`


## Prompt

```prompt
You are given an HTML SOA table (Schedule of Activities) from a
clinical trial protocol, plus an optional footnote block that defines
short marker identifiers (a / b / 1. / *  / † …).

Return EVERY DISTINCT ACTIVITY from the table (i.e. the row labels in the
first column, one per data row — skip header rows). For each activity emit:

- `text`: the row label EXACTLY as written, whitespace-normalized. **You
  MUST preserve the marker tokens inline at the end of `text`** where
  they appear in the source. Do not remove single-letter markers just
  because they look like extraneous characters. Positive examples
  (correct):
    * source `"Physical exam d"`   → `text: "Physical exam d"`
    * source `"Vital signs *"`      → `text: "Vital signs *"`
    * source `"Blood sample 1."`    → `text: "Blood sample 1."`
    * source `"Urine screen b"`     → `text: "Urine screen b"`
  Negative examples (wrong — do NOT do this):
    * source `"Physical exam d"`   ✗ `text: "Physical exam"` (marker dropped)
    * source `"Urine screen b"`    ✗ `text: "Urine screen"`  (marker dropped)
- `uses_reference_markers`: a JSON array of the marker tokens that appear
  in `text`. Each entry is the marker EXACTLY as it appears in the row —
  same casing, same trailing punctuation ("a", "*", "1.", "†"). Order
  reflects appearance in the row; deduplicate exact repeats. Empty array
  when the row has no marker citations.

Rules:
- Skip anything that is clearly a section header (a row that groups
  activities without being one itself, e.g. "STUDY PROCEDURES", "TESTS
  AND PROCEDURES") — those rows have no procedure and belong nowhere.
- Do NOT inline the definition of a marker into `text`. That's Stage 4.c's job.
- Do NOT invent markers that aren't in the row (e.g. don't guess a footnote
  based on context — only tag what is literally there).

Output JSON only, matching the schema.
```


## Schema (xgrammar-pinned)

```schema
{
  "type": "object",
  "properties": {
    "activities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "uses_reference_markers": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "text",
          "uses_reference_markers"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "activities"
  ],
  "additionalProperties": false
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
  "max_tokens_first": 384,
  "max_tokens_retry": 768,
  "image_dpi": 150
}
```
