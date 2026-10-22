"""Build a balanced, label-blind issue set from kserve/kserve.

Input:  data/kserve-kind-{bug,feature,question}.json, fetched with
        gh issue list -R kserve/kserve --state all --label kind/<k> -L 300 \
          --json number,title,body,labels,state,createdAt,url
Output: data/issues.jsonl (one issue per line: number, url, label, title, text)

KServe's issue templates write "/kind bug" or "/kind feature" into the body and
add fixed section headings ("What steps did you take..."). Both give the label
away, so they are removed. Issues with more than one kind/ label are skipped.
"""
import json
import random
import re

MAX_CHARS = 4000
PER_CLASS = 100

DROP_LINE = [
    re.compile(r"^\s*/(kind|area|priority|assign|label)\b.*$", re.I),  # prow-style commands
    re.compile(r"^\s*\*\*[^*\n]{3,120}\*\*\s*:?\s*$"),                   # bold template headings
    re.compile(r"^\s*#{1,6}\s.*$"),                                        # markdown headings
    re.compile(r"^\s*\[[^\]\n]{20,}\]?\s*$"),                             # [bracketed template hints]
    re.compile(r"^\s*(what steps did you take|what did you expect|anything else you would like|"
               r"describe the solution|describe alternatives|environment)\b[^\n]{0,60}:?\s*$", re.I),
    re.compile(r"^\s*[-*]\s*[\w /()`.:-]{2,60}:\s*$"),                    # empty "- Istio Version:" fields
]
LEADING_BOLD = re.compile(r"^\s*\*\*[^*\n]{3,120}\*\*\s*:?\s*")


def clean(body):
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    out = []
    for line in body.splitlines():
        if any(p.match(line) for p in DROP_LINE):
            continue
        out.append(LEADING_BOLD.sub("", line))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return text[:MAX_CHARS] + (" …[truncated]" if len(text) > MAX_CHARS else "")


def main():
    rng = random.Random(42)
    rows = []
    for kind in ("bug", "feature", "question"):
        issues = json.load(open(f"data/kserve-kind-{kind}.json"))
        issues = [i for i in issues if sum(l["name"].startswith("kind/") for l in i["labels"]) == 1]
        rng.shuffle(issues)
        for i in issues[:PER_CLASS]:
            rows.append({"number": i["number"], "url": i["url"], "label": kind,
                         "title": i["title"], "text": clean(i["body"]), "created": i["createdAt"]})
    rng.shuffle(rows)
    with open("data/issues.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    leaks = sum(bool(re.search(r"(?im)^\s*/kind\b|what steps did you take|describe the solution|to help us debug", r["text"])) for r in rows)
    print(f"{len(rows)} issues written, {leaks} still contain template phrases")


if __name__ == "__main__":
    main()
