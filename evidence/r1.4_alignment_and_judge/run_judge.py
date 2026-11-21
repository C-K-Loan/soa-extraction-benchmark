#!/usr/bin/env python3
"""LLM-judge harness: label alignment + content grade. One text-only call per (task, judge).

    python3 run_judge.py --dry-run          # prints 2 prompts + call/token plan, no network
    python3 run_judge.py --execute          # PAID: sends the calls (needs OPENROUTER_API_KEY)

For every gold label the judge returns the predicted label that is the same row/column
of the source table (or null), and for every pair a content grade:
  same     the two texts are the same (whitespace aside)
  strict   characters differ, but everyone reads both the same way
  missing  nothing stated is wrong, but information in gold is absent
  wrong    a difference that changes the meaning (number, week, day, window, unit,
           sign, a different activity name)
plus a reason of at most 12 words when the grade is "missing" or "wrong".

Follows the project's OpenRouter convention (analysis/rerun-failed-cells-2026-11-20/
rerun.py): POST https://openrouter.ai/api/v1/chat/completions, bearer key from the
OPENROUTER_API_KEY environment variable, temperature 0, usage included, every HTTP
body saved verbatim, finish_reason checked BEFORE parsing. Uses urllib so it has no
dependencies. The key is never printed or written.

Outputs, per judge, under judge_runs/<judge>/ :
  raw/<task_id>.json    prompt, and every attempt's HTTP status and verbatim body
  alignments.json       schema soa-judge-alignment/4:
      alignments  task id -> {gold id -> predicted id | null}
      content     task id -> {gold id -> "same" | "strict" | "missing" | "wrong" | null}  (paired ids only;
                  null = the judge gave no valid grade, recorded under problems)
      reasons     task id -> {gold id -> text}                                  ("missing" / "wrong")
      info        task id -> finish reason, usage, problems (unknown ids, one-to-one
                  violations, bad grades, parse errors)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
URL = "https://openrouter.ai/api/v1/chat/completions"
FRONTIER = ["gemini_38_flash", "gpt_56_terra", "claude_sonnet_55"]
GRADES = ("same", "strict", "missing", "wrong")
SCHEMA = "soa-judge-alignment/5"

SYSTEM_PROMPT = (
    "You are a careful annotator of clinical-trial protocol tables. "
    "You answer with a single JSON object and nothing else."
)

AXIS_TEXT = {
    "rows": {
        "unit": "row",
        "what": (
            "Each label names one ROW of the table: an activity, assessment or procedure "
            "(for example \"Informed consent\", \"Vital signs\", \"12-lead ECG\")."
        ),
        "align_note": (
            "A CANDIDATE that is evidently the transcription of a given REFERENCE row is its "
            "counterpart even if its text has mistakes or leaves something out; the mistakes are "
            "graded in step 2. A section heading and an item under it are different rows. If a "
            "CANDIDATE merges several REFERENCE rows into one, or splits one into several, pair "
            "only the closest and give null for the rest."
        ),
        "form": (
            "- case, punctuation, trademark signs;\n"
            "- a footnote marker written as a superscript, as a plain trailing letter or digit, "
            "glued to the word or separate (\"Spirometry b\" / \"Spirometryᵇ\" / "
            "\"Spirometryb\");\n"
            "- an abbreviation every reader expands the same way (\"MRI\" / \"Magnetic resonance imaging\"; "
            "\"BMI\" / \"Body mass index\");\n"
            "- an obvious spelling or OCR slip that leaves the activity unmistakable."
        ),
        "missing": (
            "part of the activity name or a qualifier in the REFERENCE is left out "
            "(\"Spirometry/ peak flow\" -> \"Spirometry\"; \"Questionnaires (A and B)\" -> "
            "\"Questionnaires (A)\"; \"12-lead ECG (triplicate)\" -> \"12-lead ECG\")"
        ),
        "wrong": (
            "the CANDIDATE names a different activity, specimen, instrument, dose, number or unit "
            "(\"Left knee X-ray\" -> \"Right knee X-ray\"; \"Systolic pressure\" -> \"Diastolic pressure\"; "
            "\"Dose 1\" -> \"Dose 2\"; \"Biopsy\" -> \"Bone scan\")"
        ),
    },
    "columns": {
        "unit": "column",
        "what": (
            "Each label is the header of one COLUMN of the table: a visit, contact or time point. "
            "A header is written as a path through the stacked header rows, top to bottom, joined "
            "by \" > \". Each step may or may not carry the name of its header row, for example "
            "\"Treatment Period > Visit Number: Visit 3 > Study Day: Day 15 > Window: ± 2 days\"."
        ),
        "align_note": (
            "A CANDIDATE that is evidently the transcription of a given REFERENCE column is its "
            "counterpart even if a visit number, week, day or window in it is wrong or left out; "
            "the mistakes are graded in step 2. Example: if the fourth REFERENCE column is "
            "\"Visit 4 > Week 6\" and the fourth CANDIDATE, sitting between the same neighbours, "
            "reads \"Visit 4 > Week 8\", they are the same column (graded wrong), not a null. "
            "Do not shift a whole run of columns by one to make digits agree when the order says "
            "otherwise, and do not pair by position when the CANDIDATE list has clearly dropped "
            "or inserted a column."
        ),
        "form": (
            "- case, punctuation, separators;\n"
            "- a footnote marker written as a superscript, as a plain trailing letter or digit, "
            "glued to the word or separate (\"Run-in a\" / \"Run-inᵃ\" / \"Run-ina\"; in "
            "\"Cycle: 2 5\" against \"Cycle: 2⁵\" the 5 is a footnote marker, not part of "
            "the cycle number);\n"
            "- an abbreviation every reader expands the same way (\"Wk 6\" / \"Week 6\"; \"EOT\" / "
            "\"End of Treatment\"; \"± 7 days\" / \"+/-7d\");\n"
            "- the NAME of a header row dropped or shortened while its value is kept "
            "(\"Assessment Point: Visit 9 > Study Month: Month 3\" / \"Visit 9 > Month: 3\")."
        ),
        "missing": (
            "a VALUE present in the REFERENCE is absent: the week or day, the visit window "
            "(\"± 2 days\"), the period name, the visit number or title"
        ),
        "wrong": (
            "a value is different: another visit number, week, day, month or cycle; another "
            "window size or unit (days vs weeks); a changed sign (\"-2\" -> \"2\", \"±\" -> \"+\"); "
            "another period or named visit (Screening -> Baseline)"
        ),
    },
}

FLAGS = ("content", "semantic")

PROMPT = """\
Two people transcribed the SAME table, the Schedule of Activities of one clinical-trial protocol. The REFERENCE transcription is taken as correct. Below are the {unit} labels each of them wrote down. You do two things: (1) pair each REFERENCE label with the CANDIDATE label that is the same {unit} of the source table, and (2) grade how well each paired CANDIDATE label reproduces the content of its REFERENCE label.

