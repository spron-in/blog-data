#!/usr/bin/env python3
"""Build the blog charts from the run CSVs."""
import csv
import datetime as dt
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from charts import line_chart, bar_chart, stacked_hbar  # noqa: E402

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
OUT = sys.argv[1] if len(sys.argv) > 1 else RES
GiB = 2**30


def t(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def load(run):
    rows = list(csv.DictReader(open(f"{RES}/{run}-metrics.csv")))
    events = {}
    for line in open(f"{RES}/{run}.events"):
        ts, what = line.strip().split(" ", 1)
        events[what] = t(ts)
    t0 = events["migration created"]
    for r in rows:
        r["min"] = (t(r["ts"]) - t0).total_seconds() / 60
    rows = [r for r in rows if r["min"] >= 0]
    return rows, events, t0


def phases(rows, events, t0):
    first = lambda cond: next((r["min"] for r in rows if cond(r)), None)
    return {
        "attached": first(lambda r: int(r["src_replicas"]) > 0),
        # The target may hold old keys until flushTarget empties it.
        "loading": next((r["min"] for i, r in enumerate(rows) if int(r["dst_keys"]) > 1000
                         and any(int(x["dst_keys"]) <= 1000 for x in rows[:i])), None),
        "copied": first(lambda r: r["w_copy_done"] == "true"),
        "sync": first(lambda r: r["w_initial_sync"] == "true"),
        "cutover": (events["cutover requested"] - t0).total_seconds() / 60,
        "done": first(lambda r: r["w_state"] == "completed"),
        "cutover_s": (events["cutover finished"] - events["cutover requested"]).total_seconds(),
    }


runs = {}
for run in sys.argv[2:] or ["redis-50g", "redis-150m"]:
    try:
        runs[run] = load(run)
    except FileNotFoundError:
        pass

for run, (rows, events, t0) in runs.items():
    p = phases(rows, events, t0)
    print(run, {k: round(v, 2) if v else v for k, v in p.items()})
    rows = [r for r in rows if p["done"] is None or r["min"] <= p["done"] + 0.2]
    marks = [(p["attached"], "snapshot"), (p["loading"], "loading"), (p["sync"], "in sync"), (p["cutover"], "cutover")]
    label = "50 GiB, 47M keys" if run == "redis-50g" else "150M keys, 20 GiB"
    line_chart(f"{OUT}/{run}-keys.svg",
               f"Keys on the Valkey target over time ({label})",
               "Minutes since the migration was created. The source kept taking ~2,000 writes/s until the cutover.",
               [("Valkey target keys (millions)", [(r["min"], int(r["dst_keys"]) / 1e6) for r in rows]),
                ("Redis source keys (millions)", [(r["min"], int(r["src_keys"]) / 1e6) for r in rows])],
               "minutes", "keys, millions", markers=[m for m in marks if m[0] is not None],
               ymax=max(int(r["src_keys"]) for r in rows) / 1e6 * 1.3)
    line_chart(f"{OUT}/{run}-source-memory.svg",
               f"Source Redis memory during the migration ({label})",
               "Largest shard's RSS, and copy-on-write memory of the source's fork(s) (RDB saves and the snapshot for the migration).",
               [("largest shard RSS, GiB", [(r["min"], int(r["src_max_rss"]) / GiB) for r in rows]),
                ("fork copy-on-write, all shards, GiB", [(r["min"], int(r["src_cow"]) / GiB) for r in rows])],
               "minutes", "GiB", markers=[m for m in marks if m[0] is not None])

if runs:
    groups = []
    for run, (rows, events, t0) in runs.items():
        p = phases(rows, events, t0)
        # Last sample before the cutover request: both sides hold the same data.
        before = [r for r in rows if r["min"] < p["cutover"]][-1]
        label = "Dataset A: 47M mixed keys" if run == "redis-50g" else "Dataset B: 150M small strings"
        groups.append((label, [int(before["src_used"]) / GiB, int(before["dst_used"]) / GiB]))
        print(run, "used_memory src/dst GiB", groups[-1][1], "keys", before["src_keys"], before["dst_keys"])
    bar_chart(f"{OUT}/memory-redis-vs-valkey.svg",
              "Same data, less memory: Redis 7.2 vs Valkey 9.0",
              "used_memory summed over 3 primaries, sampled just before the cutover, when both sides held the same keys.",
              groups, ["Redis 7.2 (source)", "Valkey 9.0 (target)"], "GiB")

if runs:
    rows_ = []
    for run, (rows, events, t0) in runs.items():
        p = phases(rows, events, t0)
        label = "A: 50 GiB, 47M keys" if run == "redis-50g" else "B: 20 GiB, 150M keys"
        rows_.append((label, [p["attached"], p["loading"] - p["attached"], p["copied"] - p["loading"],
                              p["sync"] - p["copied"], p["cutover_s"] / 60]))
        print(run, [round(v, 2) for v in rows_[-1][1]])
    stacked_hbar(f"{OUT}/migration-phases.svg",
                 "Where the time went: from creating the migration to the cutover",
                 "Minutes per phase (5s samples). Time spent in sync before we pressed Cutover is not included.",
                 rows_, ["preflight, wait for a running save", "source snapshot + transfer",
                         "load into Valkey", "catch up", "cutover"])
