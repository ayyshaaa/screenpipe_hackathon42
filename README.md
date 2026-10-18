# CONCENTRATION

*Named after the memory card game: turn over a month of screens, find the cards that match, and the pairs that keep
coming back are the tasks worth automating.*

Built at **"Build Agents That Remember" (screenpipe × 42 Paris, Oct 16–18 2026)**, Track 1 *Find what to automate*.

The starter's repeated-task finder (`bun run repetition`) ranks tasks by observed minutes, but only for records where a person
typed one `Task:`, one `Run:` and one `Minutes:` line. **CONCENTRATION proposes those annotations from raw screen history, and a
person confirms them before anything is ranked.** Steps are described with exact quotes, exceptions and one-off
troubleshooting are kept apart from the normal process, and nothing predicts savings.

> All results below use **synthetic data** (Inès, a product manager at a fictional company, Tavola, 7 Sep – 6 Oct 2026).
> Everything runs locally: screenpipe, the embedding model and the LLM. No screen text leaves the machine.

---

## Results on the synthetic month

| Hidden task | Truth | Found | Observed minutes | Note |
|---|---|---|---|---|
| Payout reconciliation (Fridays, ~1 h 40 per run) | 4 runs | **4/4** | 390.1 | every run found **whole**, though its last step starts ~90 min after the first |
| Weekly KPI report (Mondays) | 5 runs | **5/5** | 138.5 | run 3's expired-login detour kept as *troubleshooting*; the Lyon tab added from run 4 kept as *normal* |
| Refund check (mornings) | 20 runs | **20/20** | 91.9 | the €64.80 escalation kept as *exception* |
| Partner onboarding | 4 runs | **3/4** | 41.9 | **failure case**: see below |
| Monday squad sync (meeting) | not a task | proposed | — | classic false positive, **rejected by the reviewer** |

Measured with VTX-JEV-2 at its default threshold (0.89). The starter ranks the confirmed runs **payout reconciliation >
weekly report > refunds > onboarding**, the expected order, citing session IDs as sources.

**The failure case, shown on purpose.** The Sushi Kan onboarding run is missed: its company had no SIRET, so the screens
differ (no result, an extra "Request SIRET" email) and too few sessions match the usual steps. The onboarding's minutes are
also under-counted, because its first step (the application email) was grouped with other Gmail screens. This is why a
person reviews the proposals, and why minutes are *observed*, never estimated: an error under-counts rather than inflates.

---

## Quick start

Tested on **WSL2 (Ubuntu 24.04) on Windows, Python 3.12, Bun 1.3+, Ollama 0.40, CPU only, 10 GB RAM given to WSL**.
Everything below runs from the repo root; the scripts live in `event/`, the virtual environment in `.venv/`, and the
starter is cloned next to them (`hackathon-starter/`, git-ignored).

```bash
git clone https://github.com/ayyshaaa/screenpipe_hackathon42 && cd screenpipe_hackathon42
make install                                       # .venv + requirements.txt (numpy, model2vec, huggingface_hub…)
.venv/bin/hf download VTXAI/VTX-JEV-2              # embedding model (~165 MB), once, while online
git clone https://github.com/screenpipe/hackathon-starter     # Bun 1.3+, steps 7 and 8
sudo apt install -y zstd && curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b-instruct                      # writing model (~2.5 GB), optional: step 4 only
```

Then:

```bash
make pipeline FROM=2026-09-07                      # fake screenpipe + ingest + answer key + embed + tasks
make describe                                      # optional: local LLM names tasks and drafts steps (~1.5 min per task on CPU)
make review                                        # http://localhost:4300: confirm / reject, classify, Save, then Ctrl+C
make export repetition desk                        # starter records, bun run repetition, review desk on :4242
make check                                         # end-to-end test on the synthetic data
```

`make help` lists every target; `ingest`, `label`, `embed`, `sweep` and `tasks` also run one step at a time.
`make pipeline` starts the fake screenpipe itself and stops it at the end.
`make describe` is optional: without `task_descriptions.json`, review and export still work, with the `app – window`
names found by step 3 and no LLM-drafted steps on the desk.

