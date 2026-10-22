#!/usr/bin/env bash
# Smoke test: the model card's three-question request against the Instance.
# Usage: ./scripts/smoke.sh   (port-forwards the predictor Service to :3000)
set -euo pipefail
NS=decisions
TOKEN=$(kubectl -n $NS get secret openjev-shim -o jsonpath='{.data.apiKey}' | base64 -d)

kubectl -n $NS port-forward svc/openjev-predictor 3000:80 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT
until curl -s -o /dev/null http://127.0.0.1:3000/; do sleep 1; done

echo "--- without the token (expect 401)"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/v1/version

echo "--- /v1/version"
curl -s http://127.0.0.1:3000/v1/version -H "Authorization: Bearer $TOKEN"; echo

echo "--- /v1/systemone"
curl -s http://127.0.0.1:3000/v1/systemone \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
  "model": "openjev",
  "state": "Customer message: I was charged twice for my order last week and nobody has replied.",
  "questions": {
    "route":   {"type": "choice", "instructions": "Which team should handle this?",
                "criteria": {"billing": null, "shipping": null, "technical": null}},
    "angry":   {"type": "noul",   "instructions": "Is the customer angry?"},
    "urgency": {"type": "score",  "instructions": "How urgent is this?",
                "criteria": ["can wait", "this week", "today", "right now"]}
  }
}' | python3 -m json.tool
