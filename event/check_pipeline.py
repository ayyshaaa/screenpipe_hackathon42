#!/usr/bin/env python3
"""End-to-end test on the SYNTHETIC data, in a throwaway copy of the folder.

  python3 check_pipeline.py --threshold 0.8                     # JEV-2
  python3 check_pipeline.py --model hashing --threshold 0.6      # no model download needed
  python3 check_pipeline.py --starter ~/hackathon-starter        # also runs bun run repetition

Fails (exit 1) if: a hidden task is missed (< 80% of its runs), the 3 tasks are not ranked
weekly_report > refund_check > partner_onboard, a proposed task is mostly noise (chat, music, inbox),
or the exported records break the starter's rules. A recurring meeting being proposed is only a
warning: that false positive is what the human review step is for.
"""
import argparse
import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = ["weekly_report", "refund_check", "partner_onboard"]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(cmd, cwd):
    print("$", " ".join(cmd))
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode:
        print(res.stdout + res.stderr)
        sys.exit(f"FAILED: {' '.join(cmd)}")
    return res.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="VTXAI/VTX-JEV-2")
    p.add_argument("--threshold", type=float, default=0.8)
    p.add_argument("--starter", help="path to hackathon-starter, to run bun run repetition on the export")
    p.add_argument("--keep", action="store_true", help="keep the temp folder to inspect it")
    args = p.parse_args()
    if args.starter:
        args.starter = os.path.abspath(os.path.expanduser(args.starter))

    t0 = time.time()
    work = tempfile.mkdtemp(prefix="throught_check_")
    for f in glob.glob(os.path.join(HERE, "*.py")):
        shutil.copy(f, work)
    py = sys.executable
    failures, warnings = [], []
    port = free_port()
    server = None
    try:
        run([py, "fake_story.py"], work)
        server = subprocess.Popen([py, "fake_screenpipe.py", "serve", "--port", str(port)], cwd=work,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        run([py, "ingest.py", "--url", f"http://127.0.0.1:{port}", "--from", "2026-09-07", "--once"], work)
        run([py, "label_sessions.py"], work)
        run([py, "embed.py", "--model", args.model], work)
        print(run([py, "find_tasks.py", "--threshold", str(args.threshold), "--score"], work))

        sys.path.insert(0, work)
        from common import read_json
        os.chdir(work)
        runs, truth_runs = read_json("throught_runs.json"), read_json("fake_data/truth_runs.json")
        truth = read_json("fake_data/session_truth.json")

        # which hidden task does each proposed task mostly contain?
        proposed = {}
        for task in dict.fromkeys(r["task"] for r in runs):
            ids = [sid for r in runs if r["task"] == task for sid in r["sessions"]]
            proposed[task] = Counter(truth[s]["task"] or truth[s]["category"] for s in ids).most_common(1)[0][0]
        for task, what in proposed.items():
            if what == "noise":
                failures.append(f"noise proposed as a task: {task}")
            elif what not in EXPECTED:
                warnings.append(f"false positive for the reviewer to reject ({what}): {task}")

        for name in EXPECTED:
            expected = [set(r["sessions"]) for r in truth_runs if r["task"] == name]
            found = [set(r["sessions"]) for r in runs]
            hit = sum(any(len(e & f) / len(e) >= 0.5 for f in found) for e in expected)
            print(f"  {name}: {hit}/{len(expected)} runs found")
            if hit < 0.8 * len(expected):
                failures.append(f"{name}: only {hit}/{len(expected)} runs found")

        order = [proposed[t] for t in proposed if proposed[t] in EXPECTED]
        if order != EXPECTED:
            failures.append(f"ranking is {order}, expected {EXPECTED}")

        run([py, "export_starter.py", "--truth-runs"], work)
        records = read_json("starter_records.json")
        if len(records) > 1000 or len({r["id"] for r in records}) != len(records):
            failures.append("starter records: over 1000 or duplicate IDs")
        if args.starter:
            out = run(["bun", "run", "repetition", "--input", os.path.join(work, "starter_records.json")],
                      args.starter)
            pos = [out.find(f"### {n.replace('_', chr(92) + '_')}") for n in EXPECTED]
            if -1 in pos or pos != sorted(pos):
                failures.append("bun run repetition did not rank the 3 tasks as expected")
            else:
                print("  bun run repetition: 3 tasks ranked as expected")
    finally:
        if server:
            server.terminate()
        os.chdir(HERE)
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"kept {work}")

    for w in warnings:
        print("WARNING:", w)
    for f in failures:
        print("FAIL:", f)
    print(f"{'FAILED' if failures else 'PASSED'} in {time.time() - t0:.0f}s")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