| Variable | Default | Effect |
|---|---|---|
| `FROM` | empty = all history | first day kept (UTC); a bare date is a whole day |
| `TO` | empty = most recent data | last day kept (UTC); **needs `FROM`**, refused otherwise |
| `THRESHOLD` | empty = picked from the model | "same step?" cosine threshold (0.89 for JEV-2, 0.6 for `hashing`) |
| `MODEL` | `VTXAI/VTX-JEV-2` | `hashing` = built-in stand-in, no download |
| `MIN_DAYS` | `3` | a task must repeat on at least this many different days |
| `FAKE` | `1` | `0` = real screenpipe on `:3030`, no answer key (no `--score`, no `--show-truth`) |
| `REVIEW_PORT`, `FAKE_PORT` | `4300`, `3031` | ports of the review page and of the fake screenpipe |
| `TYPES`, `LLM`, `STARTER` | `ocr,accessibility`, `qwen3:4b-instruct`, `./hackathon-starter` | passed to ingest, describe, and the Bun steps |

**Changing the range invalidates later steps.** `trail.db` keeps only the chosen range, and when the range changes, ingest
deletes the outputs built from the old one (embeddings, runs, descriptions, reviewed runs, exports, answer key), so a stale
review can never be exported against new sessions. Re-run `make pipeline`, then review again. The reviewer's decisions
(`review_state.json`) are kept: they are matched by task name and session ID, so work done on sessions that still exist
is not lost, but check the confirmed tasks again before saving.

---

## How it works

```
screenpipe /search ──> ingest ──> trail.db ──> JEV-2 embeddings ──> "same step?" ──> step types ──> tasks + runs
                                                                                                        │
      starter: bun run repetition  <── export <── a person reviews (review.py) <── LLM describes ──────┘
               review desk :4242
```

Each step reads files and writes files; no script calls another. That makes every step re-runnable on its own and lets
`make` rebuild only what changed.

### 1. Ingest: screen history → sessions (`ingest.py`)

Reads screenpipe's `/search` page by page until `pagination.total`, and groups captures into **sessions**: consecutive
captures in the same app and window, with no pause longer than 5 minutes.

- **Text only, from OCR and the accessibility tree** (`content_type=ocr,accessibility`, optionally `audio`). Accessibility
  results come back typed `"UI"`, which the code maps explicitly.
- **Refused: `memory`**, which is AI-written summaries, not exact source text, so it would break the exact-quote rule;
  and **`input`**, because keystrokes can contain passwords.
- **Source IDs are kept** (`ocr:<frame_id>`, `ui:<id>`, `audio:<chunk_id>`) and travel all the way to the starter, so every
  claim can be traced back to a capture.
- **Duplicates count once, at two levels:** the same capture ID is stored once (`INSERT OR IGNORE` on a primary key), and the
  same text seen twice in a session (OCR and accessibility often read the same screen) is kept once.
- **The range is chosen here and only here** (`--from`, `--to`, UTC; `--to` needs `--from`; a bare date is a whole day).
  `trail.db` keeps exactly that range and stores it in its `meta` table; when it changes, the outputs of later steps are
  deleted, so no step can work on a different range than the one ingested.

### 2. Embeddings: sessions → vectors (`embed.py`, VTX-JEV-2)

Each session (`app | window` + text) becomes 256 numbers; sessions with similar content land close together.

**Why VTX-JEV-2.** It is a *static* model, distilled with Model2Vec: a table of one vector per token, averaged over the
text. It needs no GPU and no PyTorch, embeds our 327 sessions in about 7.5 s on a laptop CPU (model loading included),
weighs ~125 MB on disk (~165 MB to download), and handles the French/English mix of real screens. We load the FP32 file
through the `model2vec` library; the 2-bit LF2 variant exists, but its model card publishes no quality figures, and at
our scale size and speed are not the bottleneck.

