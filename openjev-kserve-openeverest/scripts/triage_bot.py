"""A GitHub triage bot whose rules are the repository's own label descriptions.

For each issue it asks OpenJev three things in one request:
  kind        one of the kind labels, described by the repo's label descriptions
  area        one of the area labels, same
  needs_info  would a maintainer have to ask the reporter for more information?

A label is applied only when OpenJev is at least --threshold sure. Everything
else keeps `needs-triage` for a human. Dry run unless --apply is given.

  ./scripts/with-openjev.sh python3 scripts/triage_bot.py --repo openeverest/openeverest --label needs-triage --limit 30
  ./scripts/with-openjev.sh python3 scripts/triage_bot.py --repo openeverest/openeverest --issue 1234 --apply
"""
import argparse
import json
import subprocess

from openjev import decide
from prepare_issues import clean

KIND_LABELS = ["bug", "enhancement", "question", "documentation", "chore"]
AREA_LABELS = ["ui", "storage", "database", "provider", "plugin", "ops", "infra", "ai"]
NEEDS_INFO_LABEL = "triage/needs-information"


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def label_criteria(repo, names):
    labels = {l["name"]: l["description"] for l in json.loads(gh("label", "list", "-R", repo, "-L", "200", "--json", "name,description"))}
    return {n: labels.get(n) or None for n in names}


def questions(repo):
    return {
        "kind": {"type": "choice", "instructions": f"You triage GitHub issues for {repo}. Which kind label fits this issue?",
                 "criteria": label_criteria(repo, KIND_LABELS)},
        "area": {"type": "choice", "instructions": f"You triage GitHub issues for {repo}. Which area label fits this issue best?",
                 "criteria": label_criteria(repo, AREA_LABELS)},
        "needs_info": {"type": "noul", "instructions": "Would a maintainer have to ask the reporter for more information "
                                                        "(versions, logs, steps to reproduce) before working on this issue?"},
    }


def plan(answers, threshold):
    add = []
    for q in ("kind", "area"):
        a = answers[q]
        if a["probabilities"][a["choice"]] >= threshold:
            add.append(a["choice"])
    if answers["needs_info"]["noul"] >= threshold:
        add.append(NEEDS_INFO_LABEL)
    return add


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", type=int)
    ap.add_argument("--label", default="needs-triage", help="triage open issues carrying this label")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out", default="results/triage-bot.jsonl")
    a = ap.parse_args()

    fields = "number,title,body,labels,url"
    if a.issue:
        issues = [json.loads(gh("issue", "view", str(a.issue), "-R", a.repo, "--json", fields))]
    else:
        issues = json.loads(gh("issue", "list", "-R", a.repo, "--state", "open", "--label", a.label,
                               "-L", str(a.limit), "--json", fields))
    qs = questions(a.repo)
    with open(a.out, "w") as out:
        for i in issues:
            state = f"GitHub issue #{i['number']}\nTitle: {i['title']}\n\n{clean(i['body'])}"
            answers, ms, _ = decide(state, qs)
            add = plan(answers, a.threshold)
            existing = sorted(l["name"] for l in i["labels"])
            out.write(json.dumps({"number": i["number"], "url": i["url"], "title": i["title"], "existing": existing,
                                  "answers": answers, "add": add, "ms": round(ms)}) + "\n")
            k, ar = answers["kind"], answers["area"]
            print(f"#{i['number']:<5} {i['title'][:58]:<58} kind={k['choice']}({k['probabilities'][k['choice']]:.2f}) "
                  f"area={ar['choice']}({ar['probabilities'][ar['choice']]:.2f}) info={answers['needs_info']['noul']:.2f} "
                  f"-> {', '.join(add) or 'human'}  [{ms:.0f} ms]")
            if a.apply and add:
                gh("issue", "edit", str(i["number"]), "-R", a.repo, "--add-label", ",".join(add))


if __name__ == "__main__":
    main()
