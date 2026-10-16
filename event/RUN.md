# THROUGHT — run order

All commands run from `~/throught` with the venv active (`source .venv/bin/activate`).
Data in `fake_data/` is SYNTHETIC (Inès at Tavola). Say so in the demo.

| # | Command | Writes |
|---|---------|--------|
| 0 | `python3 fake_story.py` | `fake_data/story.json` (fake history + answer key per capture) |
| 0b | `python3 fake_screenpipe.py serve --port 3031` (own terminal) | — (serves `/search`) |
| 1 | `python3 ingest.py --url http://localhost:3031 --since 2026-09-07T00:00:00Z --once` | `trail.db` (captures, sessions) |
| 1b | `python3 label_sessions.py` (fake data only, after every ingest) | `fake_data/session_truth.json`, `fake_data/truth_runs.json` |
| 2 | `HF_HUB_OFFLINE=1 python3 embed.py` | `embeddings.npz` |
| 2b | `python3 find_tasks.py --sweep` (pick the threshold) | — (precision/recall table) |
| 3 | `python3 find_tasks.py --threshold 0.8 --score` | `throught_runs.json` |
| 4 | `python3 describe_tasks.py --model qwen3:4b-instruct` (optional, ~30 s/task on CPU) | `task_descriptions.json` |
| 5 | `python3 review.py --show-truth` → http://localhost:4300, confirm/reject, **Save** | `reviewed_runs.json`, `review_state.json` |
| 6 | `python3 export_starter.py` | `starter_records.json`, `desk_records.json`, `desk_draft.json` |
| 7 | in `~/hackathon-starter`: `bun run repetition --input ~/throught/starter_records.json` | report in `output/` |
| 8 | in `~/hackathon-starter`: `bun start --draft ~/throught/desk_draft.json` → http://localhost:4242 | — |
| ✓ | `python3 check_pipeline.py --threshold 0.8 --starter ~/hackathon-starter` | — (PASSED / FAILED) |

Real screenpipe instead of the fake: step 1 with `--url http://localhost:3030` (key read from
`$SCREENPIPE_API_KEY` or `$SCREENPIPE_LOCAL_API_KEY`), skip 1b, `--score` and `--show-truth`.

Answer key shortcuts: `python3 review.py --truth-runs`, `python3 export_starter.py --truth-runs`.
No JEV-2 available? `python3 embed.py --model hashing` + `find_tasks.py --threshold 0.6` (tested).

## File formats between steps

- `trail.db` → table `sessions(session_id, start_ts, end_ts, minutes, app, window, url, text, source_ids, n_captures)`
- `throught_runs.json` → `[{"task", "run", "sessions", "minutes", "extra_sessions", "step_share"}]`
- `reviewed_runs.json` → `[{"task", "proposed_as", "run", "sessions", "minutes", "session_kinds"}]` (confirmed only)
- `starter_records.json` → `[{"id", "timestamp", "app", "text": "Task: …\nRun: …\nMinutes: …\nSession: …"}]`
