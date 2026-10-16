#!/usr/bin/env python3
"""A fake screenpipe: serves the SYNTHETIC story with the same /search API as the real one.

  python3 fake_screenpipe.py serve --port 3031

Supports content_type (all, ocr, accessibility, audio, input, memory), start_time, end_time,
app_name, window_name, q (plain substring), limit, offset, and returns pagination.total.
Result types match the real API: content_type=accessibility returns type "UI".
"""
import argparse
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fake_story
from common import parse_ts, read_json

TYPE_FOR = {"ocr": {"OCR"}, "accessibility": {"UI"}, "audio": {"Audio"}, "input": {"Input"},
            "memory": {"Memory"}, "all": {"OCR", "UI", "Audio"}}


def load():
    if not os.path.exists(fake_story.OUT):
        fake_story.main()
    return read_json(fake_story.OUT)["captures"]


class Handler(BaseHTTPRequestHandler):
    captures = []

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/health":
            return self.reply({"status": "healthy", "fake": True})
        if url.path != "/search":
            return self.reply({"error": "not found"}, 404)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        types = TYPE_FOR.get(q.get("content_type", "all"))
        if types is None:
            return self.reply({"error": "bad content_type"}, 400)
        start = parse_ts(q["start_time"]) if q.get("start_time") else None
        end = parse_ts(q["end_time"]) if q.get("end_time") else None
        limit = min(int(q.get("limit", 20)), 1000)
        offset = int(q.get("offset", 0))

        def keep(item):
            c = item["content"]
            ts = parse_ts(c["timestamp"])
            return (item["type"] in types
                    and (start is None or ts >= start) and (end is None or ts <= end)
                    and (not q.get("app_name") or c.get("app_name") == q["app_name"])
                    and (not q.get("window_name") or q["window_name"] in c.get("window_name", ""))
                    and (not q.get("q") or q["q"].lower() in c.get("text", "").lower()))

        hits = [c for c in self.captures if keep(c)]
        self.reply({"data": hits[offset:offset + limit],
                    "pagination": {"limit": limit, "offset": offset, "total": len(hits)}})

    def reply(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["serve"])
    p.add_argument("--port", type=int, default=3031)
    args = p.parse_args()
    Handler.captures = load()
    print(f"fake screenpipe (SYNTHETIC data, {len(Handler.captures)} captures) on http://localhost:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
