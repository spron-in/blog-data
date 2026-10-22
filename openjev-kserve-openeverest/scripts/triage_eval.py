"""Experiment 1: triage real kserve/kserve issues with OpenJev and score it
against the maintainers' kind/ labels.

  python triage_eval.py              # run all issues in data/issues.jsonl
  python triage_eval.py --limit 20   # quick check

Writes results/triage.jsonl (one line per issue: label, the four typed answers,
request latency and prompt tokens) and prints accuracy as it goes. The four
questions go out in ONE request per issue; only `kind` has ground truth, the
others show what else a triage bot would read off the same pass.
"""
import argparse
import json
import pathlib
from concurrent.futures import ThreadPoolExecutor

from openjev import decide

QUESTIONS = {
    "kind": {
        "type": "choice",
        "instructions": "You triage GitHub issues for KServe, a Kubernetes model-serving platform. What kind of issue is this?",
        "criteria": {
            "bug": "Something in KServe is broken, crashes, or behaves differently from what is documented or expected",
            "feature": "A request for new functionality, an enhancement, or a design proposal",
            "question": "The author asks for help, how to do something, or wants clarification; nothing is necessarily broken",
        },
    },
    "area": {
        "type": "choice",
        "instructions": "Which part of KServe is this issue mainly about?",
        "criteria": {
            "llm": "LLM serving, vLLM, Hugging Face runtime, generative models",
            "runtimes": "other model servers: sklearn, xgboost, Triton, TorchServe, custom containers, ServingRuntimes",
            "storage": "model download, storage initializer, S3, GCS, PVC, storage URIs",
            "networking": "ingress, Istio, Knative, gateways, routing, TLS, URLs",
            "autoscaling": "scaling, replicas, KEDA, HPA, scale to zero, GPU and resource requests",
            "controller": "InferenceService API, CRDs, controller, webhooks, status",
            "python": "Python SDK, KServe Python model server, inference protocol v1/v2, gRPC",
            "docs": "documentation and examples",
            "build": "CI, tests, releases, Helm charts, installation, images",
        },
    },
    "needs_info": {
        "type": "noul",
        "instructions": "Would a maintainer need to ask the author for more information (logs, versions, YAML, reproduction steps) before acting on this issue?",
    },
    "priority": {
        "type": "score",
        "instructions": "How urgent is this issue for the KServe maintainers?",
        "criteria": ["nice to have", "normal", "important: many users affected",
                     "critical: data loss, security or a production outage"],
    },
}

# v2 changes only the criteria text of `kind`, written after reading the misses
# in the dev split (the first 99 issues). It spells out the project's convention:
# dependency bumps and deprecations count as bugs; trouble with one's own
# install, environment or usage counts as a question.
KIND_V2 = {
    "type": "choice",
    "instructions": "You triage GitHub issues for KServe, a Kubernetes model-serving platform. What kind of issue is this?",
    "criteria": {
        "bug": "KServe itself is defective and the maintainers must fix it: a reproducible failure in KServe code, "
               "a wrong or broken example or doc, or an outdated, vulnerable or unmaintained dependency to upgrade or remove",
        "feature": "A request for new capability or a change to KServe's behaviour or API that does not exist yet",
        "question": "The author needs help with their own setup, installation, environment or usage, or asks whether "
                    "or how something is supported; KServe is not shown to be broken",
    },
}
KIND_V0 = {
    "type": "choice",
    "instructions": "What kind of GitHub issue is this?",
    "criteria": {"bug": None, "feature": None, "question": None},
}
POLICIES = {"v0": {"kind": KIND_V0}, "v1": QUESTIONS, "v2": {"kind": KIND_V2}}


def run_one(issue, questions):
    state = f"GitHub issue #{issue['number']}\nTitle: {issue['title']}\n\n{issue['text']}"
    answers, ms, usage = decide(state, questions)
    return {"number": issue["number"], "url": issue["url"], "title": issue["title"], "label": issue["label"],
            "answers": answers, "ms": round(ms, 1), "tokens": usage.get("input_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/issues.jsonl")
    ap.add_argument("--out", default="results/triage.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--policy", choices=sorted(POLICIES), default="v1")
    a = ap.parse_args()
    questions = POLICIES[a.policy]

    issues = [json.loads(line) for line in open(a.data)]
    if a.limit:
        issues = issues[: a.limit]
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    correct = done = 0
    with open(a.out, "w") as out, ThreadPoolExecutor(a.concurrency) as pool:
        for r in pool.map(lambda i: run_one(i, questions), issues):
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            done += 1
            correct += r["answers"]["kind"]["choice"] == r["label"]
            if done % 25 == 0 or done == len(issues):
                print(f"{done}/{len(issues)} accuracy={correct / done:.3f} last_ms={r['ms']}", flush=True)


if __name__ == "__main__":
    main()
