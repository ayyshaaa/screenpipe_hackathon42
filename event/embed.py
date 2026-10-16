#!/usr/bin/env python3
"""Embed every session in trail.db -> embeddings.npz (session ids + one vector each).

  python3 embed.py                      # VTX-JEV-2 (Model2Vec, static, CPU)
  python3 embed.py --model hashing      # no-download stand-in for tests / emergencies
  python3 embed.py --input text         # embed text only (default: window + text)

Vectors are L2-normalised, so cosine similarity = dot product.
At the event: export HF_HUB_OFFLINE=1 so the cached model is used without the network.
"""
import argparse
import hashlib
import re
import time

import numpy as np

from common import DB_PATH, load_sessions

DIM_HASHING = 256


def session_text(s, mode):
    if mode == "text":
        return s["text"]
    return f"{s['app']} | {s['window']}\n{s['text']}"


def hashing_embed(texts):
    """Bag of words hashed into 256 numbers, averaged. Same idea as a static model, minus the meaning."""
    out = np.zeros((len(texts), DIM_HASHING), dtype=np.float32)
    for i, text in enumerate(texts):
        for tok in re.findall(r"\w+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            out[i, h % DIM_HASHING] += 1 if (h >> 9) & 1 else -1
    return out


def normalise(v):
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--model", default="VTXAI/VTX-JEV-2", help="Hugging Face id or local folder, or 'hashing'")
    p.add_argument("--input", choices=["window+text", "text"], default="window+text")
    p.add_argument("--out", default="embeddings.npz")
    p.add_argument("--no-center", action="store_true", help="skip removing the average vector")
    args = p.parse_args()

    sessions = load_sessions(args.db)
    texts = [session_text(s, args.input) for s in sessions]
    t0 = time.time()
    if args.model == "hashing":
        vectors = hashing_embed(texts)
    else:
        from model2vec import StaticModel  # imported here so --model hashing works without it
        vectors = StaticModel.from_pretrained(args.model).encode(texts)
    vectors = normalise(np.asarray(vectors, dtype=np.float32))
    if not args.no_center:
        # Static models put every text in roughly the same direction, so almost every pair
        # looks similar (cosine > 0.8). Removing the average vector keeps only what differs.
        vectors = normalise(vectors - vectors.mean(axis=0, keepdims=True))
    np.savez(args.out, ids=np.array([s["session_id"] for s in sessions]), vectors=vectors,
             model=args.model, input=args.input, centered=not args.no_center)
    print(f"embedded {len(sessions)} sessions with {args.model} ({args.input}, "
          f"{'centered' if not args.no_center else 'not centered'}) in {time.time() - t0:.2f}s -> {args.out}")


if __name__ == "__main__":
    main()
