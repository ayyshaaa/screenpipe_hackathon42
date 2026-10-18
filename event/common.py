"""Small helpers shared by every CONCENTRATION script (no business logic here)."""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Paris")
except Exception:  # no tz database installed: Paris summer time is good enough for the demo
    LOCAL_TZ = timezone(timedelta(hours=2))

DB_PATH = "trail.db"
RUNS_PATH = "concentration_runs.json"
REVIEWED_PATH = "reviewed_runs.json"
DESCRIPTIONS_PATH = "task_descriptions.json"
TRUTH_SESSIONS_PATH = "fake_data/session_truth.json"
TRUTH_RUNS_PATH = "fake_data/truth_runs.json"

# "Same step?" cosine threshold per embedding model, picked from find_tasks.py --sweep on the
# synthetic data. find_tasks.py uses it when --threshold is not given.
DEFAULT_THRESHOLDS = {"VTXAI/VTX-JEV-2": 0.89, "hashing": 0.6}
FALLBACK_THRESHOLD = 0.9  # any other model: untested, tune it with --sweep or by hand


def parse_ts(value):
    """ISO timestamp (maybe ending in Z, maybe with nanoseconds) -> aware UTC datetime."""
    value = value.replace("Z", "+00:00")
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def local_day(ts):
    """'2026-09-07' in Paris time, so a 23:30 UTC session lands on the right day."""
    return parse_ts(ts).astimezone(LOCAL_TZ).date().isoformat()


def load_sessions(db_path=DB_PATH):
    """All sessions from trail.db as dicts, in time order."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM sessions ORDER BY start_ts, session_id").fetchall()
    sessions = []
    for r in rows:
        s = dict(r)
        s["source_ids"] = json.loads(s["source_ids"])
        sessions.append(s)
    return sessions


PAUSE_MIN = 5  # same as ingest.py --gap-min: a longer gap between two sessions is a pause, not work


def run_minutes(sessions, removed=()):
    """Observed minutes of a run, never estimated: the durations of its sessions, plus the short gaps between
    them (switching windows, <= PAUSE_MIN). Longer pauses are not counted, so a break does not inflate a run.
    removed: session IDs the reviewer left out; their duration is not counted, the gaps around them still are."""
    ss = sorted(sessions, key=lambda s: s["start_ts"])
    kept = [i for i, s in enumerate(ss) if s["session_id"] not in removed]
    if not kept:
        return 0.0
    total = sum(ss[i]["minutes"] for i in kept)
    end = parse_ts(ss[kept[0]]["end_ts"])
    for s in ss[kept[0] + 1:kept[-1] + 1]:  # gaps between the first and the last kept session only
        gap = (parse_ts(s["start_ts"]) - end).total_seconds() / 60
        if 0 < gap <= PAUSE_MIN:
            total += gap
        end = max(end, parse_ts(s["end_ts"]))
    return round(total, 2)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
