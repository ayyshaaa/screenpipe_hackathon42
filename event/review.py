#!/usr/bin/env python3
"""Review page (http://localhost:4300): a person confirms or rejects each proposed task.

  python3 review.py                          # review concentration_runs.json
  python3 review.py --runs other.json
  python3 review.py --truth-runs             # look at the answer key (synthetic data only)
  python3 review.py --show-truth             # add answer-key badges next to each session

For each task: rename it, see its runs side by side, remove wrong sessions, classify extra
sessions as exception / troubleshooting / normal, then Confirm or Reject.
Only confirmed tasks are written to reviewed_runs.json (input of export_starter.py).
Nothing is confirmed automatically.
"""
import argparse
import json
import os
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
    """decisions: {task: {status, name, removed: [ids], kinds: {id: kind}}}"""
    write_json(STATE_PATH, {"source": args.runs, "decisions": decisions})
    sessions = {s["session_id"]: s for s in load_sessions(args.db)}
    out = []
    for task in data["tasks"]:
        d = decisions.get(task["name"], {})
        if d.get("status") != "confirmed":
            continue
        removed = set(d.get("removed", []))
        for run in task["runs"]:
            kept = [s for s in run["sessions"] if s["id"] not in removed]
            if not kept:
                continue
            out.append({
                "task": (d.get("name") or task["name"]).strip(),
                "proposed_as": task["name"],  # links back to task_descriptions.json
                "run": run["run"],
                "sessions": [s["id"] for s in kept],
                "minutes": run_minutes([sessions[s["id"]] for s in kept]),
                "session_kinds": {s["id"]: d.get("kinds", {}).get(s["id"], s["kind"]) for s in kept},
            })
    write_json(REVIEWED_PATH, out)
    return len(out)


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CONCENTRATION review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e2e0da;--accent:#3a5bd9;--ok:#1f7a4d;--bad:#b3261e;--warn:#9a6200;--extra:#fff6e0}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e22;--ink:#ececf0;--muted:#9a9aa3;--line:#33333a;--accent:#8aa2ff;--ok:#5fd39a;--bad:#ff8a80;--warn:#f0b54a;--extra:#2c2618}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--ink)}
header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0}.muted{color:var(--muted)}main{padding:16px 20px;display:grid;gap:18px}
.task{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.task.confirmed{border-color:var(--ok)}.task.rejected{opacity:.55}
.top{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top input{flex:1;min-width:240px;font:600 15px system-ui;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--ink)}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.ok{border-color:var(--ok);color:var(--ok)}button.bad{border-color:var(--bad);color:var(--bad)}button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.runs{display:flex;gap:10px;overflow-x:auto;padding-top:10px}.run{min-width:280px;max-width:320px;flex:0 0 auto;border:1px solid var(--line);border-radius:8px;padding:8px}
.run h3{font-size:13px;margin:0 0 6px}.s{border-top:1px solid var(--line);padding:6px 0}.s.extra{background:var(--extra);margin:0 -8px;padding:6px 8px}
.s.removed{text-decoration:line-through;opacity:.45}.w{font-weight:600}.txt{white-space:pre-wrap;font-size:12px;color:var(--muted);max-height:3.2em;overflow:hidden;cursor:pointer}.txt.open{max-height:none}
.row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12px}select{font:inherit;font-size:12px}
.badge{font-size:11px;padding:1px 6px;border-radius:10px;border:1px solid var(--line)}.badge.truth{border-style:dashed}
.warn{color:var(--warn)}.desc{font-size:12px;margin-top:6px}.desc li{margin:2px 0}
</style></head><body>
<header><h1>CONCENTRATION · review proposed tasks</h1><span class="muted" id="src"></span><span style="flex:1"></span>
<span id="status" class="muted"></span><button class="primary" id="save">Save decisions</button></header>
<main id="tasks"></main>
<script>
const el=(t,p={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(p)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v)}for(const k of kids)e.append(k);return e};
let data,dec={};
const D=t=>dec[t]??={status:'pending',name:t,removed:[],kinds:{}};
const time=ts=>new Date(ts).toLocaleString('en-GB',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
function render(){
  const root=document.getElementById('tasks');root.replaceChildren();
  data.tasks.forEach(task=>{
    const d=D(task.name);
    const total=task.runs.reduce((n,r)=>n+r.minutes,0);
    const pending=task.runs.flatMap(r=>r.sessions).filter(s=>!d.removed.includes(s.id)&&(d.kinds[s.id]??s.kind)==='unclassified').length;
    const name=el('input',{value:d.name,oninput:e=>{d.name=e.target.value}});
    const card=el('section',{class:'task '+d.status},
      el('div',{class:'top'},name,
        el('span',{class:'muted'},`${task.runs.length} runs · ${total.toFixed(1)} observed min`),
        el('button',{class:'ok',onclick:()=>{if(pending){alert(pending+' extra session(s) still unclassified: classify or remove them first.');return}d.status='confirmed';render()}},'Confirm task'),
        el('button',{class:'bad',onclick:()=>{d.status='rejected';render()}},'Reject (not a task)'),
        el('span',{class:'badge'},d.status)),
      pending?el('div',{class:'warn row'},`${pending} highlighted session(s) are not regular steps: classify as exception / troubleshooting / normal, or remove.`):'');
    if(task.description){const ds=task.description;
      card.append(el('div',{class:'desc'},el('span',{class:'muted'},'Local LLM suggests: '),el('b',{},ds.name||''),' ',
        el('button',{onclick:()=>{d.name=ds.name;render()}},'use name'),
        el('ol',{},...(ds.steps||[]).map(st=>el('li',{},`${st.text} `,el('span',{class:'muted'},`[${st.kind}] “${st.quote}” — ${st.session_id}`))))))}
    const runs=el('div',{class:'runs'});
    task.runs.forEach(run=>{
      const box=el('div',{class:'run'},el('h3',{},`Run ${run.run} · ${run.minutes} min`));
      run.sessions.forEach(s=>{
        const removed=d.removed.includes(s.id);
        const kind=el('select',{onchange:e=>{d.kinds[s.id]=e.target.value;render()}},...['normal','exception','troubleshooting','unclassified'].map(k=>{const o=el('option',{value:k},k);if((d.kinds[s.id]??s.kind)===k)o.selected=true;return o}));
        const txt=el('div',{class:'txt',onclick:e=>e.target.classList.toggle('open')},s.text);
        box.append(el('div',{class:'s'+(s.extra?' extra':'')+(removed?' removed':'')},
          el('div',{class:'row'},el('span',{class:'w'},s.window||s.app)),
          el('div',{class:'row muted'},`${time(s.start)} · ${s.minutes} min · ${s.app}`,s.share?el('span',{class:'badge',title:'runs of this task that contain this kind of step'},'in '+s.share+' runs'):''),
          txt,
          el('div',{class:'row'},kind,
            el('button',{onclick:()=>{d.removed=removed?d.removed.filter(x=>x!==s.id):[...d.removed,s.id];render()}},removed?'restore':'remove'),
            el('span',{class:'muted',title:s.sources.join(', ')},`${s.id} · ${s.sources.length} captures`),
            s.truth?el('span',{class:'badge truth',title:'answer key, synthetic data only'},`key: ${s.truth.task||s.truth.category}${s.truth.kind&&s.truth.kind!=='normal'?' · '+s.truth.kind:''}`):'')));
      });
      runs.append(box);
    });
    card.append(runs);root.append(card);
  });
}
async function load(){
  let j;
  for(let attempt=1;attempt<=3&&!j;attempt++){  // WSL's localhost bridge sometimes resets a connection: retry
    try{const r=await fetch('/api/data',{cache:'no-store'});j=await r.json()}
    catch(e){document.getElementById('status').textContent=`loading failed (${e.message}), retry ${attempt}/3…`;await new Promise(ok=>setTimeout(ok,700))}
  }
  if(!j){document.getElementById('status').textContent='could not load the data: see the terminal running review.py';return}
  document.getElementById('status').textContent='';
  data=j.data;dec=j.decisions||{};
  document.getElementById('src').textContent='source: '+data.source;render();
}
document.getElementById('save').onclick=async()=>{
  const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(dec)});
  const j=await r.json();document.getElementById('status').textContent=j.error||`saved · ${j.runs} confirmed runs → reviewed_runs.json`;
};
load();
</script></body></html>"""


def make_handler(args, data):
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.1 keeps the connection open after the reply. With HTTP/1.0 the server closes it at
        # once, and Windows -> WSL localhost forwarding can turn that into ERR_CONNECTION_RESET.
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path == "/":
                return self.send(PAGE.encode(), "text/html; charset=utf-8")
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
    print(f"review page for {args.runs}: http://localhost:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args, data)).serve_forever()


if __name__ == "__main__":
    main()
