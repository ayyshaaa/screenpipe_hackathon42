#!/usr/bin/env python3
"""CONCENTRATION ingest: screenpipe /search -> captures -> sessions in trail.db.

What it does, in order:
  1. Asks screenpipe /search for each content type (default: ocr, accessibility),
     page by page until pagination.total is reached.
  2. Turns every result into one "capture" row with a stable source ID
     (ocr:<frame_id>, ui:<id>, audio:<chunk_id>). Same ID seen twice = stored once.
  3. Rebuilds sessions: consecutive captures in the same app + window, with no gap
     longer than --gap-min minutes. Identical text inside a session is kept once
     (OCR and the accessibility tree often capture the same screen).

Time range: --from START [--to END]. With --from alone the range runs from START to the most
recent data screenpipe has. --to needs --from. A bare date is a whole UTC day: --from 2026-09-07
starts at 00:00, --to 2026-09-13 ends at 23:59:59. trail.db only keeps the chosen range: captures
outside it are deleted before the new ones are stored, then sessions are rebuilt. When the range
changes, the outputs of later steps (embeddings, runs, descriptions, exports) are deleted too,
since they describe the old range; review_state.json (the reviewer's decisions) is kept.

Never used: content_type=memory (AI summaries, not exact quotes) and
content_type=input (keystrokes can contain passwords).

Examples:
  python3 ingest.py --url http://localhost:3031 --from 2026-09-07 --once
  python3 ingest.py --url http://localhost:3031 --from 2026-09-14 --to 2026-09-27 --once
  python3 ingest.py --url http://localhost:3030 --types ocr,accessibility,audio --once
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PAGE_SIZE = 200
# outputs of later steps, next to trail.db: stale as soon as the range changes
DERIVED = ["embeddings.npz", "concentration_runs.json", "task_descriptions.json", "reviewed_runs.json",
           "starter_records.json", "desk_records.json", "desk_draft.json",
           "fake_data/session_truth.json", "fake_data/truth_runs.json"]
SESSION_TEXT_MAX = 4000  # characters kept per session (enough for embeddings and quotes)


# ---------- small helpers ----------

def parse_ts(value):
    """screenpipe timestamps are ISO strings, sometimes ending in 'Z'."""
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    # trim nanoseconds to microseconds so fromisoformat accepts it
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_bound(value, end_of_day):
    """CLI date -> UTC datetime. A bare date (2026-09-07) means the start or the end of that day."""
    try:
        dt = parse_ts(value)
    except ValueError:
        sys.exit(f"bad date {value!r}: use 2026-09-07 or 2026-09-07T08:30:00Z")
    if end_of_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


# ---------- 1. fetch from screenpipe ----------

def fetch_all(base_url, content_type, since, until, api_key):
    """Yield every result for one content_type, following pagination."""
    offset = 0
    while True:
        params = {"content_type": content_type, "limit": PAGE_SIZE, "offset": offset}
        if since:
            params["start_time"] = since
        if until:
            params["end_time"] = until
        url = f"{base_url.rstrip('/')}/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url)
        if api_key:  # same headers as the starter's own screenpipe client
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("X-Screenpipe-Client", "api")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as e:
            sys.exit(f"screenpipe returned HTTP {e.code} for {content_type}: {e.read()[:200]!r}"
                     " (401/403 = check SCREENPIPE_API_KEY)")
        except urllib.error.URLError as e:
            sys.exit(f"cannot reach screenpipe at {base_url}: {e.reason} (is it running?)")

        items = body.get("data", [])
        for item in items:
            yield item

        total = (body.get("pagination") or {}).get("total", 0)
        offset += len(items)
        if not items or offset >= total:
            break


# ---------- 2. one result -> one capture ----------

def to_capture(item):
    """Normalise the 4 result types into the same shape. Returns None to skip."""
    kind = item.get("type")
    c = item.get("content") or {}

    if kind == "OCR":
        source_id, text = f"ocr:{c.get('frame_id')}", c.get("text")
        app, window = c.get("app_name"), c.get("window_name")
    elif kind == "UI":  # what content_type=accessibility returns
        source_id, text = f"ui:{c.get('id')}", c.get("text")
        app, window = c.get("app_name"), c.get("window_name")
    elif kind == "Audio":
        source_id, text = f"audio:{c.get('chunk_id')}", c.get("transcription")
        app, window = "audio", (c.get("speaker") or {}).get("name") or c.get("device_name")
    else:  # Input, Memory or anything new: deliberately ignored
        return None

    text = clean(text)
    ts = parse_ts(c.get("timestamp"))
    if not text or ts is None or source_id.endswith(":None"):
        return None
    return {
        "source_id": source_id,
        "kind": kind,
        "ts": iso(ts),
        "app": app or "unknown",
        "window": window or "",
        "url": c.get("browser_url") or "",
        "text": text,
    }


# ---------- database ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    source_id TEXT PRIMARY KEY,   -- ocr:<frame_id> / ui:<id> / audio:<chunk_id>
    kind      TEXT NOT NULL,      -- OCR / UI / Audio
    ts        TEXT NOT NULL,      -- UTC ISO
    app       TEXT NOT NULL,
    window    TEXT NOT NULL,
    url       TEXT NOT NULL,
    text      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS captures_ts ON captures(ts);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,  -- stable: hash of the first capture's source ID
    start_ts   TEXT NOT NULL,
    end_ts     TEXT NOT NULL,
    minutes    REAL NOT NULL,     -- observed, end - start
    app        TEXT NOT NULL,
    window     TEXT NOT NULL,
    url        TEXT NOT NULL,
    text       TEXT NOT NULL,     -- unique lines joined, capped
    source_ids TEXT NOT NULL,     -- JSON list, shown to the reviewer
    n_captures INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,       -- 'range': the --from/--to of the last ingest
    value TEXT NOT NULL
);
"""


