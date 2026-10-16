#!/usr/bin/env python3
"""Answer key for the SYNTHETIC data. Scoring only: never feed these files into the pipeline.

Reads trail.db sessions + fake_data/story.json truth (per capture) and writes:
  fake_data/session_truth.json  session_id -> {category, task, step, run, kind, purity}
  fake_data/truth_runs.json     the perfect throught_runs.json (same format + session_kinds)

Run it again every time you re-run ingest: session IDs come from trail.db.
"""
import argparse
from collections import Counter, defaultdict

import fake_story
from common import (DB_PATH, TRUTH_RUNS_PATH, TRUTH_SESSIONS_PATH, load_sessions, read_json,
                    run_minutes, write_json)


def label_sessions(sessions, capture_truth):
    """A session takes the most common label of its captures (purity = share that agrees)."""
    out = {}
    for s in sessions:
        labels = [capture_truth[c] for c in s["source_ids"] if c in capture_truth]
        if not labels:
            out[s["session_id"]] = {"category": "unknown", "task": None, "step": None, "run": None, "kind": None, "purity": 0}
            continue
        counts = Counter(tuple(sorted(l.items())) for l in labels)
        best, n = counts.most_common(1)[0]
        out[s["session_id"]] = dict(best, purity=round(n / len(labels), 2))
    return out


def truth_runs(sessions, truth):
    by_run = defaultdict(list)
    for s in sessions:
        t = truth[s["session_id"]]
        if t["category"] == "task":
            by_run[(t["task"], t["run"])].append(s)
    runs = []
    for (task, run), ss in by_run.items():
        runs.append({"task": task, "run": run, "sessions": [s["session_id"] for s in ss],
                     "minutes": run_minutes(ss),
                     "session_kinds": {s["session_id"]: truth[s["session_id"]]["kind"] for s in ss}})
    total = defaultdict(float)
    for r in runs:
        total[r["task"]] += r["minutes"]
    runs.sort(key=lambda r: (-total[r["task"]], r["task"], r["run"]))
    return runs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=DB_PATH)
    args = p.parse_args()

    sessions = load_sessions(args.db)
    truth = label_sessions(sessions, read_json(fake_story.OUT)["truth"])
    runs = truth_runs(sessions, truth)
    write_json(TRUTH_SESSIONS_PATH, truth)
    write_json(TRUTH_RUNS_PATH, runs)

    print(f"{len(truth)} sessions labelled -> {TRUTH_SESSIONS_PATH}")
    print("categories:", dict(Counter(t["category"] for t in truth.values())))
    for task, n in Counter(r["task"] for r in runs).items():
        mins = sum(r["minutes"] for r in runs if r["task"] == task)
        print(f"  {task}: {n} runs, {mins:.1f} observed minutes")
    mixed = [sid for sid, t in truth.items() if t["purity"] < 1]
    if mixed:
        print(f"  note: {len(mixed)} sessions mix captures with different labels (purity < 1)")


if __name__ == "__main__":
    main()