**What averaging costs:** word order is lost ("export then email" = "email then export"). CONCENTRATION therefore checks the
order of steps itself, in step 4.

**Mean-centering, our main fix.** Without it, almost every pair of sessions scored above 0.8 and everything merged into
8 step types. Static models give all texts a shared direction, and our `app | window` prefix ("Google Chrome" everywhere)
reinforced it. Subtracting the average vector of all sessions keeps only what distinguishes each one
(see Mu & Viswanath, *All-but-the-Top*, 2018).

### 3. "Same step?": choosing the threshold (`find_tasks.py --sweep`)

Two sessions from different days are "the same step" if their cosine similarity is ≥ the threshold. On synthetic data we
measured it against the answer key:

| Threshold | Precision | Recall |
|---|---|---|
| 0.80 | 0.27 | 0.98 |
| 0.85 | 0.34 | 0.96 |
| **0.89** | **0.37** | **0.86** |
| 0.90 | 0.37 | 0.82 |
| 0.95 | 0.27 | 0.35 |

**The default is 0.89 for JEV-2** (`DEFAULT_THRESHOLDS` in `common.py`; `hashing` gets 0.6; `--threshold` overrides it).
It has the best precision while recall stays above 0.8, and it sits inside the range that works, now only **0.88–0.89**:
below 0.88 the three short refund screens (Zendesk queue, Stripe, Zendesk reply) merge into one step type, a task needs
two linked step types, so refunds vanish (0/20 at 0.87); from 0.90 the onboarding runs split apart (0/4). The default
was 0.9 until we added the long payout task: its 16 sessions moved the mean used for centering, and the onboarding fell
from 3/4 to 0/4 at 0.9. That narrow range is the main fragility of this design (see limitations). **Recall matters more
than precision:** a missed pair can make a whole task disappear, with nobody to catch it; a false pair is filtered by
the rules in step 4 and then by the reviewer. The modest precision is partly an artefact: the answer key only calls task
steps "the same", so two near-identical Slack messages count as an error even though grouping them is harmless. What
matters is the final task score above.

### 4. Step types → tasks → runs (`find_tasks.py`)

1. **Step types.** *Leader clustering*: in time order, each session joins the group whose centre is closest if it is above
   the threshold, otherwise it starts a new group, then a clean-up pass reassigns sessions. No number of groups is fixed in
   advance, since nobody knows how many different steps a month contains. At 0.89 this gives 62 step types.
   We did not use HDBSCAN: our steps occur only 4 to 20 times, too few for density-based clustering to be tuned reliably,
   and a measured threshold is easier to justify.
2. **Linked step types.** Two types belong to one task if, on **at least 3 different days**, they occur **within 60 minutes**,
   in a **consistent order (≥ 80 %)**, and **usually together** (co-occurring days / days either occurs ≥ 60 %).
   These rules come from what a repeated task is: it recurs, its steps follow each other closely and in the same order.
   They are also what filters noise: Slack or Spotify appear every day, but not in a consistent order next to anything.
3. **Tasks.** Linked pairs are merged *transitively* (union-find): if dashboard–export, export–sheet and sheet–email are
   linked, all four are one task even if dashboard and email were never directly linked.
4. **Runs.** Each day's cluster of a task's steps is one run: a run goes on while each step starts **within 60 minutes
   of the previous step's end**, so a task with many or long steps is not cut at one hour. Two runs done back to back
   are still told apart: a new run starts when the task's usual first step comes back after its usual last step.
   Sessions that fall *inside* a run but are not one of its usual steps (the login detour, a Slack interruption, the new
   Lyon tab) are kept as **extras** for the reviewer instead of being silently dropped or silently included. Each
   session shows in how many runs its kind of step appears ("in 2/5 runs").
