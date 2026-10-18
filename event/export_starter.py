#!/usr/bin/env python3
"""Confirmed runs -> files for the screenpipe hackathon-starter.

  python3 export_starter.py                 # from reviewed_runs.json (only what a person confirmed)
  python3 export_starter.py --truth-runs    # the perfect answer (synthetic answer key)

Writes:
  starter_records.json  one record per session: "Task: / Run: / Minutes:" lines.
                        Sessions of the same run repeat the same three lines, so the starter's
                        "duplicates count once" rule merges them and lists the session IDs as sources.
  desk_records.json     the sessions of ONE run, as plain evidence for the review desk
  desk_draft.json       the same run as a procedure draft (steps, quotes, kinds) for the review desk

Then, in ../hackathon-starter:
  bun run repetition --input ../event/starter_records.json
  bun start --draft ../event/desk_draft.json      (or --input ../event/desk_records.json)
"""
import argparse
import os
import re
from collections import defaultdict

from common import (DB_PATH, DESCRIPTIONS_PATH, REVIEWED_PATH, TRUTH_RUNS_PATH, load_sessions, read_json,
                    write_json)

MAX_RECORDS = 1000          # starter limit
MAX_BYTES = 2 * 1024 * 1024  # starter limit


def minutes_str(m):
    """The starter accepts '12' or '12.5' or '12.25', > 0 and <= 1440."""
    return f"{m:.2f}".rstrip("0").rstrip(".")


def one_line(text, n=160):
    return re.sub(r"\s+", " ", text).strip()[:n]


def starter_records(runs, sessions):
    records, skipped = [], []
    for r in runs:
        m = round(r["minutes"], 2)
        if not 0 < m <= 1440:
            skipped.append(f"{r['task']} / {r['run']} ({r['minutes']} min)")
            continue
        head = f"Task: {one_line(r['task'], 120)}\nRun: {r['run']}\nMinutes: {minutes_str(m)}"
        for sid in r["sessions"]:
            s = sessions[sid]
            records.append({"id": sid, "timestamp": s["start_ts"], "app": "CONCENTRATION (reviewed)",
                            "text": f"{head}\nSession: {one_line(s['window'], 80)} | {one_line(s['text'])}"})
    return records, skipped


def frame_link(s):
    ocr = [x for x in s["source_ids"] if x.startswith("ocr:")]
    return f"screenpipe://frame/{ocr[0].split(':', 1)[1]}" if ocr else None


def pick_desk_run(runs, descriptions, wanted):
    if wanted:
        match = [r for r in runs if r["run"] == wanted]
        if not match:
            raise SystemExit(f"--desk-run {wanted} not found")
        return match[0]
    # the run of the top task with the most exceptions / troubleshooting: shows the desk's classification best
    top = runs[0]["task"]  # runs are sorted by observed minutes
    return max((r for r in runs if r["task"] == top),
               key=lambda r: (sum(k != "normal" for k in r.get("session_kinds", {}).values()), r["run"]))


def window_key(window):
    return re.sub(r"\d+", "#", window or "")