def keep_range(db, start, end):
    """Delete captures outside [start, end] (end None = no upper limit). Returns how many."""
    before = db.total_changes
    if start:
        db.execute("DELETE FROM captures WHERE ts < ?", (start,))
    if end:
        db.execute("DELETE FROM captures WHERE ts > ?", (end,))
    return db.total_changes - before


def set_range(db, start, end, db_path):
    """Remember the range in trail.db; if it changed, delete the outputs built from the old one."""
    new = json.dumps([start, end])
    old = db.execute("SELECT value FROM meta WHERE key = 'range'").fetchone()
    if old and old[0] == new:
        return []
    db.execute("INSERT OR REPLACE INTO meta VALUES ('range', ?)", (new,))
    folder = os.path.dirname(os.path.abspath(db_path))
    removed = []
    for name in DERIVED:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    return removed


def store(db, captures):
    before = db.total_changes
    db.executemany(
        "INSERT OR IGNORE INTO captures VALUES (:source_id,:kind,:ts,:app,:window,:url,:text)",
        captures,
    )
    return db.total_changes - before


# ---------- 3. captures -> sessions ----------

def rebuild_sessions(db, gap_min):
    rows = db.execute(
        "SELECT source_id, ts, app, window, url, text FROM captures ORDER BY ts, source_id"
    ).fetchall()

    sessions, cur = [], None
    for source_id, ts, app, window, url, text in rows:
        t = parse_ts(ts)
        same_place = cur and cur["app"] == app and cur["window"] == window
        small_gap = cur and (t - cur["last"]).total_seconds() <= gap_min * 60
        if not (same_place and small_gap):
            cur = {"app": app, "window": window, "url": url, "first": t, "last": t,
                   "source_ids": [], "texts": [], "seen": set()}
            sessions.append(cur)
        cur["last"] = t
        cur["source_ids"].append(source_id)
        key = hashlib.sha1(text.lower().encode()).hexdigest()
        if key not in cur["seen"]:  # duplicate capture of the same screen: keep once
            cur["seen"].add(key)
            cur["texts"].append(text)
        if url and not cur["url"]:
            cur["url"] = url

    db.execute("DELETE FROM sessions")
    for s in sessions:
        sid = "s_" + hashlib.sha1(s["source_ids"][0].encode()).hexdigest()[:10]
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, iso(s["first"]), iso(s["last"]),
             round((s["last"] - s["first"]).total_seconds() / 60, 2),
             s["app"], s["window"], s["url"],
             "\n".join(s["texts"])[:SESSION_TEXT_MAX],
             json.dumps(s["source_ids"]), len(s["source_ids"])),
        )
    return len(sessions)


# ---------- main ----------

def run_once(args, db, since):
    new = 0
    for ctype in args.types:
        caps = [c for c in (to_capture(i) for i in fetch_all(args.url, ctype, since, args.to, args.api_key)) if c]
        added = store(db, caps)
        new += added
        print(f"  {ctype}: {len(caps)} results, {added} new captures")
    n = rebuild_sessions(db, args.gap_min)
    db.commit()
    print(f"  -> {new} new captures, {n} sessions in {args.db}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:3030")
    p.add_argument("--from", dest="from_", metavar="START",
                   help="UTC start, e.g. 2026-09-07 or 2026-09-07T08:00:00Z (default: all history)")
    p.add_argument("--to", metavar="END", help="UTC end, needs --from (default: most recent data)")
    p.add_argument("--types", default="ocr,accessibility",
                   help="comma list from: ocr, accessibility, audio (memory/input are refused)")
    p.add_argument("--gap-min", type=float, default=5, help="new session after this many idle minutes")
    p.add_argument("--db", default="trail.db")
    p.add_argument("--once", action="store_true", help="run one pass and exit")
    p.add_argument("--every", type=int, default=60, help="seconds between passes when not --once")
    p.add_argument("--api-key", default=os.environ.get("SCREENPIPE_API_KEY")
                   or os.environ.get("SCREENPIPE_LOCAL_API_KEY"))
    args = p.parse_args()

    if args.to and not args.from_:
        p.error("--to needs --from")
    start = parse_bound(args.from_, end_of_day=False) if args.from_ else None
    end = parse_bound(args.to, end_of_day=True) if args.to else None
    if start and end and end < start:
        p.error("--to is before --from")
    args.from_ = iso(start) if start else None
    args.to = iso(end) if end else None

    args.types = [t.strip() for t in args.types.split(",") if t.strip()]
    bad = set(args.types) - {"ocr", "accessibility", "audio"}
    if bad:
        sys.exit(f"refusing content types {sorted(bad)}: memory is not exact source text, input can contain passwords")

    db = sqlite3.connect(args.db)
    db.executescript(SCHEMA)
    dropped = keep_range(db, args.from_, args.to)
    stale = set_range(db, args.from_, args.to, args.db)
    db.commit()

    print(f"ingest from {args.url}, range {args.from_ or 'the beginning'} -> {args.to or 'most recent data'}")
    if dropped:
        print(f"  removed {dropped} captures outside the range from {args.db}")
    if stale:
        print(f"  new range: removed outputs of the old one ({', '.join(stale)}), re-run the next steps")
    since = args.from_
    while True:
        run_once(args, db, since)
        if args.once:
            break
        # next pass: only ask for what is newer than the last capture we have
        since = db.execute("SELECT MAX(ts) FROM captures").fetchone()[0] or since
        time.sleep(args.every)


if __name__ == "__main__":
    main()