5. **Ranking** by total observed minutes, the starter's own criterion. A run's minutes are **the durations of its
   sessions plus the short gaps between them** (≤ 5 minutes, the same idle limit that ends a session at ingest):
   switching windows counts, a coffee break or a meeting between two steps does not (`run_minutes` in `common.py`).
   `MIN_DAYS` (default 3) is the "at least 3 days" rule: on a 2-week range a weekly task has only 2 runs and is,
   correctly, not proposed.

The squad sync is proposed because it follows exactly the pattern of a task (same two steps every Monday, same order).
No rule can tell a meeting from a task here, which is precisely what the human review is for.

### 5. LLM descriptions (`describe_tasks.py`, Ollama + `qwen3:4b-instruct`)

For each candidate task, the cleanest run is sent to a local LLM, which proposes a name and the steps, each with an exact
quote, a session and a kind (`normal`, `exception`, `troubleshooting`). **The LLM describes; it never decides what is a task.**

- **Why this model:** local (screen text stays on the machine), runs on CPU, follows instructions in French and English.
  We use the *instruct* tag: plain `qwen3:4b` is the thinking variant, which wrote 554 tokens and took a minute for a
  20-token answer.
- **Structured output:** Ollama's `format` takes a JSON schema, so the reply can only have the expected fields and kinds.
  `temperature: 0` makes it reproducible.
- **Prompt choices that fixed real failures:** sessions are **numbered 1, 2, 3** (a 4B model copies long IDs badly),
  quotes must come from **one line**, text is cut to 300 characters per session (prompt reading dominates CPU time), and
  the reply limit is 1,500 tokens (900 cut the JSON mid-string). Result: 0 rejected quotes on the 4 tasks, ~65–100 s per
  task (5.5 min for all 4).
- **Verification:** code maps numbers back to session IDs and **rejects any quote not found word for word** in the source.
- **Prompt injection:** screen text can contain anything, including instructions from an email or a web page. The prompt
  marks captures as untrusted data, the schema limits the output, the LLM has no tools, quotes are checked, and a person
  approves. The worst it can do is write a bad description that a human reads.

### 6. Human review (`review.py` + `review.html`, http://localhost:4300)

`review.py` is a small local server: it serves `review.html` and two endpoints, `GET /api/data` (runs, sessions, LLM
suggestions, saved decisions) and `POST /api/save`. The page is plain HTML and JavaScript, with no framework and no build
step; `review.html` is read again on every request, so an edit shows after F5. **Nothing is confirmed automatically.**