def desk_files(run, sessions, descriptions, n_runs, total_minutes):
    evidence = []
    for sid in run["sessions"]:
        s = sessions[sid]
        rec = {"id": sid, "timestamp": s["start_ts"], "app": s["app"], "text": s["text"][:50000]}
        if frame_link(s):
            rec["source"] = frame_link(s)
        evidence.append(rec)
    # LLM step texts were written for another run of the same task: match them by window
    # (digits ignored). The quote is re-checked against THIS session's text, else its first line is used.
    desc = descriptions.get(run.get("proposed_as", run["task"]), {})
    llm_step = {}
    for st in desc.get("steps", []):
        if st["session_id"] in sessions and st.get("kind") == "normal":
            llm_step.setdefault(window_key(sessions[st["session_id"]]["window"]), st)
    kinds = run.get("session_kinds", {})
    steps = []
    for rec in evidence:
        sid = rec["id"]
        st = llm_step.get(window_key(sessions[sid]["window"]))
        quote = st["quote"] if st and st["quote"] in rec["text"] else rec["text"].split("\n")[0]
        steps.append({"text": st["text"] if st else f"{sessions[sid]['window'] or rec['app']}",
                      "sourceId": sid, "quote": quote,
                      "kind": kinds.get(sid, "unclassified"),  # the reviewer's choice wins over the LLM's
                      "reviewed": False})
    draft = {
        "title": run["task"],
        "context": (f"Proposed by CONCENTRATION from {n_runs} confirmed runs ({total_minutes:.1f} observed minutes). "
                    f"This is run {run['run']}. Steps and kinds come from a person's review; check each against its evidence."),
        "revision": 1,
        "origin": "CONCENTRATION: repeated sessions found in screen history, confirmed by a person",
        "evidence": evidence,
        "steps": steps,
        "questions": [{"question": "What outcome, role and boundaries does this procedure cover?", "answer": ""},
                      {"question": "Are the steps marked exception or troubleshooting really outside the normal process?", "answer": ""}],
    }
    return evidence, draft


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", default=REVIEWED_PATH)
    p.add_argument("--truth-runs", action="store_true", help=f"export {TRUTH_RUNS_PATH} (answer key)")
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--desk-run", help="run ID to send to the review desk (default: picked automatically)")
    p.add_argument("--out-dir", default=".")
    args = p.parse_args()
    if args.truth_runs:
        args.runs = TRUTH_RUNS_PATH
    if not os.path.exists(args.runs):
        raise SystemExit(f"{args.runs} not found: confirm tasks on review.py and press Save first")

    runs = read_json(args.runs)
    if not runs:
        raise SystemExit(f"{args.runs} has no confirmed runs: nothing to export")
    sessions = {s["session_id"]: s for s in load_sessions(args.db)}
    descriptions = read_json(DESCRIPTIONS_PATH) if os.path.exists(DESCRIPTIONS_PATH) else {}

    seen = defaultdict(list)
    for r in runs:
        for sid in r["sessions"]:
            seen[sid].append(r["run"])
    clash = {sid: rs for sid, rs in seen.items() if len(rs) > 1}
    if clash:
        raise SystemExit(f"session {next(iter(clash))} is in several runs {next(iter(clash.values()))}: fix the review first")

    records, skipped = starter_records(runs, sessions)
    path = os.path.join(args.out_dir, "starter_records.json")
    write_json(path, records)
    size = os.path.getsize(path)
    if len(records) > MAX_RECORDS or size > MAX_BYTES:
        raise SystemExit(f"{len(records)} records / {size} bytes is over the starter's limits (1000 records, 2 MB)")
    print(f"{path}: {len(records)} records, {len({(r['task'], r['run']) for r in runs})} runs")
    for s in skipped:
        print(f"  skipped (minutes must be > 0 and <= 1440): {s}")

    run = pick_desk_run(runs, descriptions, args.desk_run)
    n_runs = sum(r["task"] == run["task"] for r in runs)
    total = sum(r["minutes"] for r in runs if r["task"] == run["task"])
    evidence, draft = desk_files(run, sessions, descriptions, n_runs, total)
    write_json(os.path.join(args.out_dir, "desk_records.json"), evidence)
    write_json(os.path.join(args.out_dir, "desk_draft.json"), draft)
    print(f"desk_records.json + desk_draft.json: run {run['run']} of '{run['task']}' ({len(evidence)} sessions)")
    here = os.path.abspath(args.out_dir)
    print("\nnext, in ~/hackathon-starter:")
    print(f"  bun run repetition --input {here}/starter_records.json")
    print(f"  bun start --draft {here}/desk_draft.json   # then open http://localhost:4242")


if __name__ == "__main__":
    main()
