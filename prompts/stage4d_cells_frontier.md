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
    short text like "Day 1". **You MUST include any footnote markers
    inline** — do not strip single-letter/digit trailing markers just
    because they look like extraneous characters.
    Positive examples:
      · source `"X a"`    → `cell_content: "X a"`
      · source `"X d"`    → `cell_content: "X d"`
      · source `"X 1,2"`  → `cell_content: "X 1,2"`
      · source `"x"`      → `cell_content: "x"`
    Negative example (wrong):
      · source `"X d"`    ✗ `cell_content: "X"` (marker dropped)
  * `cell_reference_markers`: markers appearing inside the cell,
    as written ("a", "1)", "*"). Empty array if none.

Do not emit rows for empty cells (blank / whitespace / "-" / "—").
For colspan / rowspan cells: emit one entry per covered id, all with
the same cell_content.

Use ids EXACTLY as they appear in the lists — do not invent, rename,
or drop leading zeros.

Output JSON only, matching the schema.