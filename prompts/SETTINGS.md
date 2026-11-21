# Prompts and decoding settings for the Table 3 runs

Files in this folder
- `stage4a_activities.md`: activities (row labels). Same for all systems.
- `stage4b_visits.md`: contacts (visit columns). Same for all systems.
- `stage4c_references.md`: reference definitions (footnotes). Same for all systems.
- `stage4d_cells_frontier.md`: cells, used for Gemini-3.8-Flash, GPT-5.6-terra and Claude-Sonnet-5.5.
- `stage4d_cells_medical_llm_medium.md`: cells, used for Medical LLM Medium (an earlier version of the same prompt).

Marker attachments have no prompt and no model call: markers are emitted with activities,
contact headers and cells, and a deterministic step joins them to the reference definitions.

Shared settings: temperature 0, top-p 1, output constrained to the JSON schema.

Settings that differed between systems

| | Frontier systems | Medical LLM Medium |
|---|---|---|
| Cells prompt | revised version | earlier version |
| Output budget per call | 4,096 tokens, one retry at 8,192 | 4,096 tokens, one retry at 32,768 |
| Cells call | one call per schedule | above 25 activities, split into chunks of 15 rows, each with the full activity and contact lists |
| Hidden reasoning | provider records show 0 reasoning tokens for Gemini-3.8-Flash and Claude-Sonnet-5.5 and 154 to 1,431 per call for GPT-5.6-terra | off |

The second Medical LLM Medium run in `predictions/` (unconstrained) names the schema in the
prompt and parses the reply instead of constraining the output.

Known consequence: the largest schedule (231 cells) needs about 9,700 output tokens for the
cells call, more than the frontier budget of 8,192.