{what}

STEP 1 - ALIGN
For every REFERENCE label find the CANDIDATE label that is the transcription of the same {unit} of the source table: the same physical {unit}, at the same place in the table.
- Both lists are in table order. Order is a strong cue: use it together with the text.
- {align_note}
- Use null only when the CANDIDATE list has no counterpart for that REFERENCE {unit} (it was skipped, or merged into another). Do not use null merely because the text differs or because you would grade it wrong.
- One-to-one: a CANDIDATE label may be used at most once. Do not assume the lists have the same length: either side may have extra {unit}s.
- Ids carry no meaning.

STEP 2 - CHECK EACH PAIR
Compare the paired CANDIDATE text with the REFERENCE text and answer two yes/no questions (true/false).
"content": do the two texts differ in ANY character? Ignore only whitespace (spaces, line breaks). Differences of form count here and only here:
{form}
"semantic": does the CANDIDATE label mean something different from the REFERENCE label, or leave out information the REFERENCE states, so that a reader would interpret the {unit} differently or know less about it? This covers a contradiction (typically {wrong}) and an omission (typically {missing}). Differences of form are not semantic. A dropped or shortened header-row NAME whose value is kept is not semantic.
Rules:
- "semantic" true implies "content" true.
- Footnote markers (a short letter, number or symbol attached to a label that points to a footnote): a marker that is DIFFERENT from the one in the REFERENCE, or a marker on a label whose REFERENCE has none, is semantic, because it points the reader to the wrong footnote. The same marker written in another form (superscript, attached or spaced), or a marker the CANDIDATE leaves out, is "content" only.
- Extra information in the CANDIDATE that the REFERENCE does not have, and that does not contradict it, is "content" only (footnote markers excepted, see above).
- Judge only what the two texts say. Do not guess what the source table contained.

