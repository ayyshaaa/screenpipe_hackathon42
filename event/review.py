#!/usr/bin/env python3
"""Review page (http://localhost:4300): a person confirms or rejects each proposed task.

  python3 review.py                          # review concentration_runs.json
  python3 review.py --runs other.json
  python3 review.py --truth-runs             # look at the answer key (synthetic data only)
  python3 review.py --show-truth             # add answer-key badges next to each session

For each task: rename it, see its runs side by side, remove wrong sessions, split a run that is
really two runs done back to back, classify extra sessions as exception / troubleshooting / normal,
then Confirm or Reject.
Only confirmed tasks are written to reviewed_runs.json (input of export_starter.py).
Nothing is confirmed automatically.
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import (DB_PATH, DESCRIPTIONS_PATH, REVIEWED_PATH, RUNS_PATH, TRUTH_RUNS_PATH, TRUTH_SESSIONS_PATH,
                    load_sessions, read_json, run_minutes, write_json)

STATE_PATH = "review_state.json"
KINDS = ["normal", "exception", "troubleshooting", "unclassified"]


def build_data(args):
    runs = read_json(args.runs)
    sessions = {s["session_id"]: s for s in load_sessions(args.db)}
    truth = read_json(TRUTH_SESSIONS_PATH) if args.show_truth and os.path.exists(TRUTH_SESSIONS_PATH) else {}
    descriptions = read_json(DESCRIPTIONS_PATH) if os.path.exists(DESCRIPTIONS_PATH) else {}
    tasks = {}
    for r in runs:
        missing = [sid for sid in r["sessions"] if sid not in sessions]
        if missing:
            raise SystemExit(f"{args.runs} mentions sessions not in {args.db} (e.g. {missing[0]}): re-run the pipeline")
        extra = set(r.get("extra_sessions", []))
        kinds = r.get("session_kinds", {})
        task = tasks.setdefault(r["task"], {"name": r["task"], "runs": [], "description": descriptions.get(r["task"])})
        task["runs"].append({"run": r["run"], "minutes": r["minutes"], "sessions": [{
            "id": sid,
            "start": sessions[sid]["start_ts"], "minutes": sessions[sid]["minutes"],
            "app": sessions[sid]["app"], "window": sessions[sid]["window"], "text": sessions[sid]["text"][:600],  # keep the page light
            "sources": sessions[sid]["source_ids"],
            "extra": sid in extra, "share": r.get("step_share", {}).get(sid, ""),
            "kind": kinds.get(sid) or ("unclassified" if sid in extra else "normal"),
            "truth": truth.get(sid),
        } for sid in r["sessions"]]})
    return {"source": args.runs, "tasks": list(tasks.values())}


def save(args, data, decisions):
    """decisions: {task: {status, name, removed: [ids], kinds: {id: kind}, splits: [ids]}}
    A session in `splits` starts a new run: run 2026-09-08 split once gives 2026-09-08 and 2026-09-08.2."""
    write_json(STATE_PATH, {"source": args.runs, "decisions": decisions})
    sessions = {s["session_id"]: s for s in load_sessions(args.db)}
    out = []
    for task in data["tasks"]:
        d = decisions.get(task["name"], {})
        if d.get("status") != "confirmed":
            continue
        removed, splits = set(d.get("removed", [])), set(d.get("splits", []))
        for run in task["runs"]:
            parts = [[]]
            for s in run["sessions"]:
                if s["id"] in splits and parts[-1]:
                    parts.append([])
                parts[-1].append(s)
            for i, part in enumerate(parts):
                kept = [s for s in part if s["id"] not in removed]
                if not kept:
                    continue
                out.append({
                    "task": (d.get("name") or task["name"]).strip(),
                    "proposed_as": task["name"],  # links back to task_descriptions.json
                    "run": run["run"] if i == 0 else f"{run['run']}.{i + 1}",
                    "sessions": [s["id"] for s in kept],
                    "minutes": run_minutes([sessions[s["id"]] for s in part], removed),
                    "session_kinds": {s["id"]: d.get("kinds", {}).get(s["id"], s["kind"]) for s in kept},
                })
    write_json(REVIEWED_PATH, out)
    return len(out)


PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review.html")  # read on every request: edit it, press F5


def make_handler(args, data):
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.1 keeps the connection open after the reply. With HTTP/1.0 the server closes it at
        # once, and Windows -> WSL localhost forwarding can turn that into ERR_CONNECTION_RESET.
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path == "/":
                with open(PAGE_PATH, encoding="utf-8") as f:
                    return self.send(f.read().encode(), "text/html; charset=utf-8")
            if self.path == "/api/data":
                state = read_json(STATE_PATH) if os.path.exists(STATE_PATH) else {}
                decisions = state.get("decisions", {}) if state.get("source") == args.runs else {}
                return self.send(json.dumps({"data": data, "decisions": decisions}).encode(), "application/json")
            self.send(b"not found", "text/plain", 404)

        def do_POST(self):
            if self.path != "/api/save":
                return self.send(b"not found", "text/plain", 404)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                n = save(args, data, json.loads(body))
                args.saved = n
                reply = {"runs": n}
            except Exception as e:  # show the reason on the page instead of a silent failure
                reply = {"error": f"save failed: {e}"}
            self.send(json.dumps(reply).encode(), "application/json")

        def send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", default=RUNS_PATH)
    p.add_argument("--truth-runs", action="store_true", help=f"review {TRUTH_RUNS_PATH} (answer key)")
    p.add_argument("--show-truth", action="store_true", help="answer-key badges (synthetic data only)")
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--port", type=int, default=4300)
    args = p.parse_args()
    if args.truth_runs:
        args.runs = TRUTH_RUNS_PATH
    data = build_data(args)
    args.saved = None  # confirmed runs written by the last Save of this session
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args, data))
    except OSError as e:
        sys.exit(f"review: port {args.port} is not free ({e.strerror}). Is the review page already running? "
                 f"Stop it, or use --port (make review REVIEW_PORT=...).")
    print(f"review page for {args.runs}: http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if args.saved is None:
            print(f"\nreview stopped. Nothing saved in this session: {REVIEWED_PATH} is unchanged.")
        else:
            print(f"\nreview stopped. Last save: {args.saved} confirmed runs in {REVIEWED_PATH}.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
