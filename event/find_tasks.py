#!/usr/bin/env python3
"""Sessions + embeddings -> step types -> candidate tasks and their runs -> concentration_runs.json

The rule, in plain words:
  1. "Same step?"  two sessions are the same kind of step if cosine >= --threshold.
     Sessions are grouped into step types (leader clustering: join the closest group, else start one).
  2. Two step types belong to one task if, on >= --min-days different days, they happen
     within --window-min minutes of each other, in a consistent order (>= --min-order),
     and they usually come together (co-occurring days / days either one appears >= --min-support).
  3. Linked step types form a candidate task. Each day's cluster of its steps is one run.
     Sessions inside a run that are not one of its steps are kept as "extra" for the reviewer
     (possible exception, troubleshooting, or noise to remove).

  python3 find_tasks.py                  # threshold picked from the embedding model (common.DEFAULT_THRESHOLDS)
  python3 find_tasks.py --threshold 0.85
  python3 find_tasks.py --sweep          # Sunday's exercise: precision/recall per threshold (needs answer key)
  python3 find_tasks.py --score          # compare the result with the answer key
"""
import argparse
import os
import re
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np

from common import (DB_PATH, DEFAULT_THRESHOLDS, FALLBACK_THRESHOLD, RUNS_PATH, TRUTH_RUNS_PATH, TRUTH_SESSIONS_PATH, load_sessions, local_day,
                    parse_ts, read_json, run_minutes, write_json)


# ---------- loading ----------

def load(db, emb_path):
    sessions = load_sessions(db)
    data = np.load(emb_path)
    index = {sid: i for i, sid in enumerate(data["ids"].tolist())}
    missing = [s["session_id"] for s in sessions if s["session_id"] not in index]
    if missing:
        raise SystemExit(f"{len(missing)} sessions have no embedding: run embed.py again after ingest")
    vectors = np.stack([data["vectors"][index[s["session_id"]]] for s in sessions])
    for s in sessions:
        s["day"] = local_day(s["start_ts"])
        s["t0"], s["t1"] = parse_ts(s["start_ts"]), parse_ts(s["end_ts"])
    return sessions, vectors, str(data["model"])


def default_threshold(model):
    if model in DEFAULT_THRESHOLDS:
        return DEFAULT_THRESHOLDS[model], f"default for {model}"
    print(f"WARNING: no tested threshold for model {model!r}: using {FALLBACK_THRESHOLD}, "
          "check it with --sweep (synthetic data) or set --threshold")
    return FALLBACK_THRESHOLD, "fallback, untested model"


# ---------- 1. step types ----------

def cluster(vectors, threshold):
    """Leader clustering, then one clean-up pass that moves each session to its closest group."""
    labels, sums = [], []
    for v in vectors:
        if sums:
            cents = np.stack(sums) / np.linalg.norm(np.stack(sums), axis=1, keepdims=True)
            sims = cents @ v
            best = int(np.argmax(sims))
            if sims[best] >= threshold:
                labels.append(best)
                sums[best] = sums[best] + v
                continue
        labels.append(len(sums))
        sums.append(v.copy())
    cents = np.stack(sums) / np.linalg.norm(np.stack(sums), axis=1, keepdims=True)
    sims = vectors @ cents.T
    for i in range(len(labels)):
        best = int(np.argmax(sims[i]))
        if sims[i, best] >= threshold:
            labels[i] = best
    return labels


# ---------- 2. linked step types ----------

def linked_pairs(sessions, labels, args):
    by_type_day = defaultdict(lambda: defaultdict(list))
    for s, lab in zip(sessions, labels):
        by_type_day[lab][s["day"]].append(s)
    recurring = [t for t, days in by_type_day.items() if len(days) >= args.min_days]
    window = args.window_min * 60
    pairs = []
    for a, b in combinations(recurring, 2):
        days_a, days_b = by_type_day[a], by_type_day[b]
        together, a_first = 0, 0
        for day in set(days_a) & set(days_b):
            # closest pair of sessions (one of each type) that day
            gap, sa, sb = min(((abs((x["t0"] - y["t0"]).total_seconds()), x, y)
                               for x in days_a[day] for y in days_b[day]), key=lambda g: g[0])
            if gap <= window:
                together += 1
                a_first += sa["t0"] <= sb["t0"]
        if together < args.min_days:
            continue
        support = together / max(len(days_a), len(days_b))
        order = max(a_first, together - a_first) / together
        if support >= args.min_support and order >= args.min_order:
            pairs.append((a, b))
    return pairs