REFERENCE {UNIT} LABELS ({n_ref})
{ref_block}

CANDIDATE {UNIT} LABELS ({n_cand})
{cand_block}

OUTPUT
Return only a JSON object, with no prose and no code fence, with one entry for every REFERENCE id ({first_ref} to {last_ref}), of exactly this shape:
{{"alignment": {{"R1": {{"c": "C1", "content": false, "semantic": false}}, "R2": {{"c": "C2", "content": true, "semantic": true, "reason": "week 8 instead of week 6"}}, "R3": {{"c": "C4", "content": true, "semantic": true, "reason": "visit window omitted"}}, "R4": {{"c": "C5", "content": true, "semantic": false}}, "R5": null}}}}
"c" is a CANDIDATE id from the list above. Give both booleans for every pair. Give "reason" (at most 12 words) only when "semantic" is true; omit it otherwise. A REFERENCE with no counterpart is null."""


def build_prompt(task: dict) -> tuple[str, dict, dict]:
    """Returns (prompt, R-id -> gold id, C-id -> predicted id). Prompt-local ids are
    used so that gold 'con_05' and predicted 'con_05' cannot be paired by id."""
    a = AXIS_TEXT[task["axis"]]
    rmap = {f"R{i}": g["id"] for i, g in enumerate(task["gold"], 1)}
    cmap = {f"C{i}": p["id"] for i, p in enumerate(task["pred"], 1)}
    line = lambda k, x: f"{k}: {json.dumps(x['text'], ensure_ascii=False)}"
    ref = "\n".join(line(f"R{i}", g) for i, g in enumerate(task["gold"], 1))
    cand = "\n".join(line(f"C{i}", p) for i, p in enumerate(task["pred"], 1)) or "(none)"
    prompt = PROMPT.format(unit=a["unit"], UNIT=a["unit"].upper(), what=a["what"],
                           align_note=a["align_note"], form=a["form"], missing=a["missing"],
                           wrong=a["wrong"], n_ref=len(rmap), n_cand=len(cmap), ref_block=ref,
                           cand_block=cand, first_ref="R1", last_ref=f"R{len(rmap)}")
    return prompt, rmap, cmap


def default_judges() -> list[str]:
    man = json.loads((HERE.parents[1] / "predictions" / "manifest.json").read_text())
    by = {s["system"]: s["model"] for s in man["systems"]}
    return [by[s] for s in FRONTIER]


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", model)


def est_tokens(text: str) -> int:
    return (len(text) + 3) // 4          # rough: 4 characters per token


def est_output_tokens(task: dict) -> int:
    """~14 tokens per paired entry ('"R12": {"c": "C12", "grade": "same"},'), plus ~22 for
    a reason. Labels without an exact-text pair are used as the proxy for 'has a reason'."""
    n = len(task["gold"])
    return 12 + 34 * n + 22 * (n - len(task["prefill"]))


def parse_alignment(content: str, rmap: dict, cmap: dict) -> tuple[dict | None, list[str]]:
    """Strict JSON in; out {"alignment": {gold id -> pred id | None},
    "content": {gold id -> grade | None} for paired ids, "reasons": {gold id -> str}}.
    Anything the judge was not allowed to say becomes null and is recorded under
    problems; nothing is repaired into a pair or into a grade."""
    problems: list[str] = []
    txt = (content or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", txt, re.S)
    if m:
        txt = m.group(1)
        problems.append("code_fence")
    try:
        obj = json.loads(txt)
    except json.JSONDecodeError:
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            return None, problems + ["not_json"]
        try:
            obj = json.loads(txt[i:j + 1])
            problems.append("prose_around_json")
        except json.JSONDecodeError:
            return None, problems + ["not_json"]
    al = obj.get("alignment") if isinstance(obj, dict) else None
    if not isinstance(al, dict):
        return None, problems + ["no_alignment_object"]
    out, grades, reasons, used, flags = {}, {}, {}, set(), {}
    for r, gid in rmap.items():
        if r not in al:
            problems.append(f"missing:{r}")
            out[gid] = None
            continue
        v = al[r]
        grade = reason = None
        fl = None
        if isinstance(v, dict):
            reason = v.get("reason")
            fl = {k: v.get(k) for k in FLAGS}
            v = v.get("c")
            if v is None and any(x is not None for x in fl.values()):
                problems.append(f"grade_without_candidate:{r}")
        if v is None:
            out[gid] = None
        elif not isinstance(v, str) or v not in cmap:
            problems.append(f"unknown_candidate:{r}={v!r}")
            out[gid] = None
        elif v in used:
            problems.append(f"not_one_to_one:{r}={v}")
            out[gid] = None
        else:
            used.add(v)
            out[gid] = cmap[v]
            if fl is not None and all(isinstance(fl[k], bool) for k in FLAGS):
                flags[gid] = fl
                if fl["semantic"] and not fl["content"]:
                    problems.append(f"inconsistent_flags:{r}")
                # legacy 4-way grade, derived (precedence wrong > missing > strict)
                grades[gid] = "wrong" if fl["semantic"] else "strict" if fl["content"] else "same"
            else:
                problems.append(f"bad_flags:{r}={fl!r}")
                grades[gid] = None
                flags[gid] = None
            if isinstance(reason, str) and reason.strip():
                reasons[gid] = reason.strip()
                if len(reason.split()) > 12:
                    problems.append(f"long_reason:{r}")
    for r in al:
        if r not in rmap:
            problems.append(f"unknown_reference:{r}")
    return {"alignment": out, "content": grades, "reasons": reasons, "flags": flags}, problems


def call(model: str, prompt: str, max_tokens: int, key: str, timeout: int) -> tuple[int, str]:
    req = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
    }
    r = urllib.request.Request(URL, data=json.dumps(req).encode(), method="POST",
                               headers={"Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def judge_task(model: str, task: dict, key: str, a, raw_dir: Path) -> dict:
    prompt, rmap, cmap = build_prompt(task)
    attempts, result = [], {"parsed": None, "problems": ["no_attempt"]}
    budget = a.max_tokens
    for n in range(1, a.max_attempts + 1):
        t0 = time.monotonic()
        try:
            status, body = call(model, prompt, budget, key, a.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            status, body = 0, f"{type(e).__name__}: {e}"
        attempts.append({"attempt": n, "max_tokens": budget, "http_status": status,
                         "latency_ms": int((time.monotonic() - t0) * 1000), "body": body})
        if status != 200:
            result = {"parsed": None, "problems": [f"http_{status}"]}
            time.sleep(min(30, 2 ** n))
            continue
        try:
            js = json.loads(body)
            choice = js["choices"][0]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            result = {"parsed": None, "problems": ["bad_response_body"]}
            continue
        finish = choice.get("finish_reason")
        meta = {"finish_reason": finish, "served_model": js.get("model"),
                "provider": js.get("provider"), "usage": js.get("usage"), "attempts": n}
        if finish == "length":                       # checked before parsing
            result = {"parsed": None, "problems": ["truncated"], **meta}
            budget *= 2
            continue
        parsed, problems = parse_alignment((choice.get("message") or {}).get("content") or "", rmap, cmap)
        result = {"parsed": parsed, "problems": problems, **meta}
        if parsed is not None:
            break
    (raw_dir / f"{task['task_id']}.json").write_text(json.dumps(
        {"task_id": task["task_id"], "judge": model, "prompt": prompt, "attempts": attempts},
        ensure_ascii=False, indent=1) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", type=Path, default=HERE / "tasks.json")
    ap.add_argument("--out", type=Path, default=HERE / "judge_runs_v5")
    ap.add_argument("--judges", nargs="+", default=None, metavar="MODEL_ID",
                    help="OpenRouter model ids (default: the three frontier ids in release/predictions/manifest.json)")
    ap.add_argument("--only", nargs="+", default=None, metavar="TASK_ID", help="restrict to these task ids")
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--redo", action="store_true", help="re-judge tasks that already have a parsed alignment")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print 2 prompts and the plan; no network")
    mode.add_argument("--execute", action="store_true", help="send the calls (costs money)")
    a = ap.parse_args()

    doc = json.loads(a.tasks.read_text())
    tasks = [t for t in doc["tasks"] if not a.only or t["task_id"] in a.only]
    judges = a.judges or default_judges()

    if a.dry_run:
        tin = tout = mx = 0
        for t in tasks:
            tin += est_tokens(SYSTEM_PROMPT) + est_tokens(build_prompt(t)[0])
            o = est_output_tokens(t)
            tout += o
            mx = max(mx, 12 + 36 * len(t["gold"]))        # every pair graded with a reason
        shown = tasks[:1] + [t for t in tasks if t["axis"] != tasks[0]["axis"]][:1] if tasks else []
        for t in shown:
            print(f"===== PROMPT for task {t['task_id']} ({t['axis']}) =====")
            print(f"[system] {SYSTEM_PROMPT}\n[user]\n{build_prompt(t)[0]}\n")
        print("===== PLAN (dry run, nothing sent) =====")
        print(f"judges ({len(judges)}): {', '.join(judges)}")
        print(f"tasks: {len(tasks)}   calls: {len(tasks)} x {len(judges)} = {len(tasks) * len(judges)}"
              f"   (plus retries only on error/truncation, max {a.max_attempts} attempts each)")
        print(f"rough tokens per judge: {tin} in + {tout} out  "
              f"(4 chars/token; output excludes any hidden reasoning tokens)")
        print(f"rough tokens total:     {tin * len(judges)} in + {tout * len(judges)} out")
        print(f"largest single answer if every pair carried a reason: ~{mx} tokens "
              f"(max_tokens = {a.max_tokens}, doubled on truncation)")
        return 0

    key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY not set")
    for model in judges:
        jdir = a.out / slug(model)
        raw = jdir / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        path = jdir / "alignments.json"
        run = json.loads(path.read_text()) if path.exists() else {}
        if run and run.get("schema") != SCHEMA:
            sys.exit(f"{path} was written by an older harness (different grade set). "
                     f"Use a fresh --out directory; nothing was overwritten.")
        run.update({"schema": SCHEMA, "judge": model, "tasks_hash": doc["meta"]["tasks_hash"]})
        for k in ("alignments", "content", "reasons", "flags", "info"):
            run.setdefault(k, {})
        for i, t in enumerate(tasks, 1):
            tid = t["task_id"]
            if tid in run["alignments"] and not a.redo:
                continue
            res = judge_task(model, t, key, a, raw)
            parsed = res.pop("parsed")
            for k, src in (("alignments", "alignment"), ("content", "content"), ("reasons", "reasons"), ("flags", "flags")):
                if parsed is not None:
                    run[k][tid] = parsed[src]
                else:
                    run[k].pop(tid, None)
            run["info"][tid] = res
            path.write_text(json.dumps(run, ensure_ascii=False, indent=1) + "\n")
            print(f"[{model}] {i}/{len(tasks)} {tid}: "
                  f"{'ok' if parsed is not None else 'FAILED'} {res.get('problems') or ''}", flush=True)
        n_ok = sum(1 for t in tasks if t["task_id"] in run["alignments"])
        print(f"[{model}] parsed {n_ok}/{len(tasks)} tasks -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
