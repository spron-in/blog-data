"""Analyse results/triage.jsonl: accuracy, confusion matrix, calibration and
the accuracy you get when you only auto-label above a confidence threshold.

  python analyze_triage.py            # prints a report, writes results/triage-summary.json
"""
import collections
import json
import statistics

KINDS = ["bug", "feature", "question"]


def main(path="results/triage.jsonl", out="results/triage-summary.json"):
    rows = [json.loads(line) for line in open(path)]
    for r in rows:
        k = r["answers"]["kind"]
        r["pred"], r["p"] = k["choice"], k["probabilities"][k["choice"]]
        r["ok"] = r["pred"] == r["label"]
    n = len(rows)
    acc = sum(r["ok"] for r in rows) / n
    print(f"issues={n} accuracy={acc:.3f}")

    confusion = {t: {p: 0 for p in KINDS} for t in KINDS}
    for r in rows:
        confusion[r["label"]][r["pred"]] += 1
    print("\nlabel \\ predicted  " + "  ".join(f"{k:>8}" for k in KINDS))
    for t in KINDS:
        print(f"{t:>17}  " + "  ".join(f"{confusion[t][p]:>8}" for p in KINDS))
    per_class = {t: confusion[t][t] / sum(confusion[t].values()) for t in KINDS}
    print("recall:", {k: round(v, 3) for k, v in per_class.items()})

    # Selective triage: auto-label only when p(choice) >= threshold, send the rest to a human.
    curve = []
    for t in [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.99]:
        sel = [r for r in rows if r["p"] >= t]
        curve.append({"threshold": t, "coverage": round(len(sel) / n, 4),
                      "accuracy": round(sum(r["ok"] for r in sel) / len(sel), 4) if sel else None, "n": len(sel)})
    print("\nthreshold coverage accuracy")
    for c in curve:
        print(f"  {c['threshold']:.2f}     {c['coverage']:.2f}     {c['accuracy']}")

    # Reliability: bucket by stated probability, compare with observed accuracy.
    buckets = collections.defaultdict(list)
    for r in rows:
        buckets[min(int(r["p"] * 10), 9)].append(r)
    reliability, ece = [], 0.0
    for b in sorted(buckets):
        rs = buckets[b]
        conf = statistics.mean(r["p"] for r in rs)
        obs = sum(r["ok"] for r in rs) / len(rs)
        ece += len(rs) / n * abs(conf - obs)
        reliability.append({"bin": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "n": len(rs), "stated": round(conf, 3), "observed": round(obs, 3)})
    print("\nreliability (stated vs observed):")
    for x in reliability:
        print(f"  {x['bin']}  n={x['n']:>3}  stated={x['stated']:.2f}  observed={x['observed']:.2f}")
    print(f"expected calibration error: {ece:.3f}")

    ms = [r["ms"] for r in rows]
    toks = [r["tokens"] for r in rows]
    print(f"\nlatency per issue (4 questions, concurrency 4): p50={statistics.median(ms):.0f} ms "
          f"p90={sorted(ms)[int(0.9 * n)]:.0f} ms; prompt tokens per issue p50={statistics.median(toks):.0f}")

    confident_misses = sorted([r for r in rows if not r["ok"]], key=lambda r: -r["p"])
    print("\nmost confident disagreements with the label:")
    for r in confident_misses[:12]:
        print(f"  #{r['number']:<5} label={r['label']:<8} openjev={r['pred']:<8} p={r['p']:.2f}  {r['title'][:70]}")

    areas = collections.Counter(r["answers"]["area"]["choice"] for r in rows)
    print("\narea distribution:", dict(areas.most_common()))

    summary = {
        "n": n, "accuracy": round(acc, 4), "confusion": confusion, "recall": per_class,
        "curve": curve, "reliability": reliability, "ece": round(ece, 4),
        "latency_ms_p50": round(statistics.median(ms)), "tokens_p50": round(statistics.median(toks)),
        "issues": [{"n": r["number"], "url": r["url"], "title": r["title"], "label": r["label"],
                    "kind": r["answers"]["kind"]["probabilities"], "area": r["answers"]["area"]["choice"],
                    "area_p": r["answers"]["area"]["probabilities"][r["answers"]["area"]["choice"]],
                    "needs_info": r["answers"]["needs_info"]["noul"], "priority": r["answers"]["priority"]["score"],
                    "ms": r["ms"]} for r in rows],
    }
    json.dump(summary, open(out, "w"), indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