**What the reviewer sees.** One card per candidate task, in ranking order, folded to one line: the name, one bar per run
(its length is the run's minutes), the number of runs and total minutes, how many sessions still need a decision, and
quick ✓ / ✗ buttons. Unfolded, the runs sit side by side (4 per row on a wide screen). Each session is one line with a
coloured dot for its kind: grey *normal*, orange *exception*, red *troubleshooting*, orange ring *to classify*. Extras
(sessions inside a run that are not one of its usual steps) are highlighted and open by default; any other line opens on
click and shows its time and app, the screen text, how many runs contain this kind of step ("in 2/5 runs"), the session ID
and capture count (source IDs on hover) and, with `--show-truth`, the answer key.

| Action | Where | What is saved |
|---|---|---|
| **Rename** | field at the top of the card, or "use name" on the LLM suggestion | `task` = new name; `proposed_as` keeps the proposed one |
| **Confirm / reject** | ✓ / ✗ on the folded line, or the buttons at the top | only confirmed tasks are saved; confirming is refused while a highlighted session is unclassified |
| **Classify** | menu on each session | `session_kinds`; the desk draft uses it over the LLM's kind |
| **Remove / restore** | button on each session | the session is left out and the run's minutes recomputed |
| **Split here / merge back** | button on each session except the first of a run (open the line to see it) | the run is saved as two, `<run>` and `<run>.2`, each with its own minutes |

The minutes shown (run headers, bars, card total) are the ones that will be saved: they update as soon as a session
is removed or a run is split, with the same rule as the server. A removed session's duration stops counting, wherever it
sits in the run; the short gaps around it still count, since they are time spent switching windows.

**LLM suggestion.** When `task_descriptions.json` exists, a folded "Local LLM suggests" block shows the proposed name and
numbered steps, each with its kind, quote and session; in the run it was read from, the cited sessions carry an
"step N" badge. It is only a suggestion: nothing changes unless the reviewer clicks "use name".

**Filters.** Chips in the header hide tasks by status (pending, confirmed, rejected) and sessions by kind (normal,
exception, troubleshooting, to classify, removed), with counts; "Expand all / Collapse all" opens or folds every card.
Filters and open cards are remembered by the browser (`localStorage`), not saved with the decisions.

**Saving.** Nothing is written until **Save decisions**. The server then writes `review_state.json` (every decision,
loaded again the next time the page opens on the same runs file) and `reviewed_runs.json` (confirmed runs only, minutes
recomputed from the sessions kept). Closing or reloading the tab with unsaved changes asks for confirmation; if a save
fails (server stopped, connection reset), the page retries, then says **NOT SAVED** and keeps the decisions so you can
save again. Ctrl+C stops the server and says whether this session saved anything; if the port is taken, it says so
instead of crashing.

**Safety.** Screen text is inserted into the page as text, never as HTML, so a captured web page or email cannot run
script in the review page. The server listens on 127.0.0.1 only. The page loads its font from Google Fonts (no screen text
is sent); offline, it falls back to the system monospace font.

### 7. Export to the starter (`export_starter.py`)

- **`starter_records.json`, one record per session**, all carrying their run's `Task:` / `Run:` / `Minutes:` lines. The
  starter's rule that duplicate captures of a run count once merges them, and lists the **session IDs as sources**, so the
  starter's report shows our evidence without changing its code. The export checks the starter's limits (1,000 records, 2 MB,
  minutes > 0 and ≤ 1,440) and that no session belongs to two runs.
- **`desk_draft.json`**: one run of the top task (the one with the most exceptions / troubleshooting, the most instructive)
  as a procedure draft. The reviewer's kinds win over the LLM's; every quote is re-checked against the source; steps start
  unreviewed, because the desk requires a person to tick each one, answer the questions and sign before approving.

### 8. Synthetic data and tests

Organisers ruled that no code written before the event could be brought, so everything here, including the fake data, was
written during the event.

- `fake_story.py` writes a month of screen history with four hidden tasks (one lasting ~1 h 40 per run, to test that a
  run is not cut at one hour), their exceptions, a recurring meeting, project work, one-offs and noise;
  `fake_screenpipe.py` serves it with the same `/search` API as screenpipe. `make pipeline` reuses
  `fake_data/story.json`: after changing `fake_story.py`, run `make clean story` first, and restart a fake screenpipe
  started by hand, since it keeps the old story in memory.
- `label_sessions.py` writes the answer key (`fake_data/session_truth.json`, `fake_data/truth_runs.json`). **It is only used
  for scoring, never as pipeline input.** `review.py --truth-runs` and `export_starter.py --truth-runs` show the perfect answer.
- `check_pipeline.py` (`make check`) runs everything in a throw-away copy and fails if a hidden task loses more than
  20 % of its runs, a run of the long task is cut instead of found whole, the ranking is wrong, noise is proposed as a
  task, or the export breaks the starter's rules. With `--starter` (`make check` passes `$(STARTER)` when that folder
  exists), it also checks the ranking produced by `bun run repetition`. With JEV-2 it reports **one expected failure,
  Sushi Kan (3/4)**, and one warning, the squad sync. With `MODEL=hashing` it passes (4/4 onboarding runs): exact shared
  words such as "SIRET" are a strong signal on synthetic text, but we keep JEV-2 as the default because real screens are
  messier.

---

## File formats between steps

