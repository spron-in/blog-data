"""Summarize the threshold studies and load runs: python analyze.py [results-dir]."""
import glob
import json
import os
import sys

import numpy as np

RES = sys.argv[1] if len(sys.argv) > 1 else "/work"
for m in ("minilm", "bge-base"):
    rows = json.load(open(f"{RES}/eval-{m}.json"))
    pos = np.array([r["dist"] for r in rows if r["kind"] == "paraphrase" and r["nearest"] == r["group"]])
    neg = np.array([r["dist"] for r in rows if r["kind"] == "near_miss"])
    auc = np.mean([(p < n) + 0.5 * (p == n) for p in pos for n in neg])
    best = max(((np.mean(pos <= t) - np.mean(neg <= t), t) for t in np.arange(0.01, 0.6, 0.01)))
    print(f"{m}: AUC paraphrase-vs-nearmiss {auc:.3f}; best Youden J {best[0]:.2f} at t={best[1]:.2f} "
          f"(para {np.mean(pos <= best[1]):.0%}, nearmiss {np.mean(neg <= best[1]):.0%})")
print()
print("run         hits  exact  semantic  false  tokens   rps  hit_p50 miss_p50")
for f in sorted(glob.glob(f"{RES}/run-*.json")):
    d = json.load(open(f)); res = d["results"]; n = len(res)
    hits = [r for r in res if r["result"] == "hit"]
    exact = sum(r["dist"] < 1e-3 for r in hits)
    tok = sum(r["usage"]["total_tokens"] for r in res if r.get("usage"))
    p50 = lambda k: np.percentile([r["latency"] for r in res if r["result"] == k], 50) * 1000 if any(r["result"] == k for r in res) else 0
    print(f"{os.path.basename(f)[4:-5]:<10} {len(hits)/n:5.1%} {exact/n:6.1%} {(len(hits)-exact)/n:8.1%} {sum(r.get('false_hit', False) for r in res):6d} {tok:7d} {n/d['elapsed']:5.1f} {p50('hit'):7.0f} {p50('miss'):8.0f}")
