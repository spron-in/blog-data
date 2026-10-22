"""Compact the experiment results into the data the blog post's widgets embed.

  python scripts/blog_widgets.py   # writes results/blog-widgets.json
"""
import json
import re

QUIZ = [3706, 2863, 2167, 2548, 3763, 3784]  # issue numbers shown in the "be the triager" quiz
HELD_OUT = {"cart-cache", "api-gateway", "billing-api", "ml-scorer", "geo-api", "events-consumer", "pdf-render"}


def load(path):
    return [json.loads(line) for line in open(path)]


def excerpt(text, n=420):
    text = re.sub(r"```.*?```", " [code] ", text, flags=re.S)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


def main():
    issues = {i["number"]: i for i in load("data/issues.jsonl")}
    v1 = load("results/triage.jsonl")
    by_n = {r["number"]: r for r in v1}

    curve = [[r["answers"]["kind"]["probabilities"][r["answers"]["kind"]["choice"]],
              int(r["answers"]["kind"]["choice"] == r["label"])] for r in v1]

    quiz = []
    for n in QUIZ:
        r = by_n[n]
        a = r["answers"]
        quiz.append({"n": n, "url": r["url"], "title": r["title"], "text": excerpt(issues[n]["text"]),
                     "label": r["label"], "kind": a["kind"]["probabilities"],
                     "area": [a["area"]["choice"], a["area"]["probabilities"][a["area"]["choice"]]],
                     "needs_info": a["needs_info"]["noul"], "priority": a["priority"]["score"]})

    status = dict(line.rstrip("\n").split("\t", 1) for line in open("results/incident-pod-status.tsv"))
    inc = []
    rows = {p: {r["app"]: r for r in load(f"results/incidents-all-{p}.jsonl")} for p in ("v1", "v2")}
    for app in sorted(rows["v1"]):
        out = {"app": app, "status": status[app].replace("\t", " · restarts "), "truth": rows["v1"][app]["truth"],
               "held_out": app in HELD_OUT}
        for p in ("v1", "v2"):
            a = rows[p][app]["answers"]
            top = sorted(a["cause"]["probabilities"].items(), key=lambda kv: -kv[1])[:3]
            out[p] = {"cause": [[k, round(v, 3)] for k, v in top], "owner": a["owner"]["choice"],
                      "restart": a["restart_helps"]["noul"], "page": a["page_now"]["noul"],
                      "severity": a["severity"]["score"], "ms": rows[p][app]["ms"]}
        inc.append(out)

    json.dump({"curve": curve, "quiz": quiz, "incidents": inc}, open("results/blog-widgets.json", "w"),
              separators=(",", ":"))
    print(f"curve={len(curve)} quiz={len(quiz)} incidents={len(inc)}")


if __name__ == "__main__":
    main()