| File | Written by | Content |
|---|---|---|
| `trail.db` | ingest | `captures`, `sessions(session_id, start_ts, end_ts, minutes, app, window, url, text, source_ids)`, `meta` (the ingested range) |
| `embeddings.npz` | embed | session IDs + one centred, normalised vector each |
| `concentration_runs.json` | find_tasks | `[{task, run, sessions, minutes, extra_sessions, step_share}]` |
| `task_descriptions.json` | describe_tasks | per task: `name`, `run` (the run it was read from), `steps[{text, session_id, quote, kind}]`, `rejected`, `model`, `seconds` |
| `review_state.json` | review page | `{source, decisions: {task: {status, name, removed, kinds, splits}}}`, every decision, reloaded by the page |
| `reviewed_runs.json` | review page | confirmed runs only: `[{task, proposed_as, run, sessions, minutes, session_kinds}]` |
| `starter_records.json` | export | `[{id, timestamp, app, text: "Task: …\nRun: …\nMinutes: …\nSession: …"}]` |
| `desk_draft.json` | export | the review desk's procedure format: `title, context, evidence, steps, questions` |

---

## Limitations and next steps

- **No answer key on real data.** Precision and recall exist only on synthetic data. On real data, review decisions measure
  the precision of proposals (tasks confirmed / proposed, sessions removed); labelling ~20 session pairs around the threshold
  would re-calibrate it; a few tasks declared by the person ("I do the KPI report every Monday") would measure recall.
- **The threshold depends on the range and the data**, through mean-centering (the average vector changes with the
  sessions kept). Adding the 16 sessions of the long payout task narrowed the working range to 0.88–0.89 and moved the
  default from 0.9 to 0.89. Next: store the calibration mean and reuse it.
- **Exception runs can be missed** when the exception changes most screens (Sushi Kan). Runs with fewer matching steps
  could be proposed as "possible runs" for the reviewer.
- **A first step can be lost** when its screens resemble other tasks' (the onboarding's application email), so minutes are
  under-counted.
- **Minutes are slightly under-counted:** a session lasts from its first to its last capture, so the time spent on the
  last screen of each session (about one capture interval, ~40 s on our data) is not counted. Long pauses (> 5 min)
  between two steps are not counted either, on purpose.
- **Word order is ignored** by the embeddings; order is only checked between steps, not inside a session.
- **The LLM's step texts are weak:** `qwen3:4b-instruct` often copies the session text instead of describing the step, and
  the desk draft reuses those texts for another run (week 37 numbers next to week 39 quotes; the quotes themselves are
  correct). The reviewer rewrites them on the desk; a larger model or a stricter prompt would help.
- **CPU-only LLM** takes ~1.5 min per task: descriptions are generated before a demo, not live.
- **Not measured yet:** time saved. The starter's next step applies: measure the same task manually and with assistance
  before claiming any benefit.

---

## Resources

- screenpipe [search API](https://docs.screenpipe.com/api-reference/search/search-screen-and-audio-content) ·
  [hackathon starter](https://github.com/screenpipe/hackathon-starter): [repeated-task finder](https://github.com/screenpipe/hackathon-starter/blob/main/examples/repetition-finder/README.md),
  [review desk](https://github.com/screenpipe/hackathon-starter/blob/main/examples/workflow-review/README.md)
- Embeddings: [3Blue1Brown](https://www.3blue1brown.com/lessons/gpt) · [Model2Vec](https://huggingface.co/blog/Pringled/model2vec) ·
  [VTX-JEV-2](https://huggingface.co/VTXAI/VTX-JEV-2) · [All-but-the-Top (mean removal)](https://arxiv.org/abs/1702.01417)
- Evaluation and clustering: [precision and recall](https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall) ·
  [scikit-learn clustering](https://scikit-learn.org/stable/modules/clustering.html) · [HDBSCAN](https://hdbscan.readthedocs.io/en/latest/how_hdbscan_works.html) ·
  [union-find](https://en.wikipedia.org/wiki/Disjoint-set_data_structure)
- LLM: [Ollama structured outputs](https://ollama.com/blog/structured-outputs) · [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- WSL: [networking](https://learn.microsoft.com/en-us/windows/wsl/networking)
