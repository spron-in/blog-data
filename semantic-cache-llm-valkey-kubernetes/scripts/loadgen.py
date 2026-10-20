"""Replay the question bank against /ask with Zipf-distributed popularity."""
import argparse
import asyncio
import json
import random
import time

import httpx
import numpy as np


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=600)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--zipf", type=float, default=1.1)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    bank = json.load(open("/work/questions.json"))
    rng = random.Random(args.seed)
    rng.shuffle(bank)
    weights = 1 / np.arange(1, len(bank) + 1) ** args.zipf
    weights /= weights.sum()
    picks = np.random.default_rng(args.seed).choice(len(bank), size=args.requests, p=weights)
    work = [(bank[i]["group"], rng.choice(bank[i]["variants"])) for i in picks]

    client = httpx.AsyncClient(base_url="http://rag-app:8000", timeout=300)
    if not args.no_cache:
        (await client.post("/reset")).raise_for_status()
    queue = asyncio.Queue()
    for item in work:
        queue.put_nowait(item)
    results = []

    async def worker():
        while not queue.empty():
            group, q = queue.get_nowait()
            t = time.perf_counter()
            r = await client.post("/ask", json={"question": q, "group": group, "threshold": args.threshold,
                                                "use_cache": not args.no_cache})
            body = r.json() if r.status_code == 200 else {"result": f"http_{r.status_code}"}
            body.pop("answer", None)
            results.append({"group": group, "q": q, "status": r.status_code,
                            "latency": time.perf_counter() - t, "end": time.time(), **body})

    start = time.time()
    await asyncio.gather(*(worker() for _ in range(args.concurrency)))
    elapsed = time.time() - start
    json.dump({"args": vars(args), "start": start, "elapsed": elapsed, "results": results}, open(args.out, "w"))

    lat = {k: np.array([r["latency"] for r in results if r["result"] == k]) for k in ("hit", "miss")}
    hits, misses = len(lat["hit"]), len(lat["miss"])
    false_hits = sum(r.get("false_hit", False) for r in results)
    tokens = sum(r["usage"]["total_tokens"] for r in results if r.get("usage"))
    errors = sum(r["status"] != 200 for r in results)
    print(f"{args.out}: {len(results)} req in {elapsed:.0f}s ({len(results) / elapsed:.1f} rps), "
          f"hits {hits} ({hits / len(results):.1%}), false hits {false_hits}, errors {errors}, LLM tokens {tokens}")
    for k, v in lat.items():
        if len(v):
            print(f"  {k}: p50 {np.percentile(v, 50) * 1000:.0f} ms, p95 {np.percentile(v, 95) * 1000:.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
