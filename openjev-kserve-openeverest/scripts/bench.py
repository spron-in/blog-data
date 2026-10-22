"""Latency and throughput of OpenJev Flash 9B on the Instance's GPU.

  python bench.py   # writes results/bench.json

Cases (one question per request unless noted):
  short      a one-line text decision, 3 options, sequential
  cold-1k    distinct ~1k-token states (nothing cached), sequential
  warm-1k    the same ~1k-token state, a new question each time (prefix cache hit)
  cold-4k    distinct ~4k-token states, sequential
  warm-4k    the same ~4k-token state, a new question each time
  throughput distinct ~1k-token decisions at concurrency 1/4/8/16

  python bench.py fanout   # one request with 1..16 questions about one fresh ~1k-token state
"""
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from openjev import decide, version

ISSUES = [json.loads(line) for line in open("data/issues.jsonl")]
CORPUS = "\n\n".join(i["title"] + "\n" + i["text"] for i in ISSUES)
QUESTION = {"type": "choice", "instructions": "What kind of GitHub issue is this?",
            "criteria": {"bug": None, "feature": None, "question": None}}
EXTRA_QUESTIONS = [
    "Does the text mention Kubernetes?", "Is a stack trace included?", "Is the author frustrated?",
    "Does it mention GPUs?", "Is a YAML manifest included?", "Does it reference a pull request?",
    "Is Python code included?", "Does it mention a version number?",
]


def state_of(chars, seed):
    """A distinct slice of real issue text, about chars/4 tokens long."""
    start = random.Random(seed).randrange(0, len(CORPUS) - chars)
    return f"[{seed}] " + CORPUS[start:start + chars]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def summarize(name, ms, tokens):
    s = {"case": name, "n": len(ms), "p50_ms": round(statistics.median(ms), 1), "p90_ms": round(pct(ms, 0.9), 1),
         "mean_tokens": round(statistics.mean(tokens))}
    print(json.dumps(s), flush=True)
    return s


def sequential(name, n, make_state, make_q):
    ms, toks = [], []
    for i in range(n):
        _, t, usage = decide(make_state(i), {"q": make_q(i)})
        ms.append(t)
        toks.append(usage.get("input_tokens", 0))
    return summarize(name, ms, toks)


def noul(i):
    return {"type": "noul", "instructions": EXTRA_QUESTIONS[i % len(EXTRA_QUESTIONS)] + f" (check {i})"}


def throughput(conc, n=96, chars=4000):
    states = [state_of(chars, 10_000 * conc + i) for i in range(n)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(conc) as pool:
        lat = list(pool.map(lambda s: decide(s, {"q": QUESTION})[1], states))
    wall = time.perf_counter() - t0
    s = {"case": f"throughput-c{conc}", "n": n, "decisions_per_s": round(n / wall, 2),
         "p50_ms": round(statistics.median(lat), 1), "p90_ms": round(pct(lat, 0.9), 1)}
    print(json.dumps(s), flush=True)
    return s


def fanout(nq, n=10, chars=4000):
    """One request, nq questions about one fresh ~1k-token state: the triage-bot pattern."""
    ms = []
    for i in range(n):
        qs = {f"q{j}": noul(j) for j in range(nq - 1)} | {"kind": QUESTION}
        ms.append(decide(state_of(chars, 50_000 + 100 * nq + i), qs)[1])
    s = {"case": f"fanout-{nq}q", "n": n, "p50_ms": round(statistics.median(ms), 1), "p90_ms": round(pct(ms, 0.9), 1),
         "ms_per_question": round(statistics.median(ms) / nq, 1)}
    print(json.dumps(s), flush=True)
    return s


def main():
    print(json.dumps(version()))
    for i in range(5):  # warm-up
        decide(state_of(2000, 900 + i), {"q": QUESTION})
    if len(sys.argv) > 1 and sys.argv[1] == "fanout":
        out = [fanout(nq) for nq in (1, 2, 4, 8, 16)]
        json.dump(out, open("results/bench-fanout.json", "w"), indent=1)
        return
    out = [
        sequential("short", 50, lambda i: f"Ticket {i}: the checkout page shows a 500 error after I click pay.",
                   lambda i: {"type": "choice", "instructions": "Which team should handle this?",
                              "criteria": {"billing": None, "frontend": None, "backend": None}}),
        sequential("cold-1k", 30, lambda i: state_of(4000, i), lambda i: QUESTION),
        sequential("warm-1k", 30, lambda i: state_of(4000, 7), noul),
        sequential("cold-4k", 20, lambda i: state_of(16000, 100 + i), lambda i: QUESTION),
        sequential("warm-4k", 20, lambda i: state_of(16000, 107), noul),
    ]
    out += [throughput(c) for c in (1, 4, 8, 16)]
    json.dump(out, open("results/bench.json", "w"), indent=1)


if __name__ == "__main__":
    main()