def components(pairs):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups = defaultdict(set)
    for x in list(parent):
        groups[find(x)].add(x)
    return list(groups.values())


# ---------- 3. runs ----------

def type_name(sessions, labels, t):
    windows = Counter(re.sub(r"\d+", "#", s["window"]) for s, lab in zip(sessions, labels) if lab == t)
    return windows.most_common(1)[0][0] or "untitled"


def find_runs(sessions, labels, types, args, taken):
    core = sorted((s for s, lab in zip(sessions, labels) if lab in types), key=lambda s: s["t0"])
    groups, cur = [], []
    for s in core:
        if cur and (s["day"] != cur[0]["day"] or (s["t0"] - cur[0]["t0"]).total_seconds() > args.window_min * 60):
            groups.append(cur)
            cur = []
        cur.append(s)
    if cur:
        groups.append(cur)
    label_of = {s["session_id"]: lab for s, lab in zip(sessions, labels)}
    runs = []
    for g in groups:
        if len({label_of[s["session_id"]] for s in g}) < 2:
            continue
        start, end = g[0]["t0"], max(s["t1"] for s in g)
        core_ids = {s["session_id"] for s in g}
        extras = [s for s in sessions if s["session_id"] not in core_ids and start <= s["t0"] <= end]
        members = sorted(g + extras, key=lambda s: s["t0"])
        if any(s["session_id"] in taken for s in members):
            members = [s for s in members if s["session_id"] not in taken]
        runs.append({"day": g[0]["day"], "sessions": members, "extra": {s["session_id"] for s in extras}})
    return runs


def build(sessions, vectors, args):
    labels = cluster(vectors, args.threshold)
    label_of = {s["session_id"]: lab for s, lab in zip(sessions, labels)}
    tasks, taken = [], set()
    for types in components(linked_pairs(sessions, labels, args)):
        runs = find_runs(sessions, labels, types, args, taken)
        if len({r["day"] for r in runs}) < args.min_days:
            continue
        for r in runs:
            taken.update(s["session_id"] for s in r["sessions"])
        # order step types by their usual position inside a run
        pos = defaultdict(list)
        for r in runs:
            core = [s for s in r["sessions"] if s["session_id"] not in r["extra"]]
            for i, s in enumerate(core):
                pos[label_of[s["session_id"]]].append(i / max(len(core) - 1, 1))
        ordered = sorted(types, key=lambda t: np.median(pos[t]) if pos[t] else 1)
        name = f"{type_name(sessions, labels, ordered[0])} → {type_name(sessions, labels, ordered[-1])}"
        tasks.append({"name": name, "runs": runs})

    out, n_runs = [], defaultdict(int)
    for task in tasks:
        type_runs = Counter()
        for r in task["runs"]:
            type_runs.update({label_of[s["session_id"]] for s in r["sessions"]})
        for r in task["runs"]:
            if not r["sessions"]:
                continue
            n_runs[(task["name"], r["day"])] += 1
            suffix = "" if n_runs[(task["name"], r["day"])] == 1 else f"-{n_runs[(task['name'], r['day'])]}"
            out.append({
                "task": task["name"],
                "run": f"{r['day']}{suffix}",
                "sessions": [s["session_id"] for s in r["sessions"]],
                "minutes": run_minutes(r["sessions"]),
                "extra_sessions": sorted(r["extra"] & {s["session_id"] for s in r["sessions"]}),
                "step_share": {s["session_id"]: f"{type_runs[label_of[s['session_id']]]}/{len(task['runs'])}"
                               for s in r["sessions"]},
            })
    total = defaultdict(float)
    for r in out:
        total[r["task"]] += r["minutes"]
    out.sort(key=lambda r: (-total[r["task"]], r["task"], r["run"]))
    return out, labels


