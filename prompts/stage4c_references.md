# Stage 4.c — reference extraction

Text-only. Input: merged HTML from Stage 3.b (+ optional footnote block). Output: list of {text, reference_marker} for every reference / footnote definition attached to the SOA table.

- **Schema version**: `soa_schedule_v1 (references)`

## Prompt

```prompt
You are given an HTML SOA table (Schedule of Activities) from a clinical
trial protocol, plus an optional footnote block that may list reference
definitions below the table.

Your job: return EVERY reference / footnote definition that could be cited
by a table cell — the ones that define what markers like "a", "1", "*", "†",
"(b)" mean. These usually live in a <tfoot>, a <div class="table-footnotes">,
or the footnote_block below the table.

For each definition, emit:

- `reference_marker`: the marker / symbol that identifies the reference,
  EXACTLY as written before its text. All of these are valid marker
  shapes and MUST be extracted the same way — do not skip numeric ones:
    * lowercase letters: "a", "b", "aa", "ab"
    * numbers: "1", "2", "13" (with or without a trailing dot: "1", "1.")
    * symbols: "*", "†", "‡", "§", "¶", "(a)", "(1)"
  Include the trailing punctuation only if it is part of the marker
  itself (e.g. "1." keeps the dot). Do not add colons.
  If the footnote block below the SOA table contains a list like
  `"1 See Section 3.2\n2 Blood draw at ...\n3 ..."` you MUST return one
  entry per numbered line — treat digits identically to letters.
- `text`: the FULL definition sentence(s) after the marker, whitespace-
  normalized, without the marker prefix. If the definition spans multiple
  lines in the source, join them with single spaces.

Rules:
- Skip citations inside cells (e.g. a cell "Physical exam a" is NOT a
  reference definition — the definition is the row in the footnote block
  that starts with "a ...").
- Skip section labels, running headers, page numbers, revision stamps
  ("LY2148568 PK Addendum", "Amendment (a) to Addendum (3)", etc.).
- If a marker appears more than once (e.g. two "a" rows), emit each one
  as its own entry — do not merge.
- Preserve the original casing of the text.
- If no references exist, return an empty array.

Output JSON only, matching the schema.
```


## Schema (xgrammar-pinned)

```schema
{
  "type": "object",
  "properties": {
    "references": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "reference_marker": {
            "type": "string"
          },
          "text": {
            "type": "string"
          }
        },
        "required": [
          "reference_marker",
          "text"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "references"
  ],
  "additionalProperties": false
}
```

## User prompt

Sent alongside the page image on every request. Kept minimal — the SYSTEM prompt already specifies the classification target and format.

```user
Extract all references from this SOA table. Return JSON only.
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
