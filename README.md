# THROUGHT: finding repeated tasks in screen history

THROUGHT reads someone's screen history (from [screenpipe](https://screenpipe.com)), finds the tasks they
repeat (for example, "every Monday I build the KPI report"), and lists them by how much time they took.
**A person confirms or rejects every proposed task** before anything leaves the tool. The confirmed tasks
are then exported to the screenpipe `hackathon-starter`, which ranks them and turns one of them into a
reviewable procedure (SOP).

> **All data in `fake_data/` is SYNTHETIC.** It is a made-up month (7 Sep – 6 Oct 2026) of Inès, a
> product manager at a fictional food-delivery company called Tavola. Say so in every demo.

---

## Contents

1. [The idea in five sentences](#1-the-idea-in-five-sentences)
2. [Vocabulary](#2-vocabulary)
3. [Pipeline at a glance](#3-pipeline-at-a-glance)
4. [Folder layout](#4-folder-layout)
5. [Install everything](#5-install-everything)
6. [Launch the MVP (quick start)](#6-launch-the-mvp-quick-start)
7. [Every step and every script, in detail](#7-every-step-and-every-script-in-detail)
8. [How to view the results](#8-how-to-view-the-results)
9. [What we expect, what we have, and why](#9-what-we-expect-what-we-have-and-why)
10. [Testing the whole pipeline](#10-testing-the-whole-pipeline)
11. [Using real screenpipe data instead of the fake](#11-using-real-screenpipe-data-instead-of-the-fake)
12. [Troubleshooting](#12-troubleshooting)
13. [File formats between steps](#13-file-formats-between-steps)
14. [Privacy and safety rules built into the code](#14-privacy-and-safety-rules-built-into-the-code)

---

## 1. The idea in five sentences

1. Screenpipe takes a screenshot every few seconds and reads its text (OCR). We call each one a **capture**.
2. We glue consecutive captures of the same window into **sessions** ("12 minutes in the Google Sheet *Weekly KPI report*").
3. We turn each session into a list of numbers (an **embedding**) so that sessions *about the same thing* get similar numbers, even when dates and amounts change.
4. Sessions that look alike become **step types**. Step types that keep happening together, in the same order, on several different days, form a **candidate task**. Each day's occurrence of it is a **run**.
5. A person reviews the candidates on a web page, confirms the real tasks, rejects the false ones, and labels unusual steps. Only then do we export.

---

## 2. Vocabulary

| Word | Simple meaning | In the code |
|---|---|---|
| **Capture** | One thing screenpipe saw: a screenshot's text (OCR) or the window's accessibility text (UI). | Row of table `captures` in `trail.db`. ID like `ocr:1042` or `ui:17`. |
| **Session** | A stretch of time in one app + one window, with no pause longer than 5 minutes. | Row of table `sessions`. ID like `s_9623598350` (hash of its first capture ID, so it stays the same if you re-ingest). |
| **Embedding** | A list of 256 numbers that represents what a session's text is about. | `embeddings.npz`, one vector per session, length 1 (L2-normalised). |
| **Cosine similarity** | A score from −1 to 1: how much two embeddings point in the same direction. 1 = same meaning. | Because vectors have length 1, cosine = dot product (`a @ b`). |
| **Threshold** | The cosine above which we say "these two sessions are the same kind of step". | `find_tasks.py --threshold`; default picked from the embedding model (`DEFAULT_THRESHOLDS` in `common.py`). |
| **Step type** | A group of sessions that are the same step done on different days ("export from Metabase"). | Cluster label from `cluster()` in `find_tasks.py`. |
| **Task** | A group of step types that happen together, in order, on ≥ 3 days. | Connected component of linked step types. |
| **Run** | One occurrence of a task on one day. | One entry in `throught_runs.json`. |
| **Observed minutes** | Time from the first session's start to the last session's end in a run. Measured, never estimated. | `run_minutes()` in `common.py`. |
| **Extra session** | A session that sits *inside* a run's time span but is not one of the task's usual steps: maybe an exception, a fix, or an interruption. | `extra_sessions` in `throught_runs.json`. Highlighted in yellow on the review page. |
| **Kind** | What a step is: `normal` (the usual process), `exception` (a business case that needs special handling), `troubleshooting` (fixing a problem that is not part of the process), `unclassified` (not decided yet). | `session_kinds`. Set by the reviewer. |
| **Answer key** | For the synthetic data only: the true label of every capture, so we can measure how good the pipeline is. **Never fed into the pipeline.** | `fake_data/story.json` → `truth`, `fake_data/session_truth.json`, `fake_data/truth_runs.json`. |

---

## 3. Pipeline at a glance

```
 0  fake_story.py ──► fake_data/story.json  (captures + answer key)
                         │
 0b fake_screenpipe.py serve  (HTTP /search on :3031, same API as real screenpipe on :3030)
                         │
 1  ingest.py ─────────► trail.db  (captures → sessions)
                         │                         1b label_sessions.py ─► fake_data/session_truth.json
                         │                                                 fake_data/truth_runs.json
 2  embed.py ──────────► embeddings.npz  (one vector per session)        (answer key, scoring only)
                         │
 3  find_tasks.py ─────► throught_runs.json  (candidate tasks + runs)
                         │
 4  describe_tasks.py ─► task_descriptions.json  (optional: local LLM names tasks, quotes steps)
                         │
 5  review.py ─────────► reviewed_runs.json + review_state.json   ◄── a PERSON decides here
     (web page :4300)    │
 6  export_starter.py ─► starter_records.json, desk_records.json, desk_draft.json
                         │
 7  hackathon-starter: bun run repetition  ─► output/repetition-<id>.md  (ranked report)
 8  hackathon-starter: bun start --draft   ─► review desk on :4242 (procedure / SOP)

 ✓  check_pipeline.py: runs 0 → 3 + export in a temp folder and says PASSED / FAILED
```

`common.py` is shared by all scripts (paths, timestamp helpers, loading sessions, computing minutes).

---

## 4. Folder layout

```
~/throught/
├── README.md                  this file
├── Makefile                   runs the pipeline (make help)
├── requirements.txt           Python dependencies (pip install -r requirements.txt)
├── .venv/                     Python virtual environment (shared, not committed)
├── hackathon-starter/         screenpipe's starter (Bun / TypeScript), steps 7 and 8
└── event/                     run every python command from here
    ├── common.py              shared helpers
    ├── fake_story.py          step 0  – generate the synthetic month
    ├── fake_screenpipe.py     step 0b – serve it like screenpipe does
    ├── ingest.py              step 1  – screenpipe → trail.db
    ├── label_sessions.py      step 1b – answer key per session (synthetic only)
    ├── embed.py               step 2  – sessions → vectors
    ├── find_tasks.py          step 3  – vectors → candidate tasks and runs
    ├── describe_tasks.py      step 4  – local LLM names and describes each task
    ├── review.py              step 5  – review web page
    ├── export_starter.py      step 6  – export to hackathon-starter formats
    ├── check_pipeline.py      end-to-end test
    ├── RUN.md                 one-page cheat sheet of the run order
    ├── fake_data/             synthetic data + answer key
    └── *.json, trail.db, embeddings.npz   outputs of each step (see section 13)
```

---

## 5. Install everything

Tested on Ubuntu under WSL2 with Python 3.12, Bun 1.4, Ollama 0.40.

### 5.1 Python environment

The Python scripts only use the standard library plus **numpy** and **model2vec** (model2vec pulls in
`huggingface_hub`, `tokenizers` and `safetensors`).

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip curl git
cd ~/screenpipe_hackathon42
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt   # or just: pip install numpy model2vec
```

From now on, open every terminal with:

```bash
cd ~/screenpipe_hackathon42/event && source ../.venv/bin/activate
```

### 5.2 Embedding model: VTX-JEV-2 (about 30 MB, runs on CPU)

Download it once while you have internet; it goes into `~/.cache/huggingface/hub/`:

```bash
python3 -c "from model2vec import StaticModel; StaticModel.from_pretrained('VTXAI/VTX-JEV-2'); print('ok')"
# or, with the Hugging Face CLI installed by huggingface_hub:
hf download VTXAI/VTX-JEV-2
```

After that, run with `HF_HUB_OFFLINE=1` so it never tries the network (useful on event Wi-Fi).

**No model at all?** `embed.py --model hashing` uses a built-in, no-download stand-in (see step 2).

### 5.3 Local LLM: Ollama + qwen3:4b-instruct (optional, about 2.5 GB, step 4 only)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &                 # skip if it already runs as a service; `ollama list` tells you
ollama pull qwen3:4b-instruct
ollama list                    # should show qwen3:4b-instruct
```

Step 4 is optional: the review page works without it, it just doesn't show suggested names.

### 5.4 Bun + hackathon-starter (steps 7 and 8)

```bash
curl -fsSL https://bun.sh/install | bash
exec $SHELL                    # reload PATH so `bun` is found
bun --version                  # needs >= 1.3
cd ~/screenpipe_hackathon42
git clone https://github.com/screenpipe/hackathon-starter.git   # skip if the folder already exists
cd hackathon-starter && bun run demo   # sanity check: no dependencies needed
```

---

## 6. Launch the MVP (quick start)

**With make (one terminal)**, from the repo root (`make help` lists every target and variable):

```bash
make install                                         # once: .venv + requirements
make pipeline FROM=2026-09-07 TO=2026-10-06          # fake screenpipe + steps 1 → 3, the whole month
make pipeline FROM=2026-09-14 TO=2026-09-27          # same on 2 weeks (trail.db keeps only this range)
make pipeline FROM=2026-09-07                        # from 7 Sep to the most recent data
make review                                          # 5 → http://localhost:4300, Save, then Ctrl+C
make export repetition desk                          # 6, 7, 8
```

`make pipeline` starts the fake screenpipe itself and stops it at the end (no `make fake-up` needed).

| Variable | Default | Meaning |
|---|---|---|
| `FROM`, `TO` | empty | UTC range; `TO` needs `FROM`; a bare date is a whole day; empty = all history |
| `FAKE` | `1` | `0` = real screenpipe on :3030 (no answer key, no `--score` / `--show-truth`) |
| `MODEL` | `VTXAI/VTX-JEV-2` | `hashing` = no download needed |
| `THRESHOLD` | empty | empty = picked from `MODEL` (0.9 JEV-2, 0.6 hashing); set it to override |
| `MIN_DAYS` | `3` | a task must repeat on at least this many days to count as repetitive |
| `TYPES`, `URL` | `ocr,accessibility`, from `FAKE` | passed to `ingest.py` |

With `MIN_DAYS=3`, a 2-week range has only 2 runs of each weekly task, so weekly tasks are expected to
drop out (on 14 → 27 Sep only `refund_check` is found).

**By hand**, you need **two terminals**: one keeps the fake screenpipe running, the other runs the pipeline.

**Terminal A** (leave it running):

```bash
cd ~/screenpipe_hackathon42/event && source ../.venv/bin/activate
python3 fake_story.py                              # 0  : generate the synthetic month
python3 fake_screenpipe.py serve --port 3031       # 0b : fake screenpipe API
```

**Terminal B:**

```bash
cd ~/screenpipe_hackathon42/event && source ../.venv/bin/activate
export HF_HUB_OFFLINE=1

python3 ingest.py --url http://localhost:3031 --from 2026-09-07 --once              # 1
python3 label_sessions.py                                                           # 1b (fake data only)
python3 embed.py                                                                    # 2
python3 find_tasks.py --sweep                                                       # 2b (optional: precision/recall table)
python3 find_tasks.py --score                                                       # 3  (threshold from the model, see below)
python3 describe_tasks.py --model qwen3:4b-instruct                                 # 4  (optional, ~1 min per task on CPU)
python3 review.py --show-truth                                                      # 5  → open http://localhost:4300
```

On the review page: reject the *Squad sync* meeting, confirm the three real tasks, classify every yellow
session, press **Save decisions**. Then stop `review.py` with `Ctrl+C` and continue:

```bash
python3 export_starter.py                                                           # 6

cd ~/screenpipe_hackathon42/hackathon-starter
bun run repetition --input ~/screenpipe_hackathon42/event/starter_records.json                     # 7 → output/repetition-*.md
bun start --draft ~/screenpipe_hackathon42/event/desk_draft.json                                   # 8 → open http://localhost:4242
```

No time for the review page? Use the answer key instead of your own decisions:
`python3 export_starter.py --truth-runs` (synthetic data only).

---

## 7. Every step and every script, in detail

Each step below has **Concept** (what it means in plain words) and **In the code** (how it does it).

### `common.py` — shared helpers

- **Concept:** small tools every script needs, so they all agree on file names, time zones and how minutes are counted.
- **In the code:**
  - Path constants: `DB_PATH = "trail.db"`, `RUNS_PATH`, `REVIEWED_PATH`, `DESCRIPTIONS_PATH`, `TRUTH_*_PATH`.
  - `parse_ts()` reads ISO timestamps (with `Z`, with nanoseconds) into UTC `datetime`s; `iso()` writes them back.
  - `local_day()` gives the day **in Paris time** (`Europe/Paris`, falls back to UTC+2 if no tz database), so a session at 23:30 UTC counts for the right day.
  - `load_sessions()` reads table `sessions` from `trail.db`, ordered by time, and decodes `source_ids` from JSON.
  - `run_minutes(sessions)` = last `end_ts` − first `start_ts`, in minutes. This is the only way minutes are ever computed.
  - `read_json()` / `write_json()` (UTF-8, `ensure_ascii=False`, indented).

### Step 0 — `fake_story.py`: generate the synthetic month

- **Concept:** we need screen history where *we know the right answer*, to measure the pipeline. The script invents a month of Inès's work with three hidden repeated tasks, plus things that must **not** be detected as tasks.

  | Hidden thing | What happens | What THROUGHT should do |
  |---|---|---|
  | `weekly_report` | 5 Mondays, ~25 min: Metabase dashboard → CSV export → Google Sheet → (Lyon tab, from run 4) → Gmail. Run 2 is interrupted by a Slack message; run 3 has an expired-password detour. | Find it, ranked **1st** by minutes. Slack = noise to remove, password = troubleshooting, Lyon tab = a normal process change. |
  | `refund_check` | 20 weekday mornings, ~4 min: Zendesk queue → Stripe refund → Zendesk reply. One €64.80 refund is over the €50 limit and gets escalated. | Find it, ranked **2nd**. Escalation = exception. |
  | `partner_onboard` | 4 Thursdays, ~19 min: Gmail application → Pappers SIRET lookup → Tavola admin → Notion checklist. Sushi Kan has no SIRET, so an extra email asks for it. | Find it, ranked **3rd**. Missing SIRET = exception. |
  | Squad sync | Monday meeting (Google Meet + Notion notes), same steps every week. | Classic false positive: it *will* be proposed; the **reviewer rejects it**. |
  | Project work, one-offs, noise | Figma/Notion design work on random days; six one-time things (pricing deck, hotel booking…); Slack, Mail, Spotify sprinkled through the day. | Must not become tasks. |

- **In the code:**
  - Fixed seed `SEED = 42`, so every run produces exactly the same data (2,386 captures).
  - Each task is a list of **step templates** `(step key, app, window, url, minutes, [screen lines])` with `{placeholders}` (week number, order count, ticket number…) filled per run, so text changes week to week like real life.
  - `Story.add_session()` writes one OCR capture every 30–50 s for the session's duration, plus one `UI` (accessibility) capture repeating the first line — this tests that ingest counts duplicates once.
  - `Story.run_steps()` plays steps back to back with small random gaps and labels every capture in `self.truth` (`category`, `task`, `step`, `run`, `kind`).
  - `build()` places everything on the calendar, keeps a `busy` list per day so noise never lands inside a run (except the deliberate Slack popup), and writes `meta.expected_ranking` and `meta.expected_runs`.
  - Output: `fake_data/story.json` = `{"meta", "captures", "truth"}`. Captures have the exact shape of screenpipe's `/search` results.

### Step 0b — `fake_screenpipe.py`: pretend to be screenpipe

- **Concept:** a tiny web server that answers the same questions as the real screenpipe, so `ingest.py` works the same on fake and real data.
- **In the code:**
  - `ThreadingHTTPServer` on `127.0.0.1:<port>`; endpoints `/health` and `/search`.
  - `/search` supports `content_type` (`ocr`→`OCR`, `accessibility`→`UI`, `audio`, `input`, `memory`, `all`), `start_time`, `end_time`, `app_name`, `window_name`, `q` (case-insensitive substring), `limit` (max 1000), `offset`, and returns `pagination.total`, like the real API.
  - If `fake_data/story.json` is missing, it calls `fake_story.main()` first.

### Step 1 — `ingest.py`: screen history → sessions in `trail.db`

- **Concept:** download everything screenpipe saw, keep each thing once, and cut the timeline into sessions ("time spent in one window").
- **In the code:**
  1. `fetch_all()` calls `GET /search?content_type=…&limit=200&offset=…` page by page until `offset >= pagination.total`. If an API key is set (`--api-key`, or env `SCREENPIPE_API_KEY` / `SCREENPIPE_LOCAL_API_KEY`) it sends `Authorization: Bearer …`. Clear error messages for HTTP 401/403 and "cannot reach".
  2. `to_capture()` turns `OCR`, `UI` and `Audio` results into one common shape with a **stable source ID** (`ocr:<frame_id>`, `ui:<id>`, `audio:<chunk_id>`), cleans whitespace, and drops empty ones. `Input` and `Memory` are ignored on purpose (see section 14).
  3. `store()` does `INSERT OR IGNORE` into `captures` (primary key = source ID), so re-running ingest never duplicates.
  4. `rebuild_sessions()` walks all captures in time order and starts a new session when the **app or window changes** or the **gap is longer than `--gap-min`** (default 5 min). Inside a session, identical text (SHA-1 of lowercased text) is kept once — OCR and UI often see the same screen. Session text is capped at 4,000 characters. The table `sessions` is rebuilt from scratch each time.
  - **Time range:** `--from START` alone = from START to the most recent data; `--from START --to END` = a fixed range; no `--from` = all history. `--to` without `--from` is an error. A bare date is a whole UTC day (`--to 2026-09-13` ends at 23:59:59). `trail.db` only keeps the chosen range: captures outside it are deleted before ingesting. The range is stored in table `meta`; when it changes, the outputs of later steps (`embeddings.npz`, `throught_runs.json`, `task_descriptions.json`, `reviewed_runs.json`, exports, answer-key files) are deleted because they describe the old range. `review_state.json` is kept.
  - `--once` runs one pass; without it, it polls every `--every` seconds (default 60), asking only for captures newer than the latest stored one (still capped by `--to` if given).
  - **Result on the synthetic data:** 2,386 captures → **321 sessions**.

### Step 1b — `label_sessions.py`: answer key per session (synthetic only)

- **Concept:** the answer key is per capture; the pipeline works on sessions. This translates the answer key to sessions so we can score results. **Its output is never an input to the pipeline**, only to `--score`, `--sweep`, `--show-truth` and `--truth-runs`.
- **In the code:**
  - `label_sessions()` gives each session the most common label of its captures and a `purity` (share of captures that agree).
  - `truth_runs()` builds the *perfect* `throught_runs.json` (same format + `session_kinds`) and sorts tasks by total minutes.
  - Writes `fake_data/session_truth.json` and `fake_data/truth_runs.json`. **Re-run after every ingest**, because session IDs come from `trail.db`.

### Step 2 — `embed.py`: sessions → vectors

- **Concept:** computers can't compare meaning directly, so each session's text becomes 256 numbers. Sessions about the same step ("Download full results | orders_week_37.csv" and "… orders_week_39.csv") get vectors pointing in nearly the same direction.
- **In the code:**
  - Input text per session: `"<app> | <window>\n<text>"` (default `--input window+text`), or the text alone with `--input text`.
  - Default model `VTXAI/VTX-JEV-2` through `model2vec.StaticModel` — a *static* model: it looks up one vector per word piece and averages them. No GPU, no transformer at run time, so it embeds all 321 sessions in well under a second.
  - `--model hashing`: a no-download fallback. Each word is hashed (MD5) into one of 256 slots with a +1/−1 sign, then summed. It catches shared words, not meaning.
  - Vectors are L2-normalised, then **centered**: the average vector is subtracted and they are normalised again. Why: a static model points almost every text in roughly the same direction (most pairs have cosine > 0.8); removing the common part keeps only what makes sessions different. Turn it off with `--no-center`.
  - Output: `embeddings.npz` with `ids`, `vectors` (321 × 256), `model`, `input`, `centered`.

### Step 2b — `find_tasks.py --sweep`: check the threshold

- **Concept:** the threshold is the most important setting. Too low = different steps get merged; too high = the same step on different days gets split. The sweep measures this against the answer key.
- **In the code:** for every pair of sessions **on different days**, "same" means same task *and* same step in the answer key. For each threshold it prints **precision** (of the pairs we call similar, how many really are the same step) and **recall** (of the truly-same pairs, how many we catch). Measured on our data with JEV-2:

  | threshold | 0.70 | 0.80 | 0.90 | 0.92 | 0.95 |
  |---|---|---|---|---|---|
  | precision | 0.16 | 0.26 | **0.37** | 0.34 | 0.25 |
  | recall    | 0.99 | 0.98 | **0.82** | 0.69 | 0.34 |

  Precision peaks at 0.90 with recall still above 0.8, which is why 0.9 is the default for JEV-2 (`DEFAULT_THRESHOLDS` in `common.py`). The sweep needs the answer key, so it only runs on the synthetic data; on real data the per-model default is used. Low precision overall is expected: this is pair-by-pair, before the "repeats on several days in the same order" rule of step 3 filters most mistakes out.

### Step 3 — `find_tasks.py`: vectors → candidate tasks and runs

- **Concept:** in plain words:
  1. **Same step?** Two sessions are the same kind of step if their cosine ≥ threshold. Group sessions into step types.
  2. **Same task?** Two step types belong to one task if, on **≥ 3 different days**, they happen **within 60 minutes** of each other, **usually in the same order**, and **usually together**.
  3. **Runs:** every day's cluster of a task's steps is one run. Other sessions that fall inside that run's time span are kept as **extra** for the reviewer to judge.
- **In the code:**
  - `cluster()` — *leader clustering*: go through sessions in time order; join the group whose centroid is most similar if ≥ threshold, otherwise start a new group. Then one clean-up pass moves each session to its best group.
  - `linked_pairs()` — for every pair of step types seen on ≥ `--min-days` days: count days where their closest sessions are ≤ `--window-min` apart (`together`); `support = together / max(days of a, days of b)` must be ≥ `--min-support` (0.6); `order = share of those days with the same one first` must be ≥ `--min-order` (0.8).
  - `components()` — union-find: linked step types → one candidate task.
  - `find_runs()` — sorts the task's sessions in time, cuts into groups (new group when the day changes or > 60 min from the group start), keeps groups with **≥ 2 different step types**, then adds every other session that starts inside the group's span as `extra`. A session already used by a bigger task is not reused (`taken`).
  - `build()` — keeps tasks seen on ≥ 3 days, orders their step types by median position, and names a task `"<first step's window> → <last step's window>"` (digits replaced by `#`). Each run gets `minutes` (via `run_minutes`), `extra_sessions`, and `step_share` (e.g. `"18/20"` = this kind of step appears in 18 of the task's 20 runs). Tasks are sorted by total observed minutes.
  - `--score` prints, per proposed task, which hidden task most of its sessions belong to (`TASK` / `FALSE POSITIVE`), and how many true runs were found (a true run counts as found if ≥ 50 % of its sessions are in one proposed run).
  - Output: `throught_runs.json`.

### Step 4 — `describe_tasks.py`: a local LLM names the tasks (optional)

- **Concept:** names like "Refund requests – Zendesk → Ticket ## – Zendesk" are ugly. A small language model running **on your own machine** (Ollama) suggests a short name and lists the steps, each with an **exact quote** from the screen as proof. The LLM never decides what is a task; it only describes.
- **In the code:**
  - `representative_run()` picks one run per task: fewest extra sessions, then most sessions, then most recent.
  - Sessions are sent numbered **1, 2, 3…** (small models copy short numbers reliably, long IDs not), with app, window, and the first `--max-chars` (300) characters of text.
  - `ask_ollama()` calls `POST /api/chat` with `temperature 0`, `think: false`, and a JSON schema in `format`, so the reply must be `{name, steps: [{session, text, quote, kind}]}`. The system prompt says the screen text is **untrusted** and must not be obeyed.
  - `check_steps()` maps numbers back to session IDs and **rejects** every step whose quote is not found word for word (`find_quote()`) in that session's text. Rejected steps are kept with a reason, for transparency.
  - Output: `task_descriptions.json` (`name`, `run`, `steps`, `rejected`, `model`, `seconds`).

### Step 5 — `review.py`: a person decides

- **Concept:** the most important step. Algorithms propose; a person disposes. Nothing is ever confirmed automatically.
- **What you do on http://localhost:4300:**
  - Each candidate task is a card with its runs side by side (one column per run, sessions in time order).
  - **Rename** the task (or click **use name** to take the LLM's suggestion, shown with its quoted steps).
  - **remove** a session that doesn't belong (e.g. the Slack popup); **restore** to undo.
  - Sessions highlighted in **yellow** are *extra*. Each needs a kind: `exception`, `troubleshooting`, or `normal`. **Confirm task** is blocked while any extra session is still `unclassified`.
  - **Reject (not a task)** for false positives such as the Squad sync meeting.
  - Click a session's text to expand it; hover its ID to see its source capture IDs.
  - With `--show-truth`, dashed **key:** badges show the answer key (synthetic data only) so you can check yourself.
  - **Save decisions** writes the files.
- **In the code:**
  - `build_data()` joins `throught_runs.json` + `trail.db` + `task_descriptions.json` (+ answer key if `--show-truth`) into one JSON for the page; it refuses to start if the runs mention sessions that no longer exist (re-run the pipeline).
  - The page is plain HTML + JavaScript embedded in the `PAGE` string, served by a `ThreadingHTTPServer` with `GET /`, `GET /api/data`, `POST /api/save`. It uses HTTP/1.1 and the page retries loading 3 times, because Windows → WSL `localhost` forwarding sometimes resets connections.
  - `save()` writes `review_state.json` (all decisions, so you can close and resume) and `reviewed_runs.json` (**confirmed tasks only**, removed sessions dropped, minutes recomputed from what's left, each session's kind).
  - `--truth-runs` opens the answer key itself in the page; `--runs other.json` reviews any runs file; `--port` changes the port.

### Step 6 — `export_starter.py`: hand over to the hackathon-starter

- **Concept:** translate the confirmed tasks into the input formats of screenpipe's starter, so its existing tools can rank them and turn one into a procedure.
- **In the code:**
  - Refuses to run if `reviewed_runs.json` is missing or empty, or if one session is in two runs.
  - `starter_records.json`: one record per session, `app = "THROUGHT (reviewed)"`, `text` starting with `Task: …\nRun: …\nMinutes: …` then `Session: <window> | <text>`. Every session of a run repeats the same three header lines, so the starter's "duplicates count once" rule merges them into one run and lists the session IDs as sources. Checks the starter's limits (≤ 1000 records, ≤ 2 MB, 0 < minutes ≤ 1440).
  - `pick_desk_run()` chooses one run for the review desk: by default the run of the **top task** with the **most non-normal steps** (best shows the classification). Override with `--desk-run <run id>`.
  - `desk_records.json`: that run's sessions as plain evidence (with a `screenpipe://frame/<id>` link when an OCR frame exists).
  - `desk_draft.json`: the same run as a procedure draft: title, context, evidence, one step per session (`text`, `sourceId`, `quote`, `kind` from the **reviewer**, `reviewed: false`), and two open questions. If an LLM step exists for the same window (digits ignored), its text is used, and its quote is kept **only if** it appears in this run's session; otherwise the session's first line is used as the quote.
  - `--truth-runs` exports the answer key instead of your review.

### Steps 7 and 8 — in `~/throught/hackathon-starter` (Bun / TypeScript, not ours)

- **Step 7, `bun run repetition --input …/starter_records.json`:** the starter's *Repeated-task finder*. It groups records by the `Task:` / `Run:` labels and ranks tasks by observed minutes, writing a Markdown report to `output/repetition-<id>.md`.
- **Step 8, `bun start --draft …/desk_draft.json`:** the starter's *Workflow review desk* on http://localhost:4242. You check each step against its evidence, fix the classification, answer the questions, then **Approve and freeze** and export an SOP. (Alternative: `bun start --input …/desk_records.json` to start from raw evidence.)

### `check_pipeline.py` — end-to-end test

See [section 10](#10-testing-the-whole-pipeline).

---

## 8. How to view the results

| What | How |
|---|---|
| Step-by-step summaries | Every script prints a short summary in the terminal (counts, runs, minutes, `--score` verdicts). |
| Sessions in the database | `sqlite3 trail.db "SELECT start_ts, minutes, app, window FROM sessions LIMIT 20;"` (install with `sudo apt install sqlite3`) |
| Candidate tasks | `python3 find_tasks.py --score`, or open `throught_runs.json`. |
| Review page | `python3 review.py --show-truth` → http://localhost:4300 |
| The perfect answer, for comparison | `python3 review.py --truth-runs` → http://localhost:4300 |
| What you confirmed | `reviewed_runs.json` (and `review_state.json` for all decisions incl. rejections). |
| Ranked report | `ls -t ~/throught/hackathon-starter/output/repetition-*.md \| head -1 \| xargs less` |
| Procedure / SOP desk | `bun start --draft ~/throught/event/desk_draft.json` → http://localhost:4242 |
| Pass / fail of the whole pipeline | `python3 check_pipeline.py …` (section 10) |

Quick one-liner to summarise any runs file:

```bash
python3 -c "
import json,sys,collections as c
t=c.defaultdict(lambda:[0,0.0])
for r in json.load(open(sys.argv[1])): t[r['task']][0]+=1; t[r['task']][1]+=r['minutes']
[print(f'{n:3} runs {m:7.1f} min  {k}') for k,(n,m) in t.items()]" throught_runs.json
```

---

## 9. What we expect, what we have, and why

Measured on **16 Oct 2026** with JEV-2, `window+text`, centered, on the files in this folder.

### 9.1 Detection (`find_tasks.py`)

**Threshold:** `find_tasks.py` picks it from the embedding model stored in `embeddings.npz`
(`DEFAULT_THRESHOLDS` in `common.py`: **0.9 for JEV-2**, **0.6 for hashing**; any other model gets 0.9
with a warning). At 0.8 with JEV-2 the refund task disappears completely, see below. `--threshold`
still overrides it.

| Hidden task | Expected | We have (threshold 0.9) | Verdict |
|---|---|---|---|
| `weekly_report` | 5 runs, 138.5 min, rank 1 | **5/5 runs, 138.5 min**, ranked 1st among real tasks | ✅ Perfect. |
| `refund_check` | 20 runs, 93.7 min, rank 2 | **20/20 runs, 91.9 min**, ranked 2nd | ✅ 1.8 min short (one session missed, see below). |
| `partner_onboard` | 4 runs, 79.2 min, rank 3 | **3/4 runs, 41.9 min**, ranked 3rd | ⚠️ Sushi Kan run missed, and found runs lack their first step(s). |
| Squad sync (meeting) | proposed, then rejected by the reviewer | proposed, **158.3 min, ranked 1st overall** | ✅ Expected false positive; rejected on the review page. |
| Project work, one-offs, noise | never proposed | never proposed | ✅ |

The *extra* sessions flagged inside runs are exactly the ones we planted:

| Run | Extra session flagged | Truth | Reviewer chose |
|---|---|---|---|
| weekly 2026-09-14 | Slack "is the weekly report out yet?" | noise | **removed** |
| weekly 2026-09-21 | SSO "password expired" | troubleshooting | **troubleshooting** |
| weekly 2026-09-28, 10-05 | Lyon tab | normal (process change) | **normal** |
| refund 2026-09-21 | €64.80 escalation to Finance | exception | **exception** |
| refund 2026-09-08, 10-06 | Stripe step | normal | **normal** |

**Why these results:**

- **Why 0.9 and not 0.8?** At 0.8, all 60 refund sessions (Zendesk queue, Stripe, Zendesk reply) fall into **one** step type: they are short, similar texts full of ticket numbers and euro amounts. A task needs **at least two linked step types**, so with one type there's nothing to link and the task vanishes (0/20). At 0.9 they split into three step types (queue, Stripe, reply) and all 20 runs are found. This matches the sweep: 0.9 has the best precision.
- **Why Sushi Kan is missed.** That run is the exception: the Pappers page says *"Aucun résultat"*, there is an extra "Request SIRET" email, and the admin page says *"saved with SIRET pending"*. Each of those sessions looks different from the other weeks, so each becomes its own step type. Only the Notion checklist matches the usual steps, and a run needs ≥ 2 of the task's step types, so the run is dropped. In plain words: **the run that was *different* is exactly the one the "find what repeats" rule cannot see.** This is a known limit of the approach.
- **Why the partner runs are shorter (41.9 vs 79.2 min).** The first step, *"New partner application – Gmail"*, contains each restaurant's name, city and cuisine, so each week's email lands in a different step type and never repeats on 3 days. Since run minutes are measured from the first *detected* session, the application step (and on 17 Sep the Pappers step too) is outside the run. The missing Sushi Kan run accounts for the rest.
- **Why refund is 1.8 min short.** On 7 Sep the Zendesk queue session went into a different step type and starts *before* the run's first detected session, so it isn't even picked up as an extra (extras are only searched *inside* the run's time span). That run reads 2.47 min instead of 4.25.
- **Why the meeting is ranked first.** It *is* repeated, same steps, same order, every Monday, 30 min. Nothing in the screen text says "this is a meeting, not a process". Deciding that is a judgement call, which is why the review step exists.
- **Why the fallback works better here.** `embed.py --model hashing` (threshold 0.6, picked automatically) finds **4/4** partner runs and passes the full test (section 10). On this synthetic data, exact shared words ("SIRET", "Partner", "Tavola Admin") are a strong signal. Real data is messier; we keep JEV-2 as the default because it captures meaning, not just shared words, and the review step catches its misses.

### 9.2 LLM descriptions (`describe_tasks.py`)

| Task | Suggested name | Steps kept / rejected | Time |
|---|---|---|---|
| Squad sync | "Capture Action Items" | 2 / 0 | 53 s |
| Weekly report | "Export and Report" | 4 / 0 | 85 s |
| Refund | "Process Refund" | 3 / 0 | 61 s |
| Partner onboarding | "Onboard partner" | 3 / 0 | 80 s |

- ✅ All quotes were found word for word in their sessions (0 rejected), so no invented evidence.
- ⚠️ `qwen3:4b-instruct` often copies the whole session text into the step's `text` field instead of writing a short description. Since `export_starter.py` reuses that text for other runs of the task, the desk draft for run 2026-09-21 shows *week 37* numbers in its step texts while its quotes (correctly) come from *week 39*. The reviewer should rewrite step texts on the desk. A bigger model or a stricter prompt would fix this.
- ⚠️ It is slow on CPU (~1 min per task), which is why it is optional.

### 9.3 Review and export (current saved state)

- Squad sync: **rejected**. Weekly report: **confirmed**, renamed to "Send weekly KPI report", Slack popup removed, kinds set. Refund: **confirmed**, escalation = exception. Partner onboarding: **confirmed** (3 runs).
- The refund and partner tasks kept their automatic window-based names; click **use name** on the review page to take the LLM's names before saving if you want nicer labels in the report.
- `reviewed_runs.json` → 28 runs; `export_starter.py` produced `starter_records.json`, and the desk files hold run **2026-09-21** of "Send weekly KPI report" (the one with the troubleshooting step).

---

## 10. Testing the whole pipeline

`check_pipeline.py` copies the `*.py` files to a temporary folder, runs steps 0 → 3 plus the export
(on the answer key), and checks:

- each hidden task has **≥ 80 %** of its runs found,
- the ranking is `weekly_report > refund_check > partner_onboard`,
- no proposed task is mostly noise (chat, music, inbox),
- the export respects the starter's rules (≤ 1000 records, unique IDs),
- with `--starter`, that `bun run repetition` ranks the three tasks correctly.

A proposed meeting is only a **WARNING** (the reviewer handles it). Your real files are never touched; `--keep` keeps the temp folder.

```bash
cd ~/throught/event && source ../.venv/bin/activate
HF_HUB_OFFLINE=1 python3 check_pipeline.py --starter ~/throught/hackathon-starter
python3 check_pipeline.py --model hashing --starter ~/throught/hackathon-starter
```

Results today:

| Command | Result | Why |
|---|---|---|
| JEV-2, `--threshold 0.8` (forced) | ❌ **FAILED**: refund 0/20, partner 3/4, ranking wrong | All refund steps merge into one step type (section 9.1). |
| JEV-2 (default threshold 0.9) | ❌ **FAILED** only on partner 3/4 (75 % < 80 %) | Sushi Kan exception run missed. |
| hashing (default threshold 0.6) | ✅ **PASSED** (5/5, 20/20, 4/4) in ~3 s | Shared exact words are a strong signal on synthetic data. |

---

## 11. Using real screenpipe data instead of the fake

1. Install and start [screenpipe](https://screenpipe.com); it serves its API on `http://localhost:3030`.
2. If it requires a key: `export SCREENPIPE_API_KEY=…` (or `SCREENPIPE_LOCAL_API_KEY`).
3. Run the same pipeline, but:
   - skip steps 0, 0b and **1b** (there is no answer key for real data),
   - step 1: `python3 ingest.py --url http://localhost:3030 --from <date> [--to <date>] --once` (or `make pipeline FAKE=0 FROM=<date> [TO=<date>]`) (add `--types ocr,accessibility,audio` for audio transcripts; drop `--once` to keep polling),
   - drop `--score`, `--sweep` and `--show-truth` (they need the answer key).
4. Only capture permissioned work. Review everything before sharing.

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `cannot reach screenpipe at http://localhost:3031` | Terminal A must be running `fake_screenpipe.py serve --port 3031`. |
| `screenpipe returned HTTP 401/403` | Set `SCREENPIPE_API_KEY` (real screenpipe only). |
| `N sessions have no embedding: run embed.py again after ingest` | Every ingest rebuilds sessions: re-run `embed.py` (and `label_sessions.py` on fake data). |
| `… mentions sessions not in trail.db` (review/export) | Same cause: re-run steps 2 → 3 after the ingest. |
| JEV-2 tries to download / no internet | Download once (section 5.2), then `export HF_HUB_OFFLINE=1`. Or use `--model hashing` (its threshold, 0.6, is picked automatically). |
| `ModuleNotFoundError: model2vec` / `numpy` | Activate the venv: `source ~/throught/.venv/bin/activate`. |
| `Ollama call failed … Is it running?` | `ollama serve &` then `ollama list`; `ollama pull qwen3:4b-instruct` if missing. |
| `reply was not complete JSON` | Raise `--num-predict 2500` or lower `--max-chars 200`. |
| Review page: `ERR_CONNECTION_RESET` / "loading failed" (Windows browser → WSL) | The page retries 3 times; refresh once more. Keep only one `review.py` running. |
| **Confirm task** shows an alert | Classify or remove every yellow (extra) session first. |
| `reviewed_runs.json not found` / `has no confirmed runs` | Confirm at least one task on the review page and press **Save decisions**. |
| `Address already in use` | Another copy is running: `Ctrl+C` it, or use `--port`. |
| Refund task missing from results | You forced `--threshold 0.8` with JEV-2. Drop `--threshold` (default 0.9). |

---

## 13. File formats between steps

| File | Written by | Shape |
|---|---|---|
| `fake_data/story.json` | `fake_story.py` | `{"meta": {...}, "captures": [screenpipe /search results], "truth": {source_id: {category, task, step, run, kind}}}` |
| `trail.db` | `ingest.py` | SQLite. `captures(source_id, kind, ts, app, window, url, text)`; `meta(key, value)` (the `--from`/`--to` range); `sessions(session_id, start_ts, end_ts, minutes, app, window, url, text, source_ids, n_captures)` |
| `fake_data/session_truth.json` | `label_sessions.py` | `{session_id: {category, task, step, run, kind, purity}}` |
| `fake_data/truth_runs.json` | `label_sessions.py` | like `throught_runs.json` + `session_kinds` |
| `embeddings.npz` | `embed.py` | numpy archive: `ids`, `vectors` (n × 256, float32), `model`, `input`, `centered` |
| `throught_runs.json` | `find_tasks.py` | `[{"task", "run", "sessions", "minutes", "extra_sessions", "step_share"}]` |
| `task_descriptions.json` | `describe_tasks.py` | `{task: {"name", "run", "steps": [{text, session_id, quote, kind}], "rejected", "model", "seconds"}}` |
| `review_state.json` | `review.py` | `{"source", "decisions": {task: {status, name, removed, kinds}}}` |
| `reviewed_runs.json` | `review.py` | `[{"task", "proposed_as", "run", "sessions", "minutes", "session_kinds"}]` (confirmed only) |
| `starter_records.json` | `export_starter.py` | `[{"id", "timestamp", "app", "text": "Task: …\nRun: …\nMinutes: …\nSession: …"}]` |
| `desk_records.json` | `export_starter.py` | `[{"id", "timestamp", "app", "text", "source"?}]` (one run) |
| `desk_draft.json` | `export_starter.py` | `{"title", "context", "revision", "origin", "evidence", "steps": [{text, sourceId, quote, kind, reviewed}], "questions"}` |

---

## 14. Privacy and safety rules built into the code

- **Never ingested:** `content_type=input` (keystrokes can contain passwords) and `content_type=memory` (AI summaries, not exact source text). `ingest.py` refuses them even if asked.
- **Everything runs locally:** fake screenpipe, SQLite, the embedding model and the LLM (Ollama) are all on your machine. Servers listen on `127.0.0.1` only.
- **Screen text is untrusted:** the LLM is told never to follow instructions found in it, and every quote it returns is checked word for word against the source; failures are rejected and shown.
- **Nothing is confirmed automatically:** only tasks a person confirms on the review page are exported.
- **Minutes are observed, never estimated:** first session start → last session end.
- **The answer key is for scoring only:** it is never an input to steps 1 → 3.