# ---------- answer-key helpers (synthetic data only) ----------

def sweep(sessions, vectors):
    truth = read_json(TRUTH_SESSIONS_PATH)
    key = [(truth[s["session_id"]]["task"], truth[s["session_id"]]["step"])
           if truth[s["session_id"]]["category"] == "task" else None for s in sessions]
    sims = vectors @ vectors.T
    days = [s["day"] for s in sessions]
    i, j = np.triu_indices(len(sessions), 1)
    keep = np.array([days[a] != days[b] for a, b in zip(i, j)])
    i, j = i[keep], j[keep]
    same = np.array([key[a] is not None and key[a] == key[b] for a, b in zip(i, j)])
    print("threshold  precision  recall   (pairs from different days; same = same task and step)")
    for thr in np.r_[np.arange(0.3, 0.85, 0.1), np.arange(0.9, 0.995, 0.01)]:
        pred = sims[i, j] >= thr
        tp = int((pred & same).sum())
        prec = tp / max(int(pred.sum()), 1)
        rec = tp / max(int(same.sum()), 1)
        print(f"  {thr:.2f}      {prec:.2f}      {rec:.2f}")


def score(runs):
    truth = read_json(TRUTH_SESSIONS_PATH)
    truth_runs = read_json(TRUTH_RUNS_PATH)
    print("\nscore against the answer key:")
    for task in dict.fromkeys(r["task"] for r in runs):
        ids = [sid for r in runs if r["task"] == task for sid in r["sessions"]]
        top, n = Counter(truth[sid]["task"] or truth[sid]["category"] for sid in ids).most_common(1)[0]
        n_runs = sum(r["task"] == task for r in runs)
        verdict = "TASK" if top in ("weekly_report", "refund_check", "partner_onboard") else "FALSE POSITIVE"
        print(f"  {verdict:14} {task}  ({n_runs} runs, mostly {top}: {n}/{len(ids)} sessions)")
    for tr_task in dict.fromkeys(r["task"] for r in truth_runs):
        expected = [set(r["sessions"]) for r in truth_runs if r["task"] == tr_task]
        found = [set(r["sessions"]) for r in runs]
        hit = sum(any(len(e & f) / len(e) >= 0.5 for f in found) for e in expected)
        print(f"  {tr_task}: {hit}/{len(expected)} true runs found")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--embeddings", default="embeddings.npz")
    p.add_argument("--threshold", type=float,
                   help="'same step?' cosine threshold (default: picked from the embedding model)")
    p.add_argument("--window-min", type=float, default=60)
    p.add_argument("--min-days", type=int, default=3)
    p.add_argument("--min-support", type=float, default=0.6)
    p.add_argument("--min-order", type=float, default=0.8)
    p.add_argument("--out", default=RUNS_PATH)
    p.add_argument("--sweep", action="store_true")
    p.add_argument("--score", action="store_true")
    args = p.parse_args()

    sessions, vectors, model = load(args.db, args.embeddings)
    if args.sweep:
        return sweep(sessions, vectors)
    why = "set by --threshold"
    if args.threshold is None:
        args.threshold, why = default_threshold(model)
    runs, labels = build(sessions, vectors, args)
    write_json(args.out, runs)
    print(f"{len(set(labels))} step types from {len(sessions)} sessions (threshold {args.threshold}, {why})")
    for task in dict.fromkeys(r["task"] for r in runs):
        rs = [r for r in runs if r["task"] == task]
        print(f"  {task}: {len(rs)} runs, {sum(r['minutes'] for r in rs):.1f} observed minutes")
    print(f"-> {args.out}")
    if args.score and os.path.exists(TRUTH_SESSIONS_PATH):
        score(runs)


if __name__ == "__main__":
    main()
