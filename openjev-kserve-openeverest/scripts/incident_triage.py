"""Experiment 2: OpenJev as the fast decision step of a Kubernetes ops agent.

For every pod in a namespace, the state is what an on-call engineer would look
at first: `kubectl describe pod` and the last log lines (current and previous
container). OpenJev answers five questions about it in one request. The
ground-truth cause sits on the owning Deployment's `incident/cause` label, which
never appears in the state.

  ./scripts/with-openjev.sh python3 scripts/incident_triage.py --policy v1
  ./scripts/with-openjev.sh python3 scripts/incident_triage.py --policy v2
"""
import argparse
import json
import re
import subprocess

from openjev import decide

QUESTIONS = {
    "cause": {
        "type": "choice",
        "instructions": "You are the on-call SRE. What is the most likely root cause of this pod's state?",
        "criteria": {
            "out-of-memory": "the container is killed for exceeding its memory limit (OOMKilled)",
            "image-pull": "the image cannot be pulled: wrong name or tag, or missing registry credentials",
            "missing-config": "a ConfigMap, Secret or required setting or environment variable is missing",
            "dependency-down": "the application starts but cannot reach a database or another service it depends on",
            "unschedulable": "the pod cannot be scheduled: not enough CPU, memory or GPUs, or no node matches its selectors",
            "bad-probe": "a liveness or readiness probe is misconfigured or failing while the application itself runs",
            "storage": "a PersistentVolumeClaim is not bound or a volume cannot be mounted",
            "bad-command": "the container command or entrypoint does not exist or is wrong",
            "healthy": "nothing is wrong; the workload runs normally",
        },
    },
    "owner": {
        "type": "choice",
        "instructions": "Who has to act to fix this?",
        "criteria": {
            "app-team": "the team that owns the application code, image or its configuration",
            "platform-team": "the cluster or platform team: nodes, capacity, storage classes, networking",
            "nobody": "no one; nothing is broken",
        },
    },
    "restart_helps": {"type": "noul", "instructions": "Would simply deleting the pod so it restarts fix the problem?"},
    "page_now": {"type": "noul", "instructions": "Should a human be paged right now, given this is a production namespace?"},
    "severity": {"type": "score", "instructions": "How severe is this for users of the service?",
                 "criteria": ["none", "minor", "degraded", "outage"]},
}

# v2: the on-call rule of thumb written into the question. The current state
# matters; a probe warning only while the container was starting is normal.
QUESTIONS_V2 = {
    **QUESTIONS,
    "cause": {
        **QUESTIONS["cause"],
        "instructions": "You are the on-call SRE. Judge the pod by its current state (Status, Ready, Restart Count, "
                        "recent events), not by one-off events from container start-up. What is the most likely root cause?",
        "criteria": {**QUESTIONS["cause"]["criteria"],
                     "healthy": "nothing is wrong now: the pod is Running and Ready without restarts; "
                                "a probe failure only during start-up is normal"},
    },
}
POLICIES = {"v1": QUESTIONS, "v2": QUESTIONS_V2}

NOISE = re.compile(r"^(Volumes|QoS Class|Node-Selectors|Tolerations|  kube-api-access)", re.M)


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def describe(ns, pod):
    """kubectl describe without the boilerplate sections that never carry the answer."""
    text = sh("kubectl", "-n", ns, "describe", "pod", pod)
    keep, skip = [], False
    for line in text.splitlines():
        if NOISE.match(line):
            skip = True
        elif line and not line.startswith(" "):
            skip = False
        if not skip:
            keep.append(line)
    return "\n".join(keep)


def state_for(ns, pod):
    logs = sh("kubectl", "-n", ns, "logs", pod, "--all-containers", "--tail=15").strip()
    prev = sh("kubectl", "-n", ns, "logs", pod, "--all-containers", "--previous", "--tail=15").strip()
    return (f"$ kubectl describe pod {pod}\n{describe(ns, pod)}\n\n"
            f"$ kubectl logs {pod} --tail=15\n{logs or '(no output)'}\n\n"
            f"$ kubectl logs {pod} --previous --tail=15\n{prev or '(no previous container)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", default="incidents")
    ap.add_argument("--out", default="results/incidents.jsonl")
    ap.add_argument("--policy", choices=sorted(POLICIES), default="v1")
    a = ap.parse_args()
    questions = POLICIES[a.policy]

    deployments = json.loads(sh("kubectl", "-n", a.namespace, "get", "deploy", "-o", "json"))["items"]
    truth = {d["spec"]["selector"]["matchLabels"]["app"]: d["metadata"]["labels"].get("incident/cause") for d in deployments}
    pods = json.loads(sh("kubectl", "-n", a.namespace, "get", "pods", "-o", "json"))["items"]

    correct = 0
    with open(a.out, "w") as out:
        for p in sorted(pods, key=lambda p: p["metadata"]["name"]):
            name, app = p["metadata"]["name"], p["metadata"]["labels"].get("app")
            state = state_for(a.namespace, name)
            answers, ms, usage = decide(state, questions)
            cause = answers["cause"]
            ok = cause["choice"] == truth.get(app)
            correct += ok
            row = {"pod": name, "app": app, "truth": truth.get(app), "answers": answers, "ms": round(ms),
                   "tokens": usage.get("input_tokens"), "state": state}
            out.write(json.dumps(row) + "\n")
            print(f"{'OK ' if ok else 'XX '} {app:<16} truth={truth.get(app):<16} cause={cause['choice']:<16} "
                  f"p={cause['probabilities'][cause['choice']]:.2f} owner={answers['owner']['choice']:<13} "
                  f"restart={answers['restart_helps']['noul']:.2f} page={answers['page_now']['noul']:.2f} "
                  f"sev={answers['severity']['score']:.1f} {ms:.0f}ms {usage.get('input_tokens')}tok")
    print(f"\n{correct}/{len(pods)} root causes correct")


if __name__ == "__main__":
    main()
