# CONCENTRATION — run order

All commands run from `event/` with the venv active (`source ../.venv/bin/activate`).
Data in `fake_data/` is SYNTHETIC (Inès at Tavola). Say so in the demo.

| # | Command | Writes |
|---|---------|--------|
| 0 | `python3 fake_story.py` | `fake_data/story.json` (fake history + answer key per capture) |
| 0b | `python3 fake_screenpipe.py serve --port 3031` (own terminal) | — (serves `/search`) |
| 1 | `python3 ingest.py --url http://localhost:3031 --from 2026-09-07 [--to 2026-09-27] --once` | `trail.db` (captures, sessions) |
| 1b | `python3 label_sessions.py` (fake data only, after every ingest) | `fake_data/session_truth.json`, `fake_data/truth_runs.json` |
| 2 | `HF_HUB_OFFLINE=1 python3 embed.py` | `embeddings.npz` |
| 2b | `python3 find_tasks.py --sweep` (check the threshold, optional) | — (precision/recall table) |
| 3 | `python3 find_tasks.py --score` (threshold from the model: 0.9 JEV-2, 0.6 hashing; `--threshold` overrides) | `concentration_runs.json` |
| 4 | `python3 describe_tasks.py --model qwen3:4b-instruct` (optional, ~65–100 s/task on CPU, 5.5 min for the 4 tasks) | `task_descriptions.json` |
| 5 | `python3 review.py --show-truth` → http://localhost:4300, confirm/reject, **Save** | `reviewed_runs.json`, `review_state.json` |
| 6 | `python3 export_starter.py` | `starter_records.json`, `desk_records.json`, `desk_draft.json` |
| 7 | in `../hackathon-starter`: `bun run repetition --input ../event/starter_records.json` | report in `output/` |
| 8 | in `../hackathon-starter`: `bun start --draft ../event/desk_draft.json` → http://localhost:4242 | — |
| ✓ | `python3 check_pipeline.py --starter ../hackathon-starter` | — (PASSED / FAILED) |

Shortcut: `make pipeline FROM=… [TO=…]` from the repo root runs 0b → 3 (`make help`).
`--to` needs `--from`; trail.db only keeps the chosen range.

Real screenpipe instead of the fake: step 1 with `--url http://localhost:3030` (key read from
`$SCREENPIPE_API_KEY` or `$SCREENPIPE_LOCAL_API_KEY`), skip 1b, `--score` and `--show-truth`.

Answer key shortcuts: `python3 review.py --truth-runs`, `python3 export_starter.py --truth-runs`.
No JEV-2 available? `python3 embed.py --model hashing` then `find_tasks.py` (picks 0.6 by itself, tested).

## File formats between steps

- `trail.db` → table `sessions(session_id, start_ts, end_ts, minutes, app, window, url, text, source_ids, n_captures)`
- `concentration_runs.json` → `[{"task", "run", "sessions", "minutes", "extra_sessions", "step_share"}]`
- `reviewed_runs.json` → `[{"task", "proposed_as", "run", "sessions", "minutes", "session_kinds"}]` (confirmed only)
- `starter_records.json` → `[{"id", "timestamp", "app", "text": "Task: …\nRun: …\nMinutes: …\nSession: …"}]`
