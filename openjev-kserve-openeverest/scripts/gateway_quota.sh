#!/usr/bin/env bash
# Token quota on the Envoy AI Gateway for a TypeSafe decision model.
#
# Sets topology.parameters.tokenLimitPerHour on the Instance, sends the same
# decision (239 input tokens) until the Gateway answers 429, then removes the
# limit again. Needs a Redis-compatible rate-limit backend configured in the
# provider chart (envoy-gateway.config.envoyGateway.rateLimit.backend).
set -euo pipefail
NS=${NS:-decisions}
INSTANCE=${INSTANCE:-openjev}
LIMIT=${LIMIT:-600}

conn() { kubectl -n "$NS" get secret "$INSTANCE-conn" -o jsonpath="{.data.$1}" | base64 -d; }
URI=$(conn uri); MODEL=$(conn model); KEY=$(conn password)
BODY='{"model": "'"$MODEL"'", "state": "Customer message: I was charged twice for my order last week and nobody has replied.",
       "questions": {"route": {"type": "choice", "instructions": "Which team should handle this?",
                               "criteria": {"billing": null, "shipping": null, "technical": null}},
                     "angry": {"type": "noul", "instructions": "Is the customer angry?"},
                     "urgency": {"type": "score", "instructions": "How urgent is this?",
                                 "criteria": ["can wait", "this week", "today", "right now"]}}}'

kubectl -n "$NS" patch instance "$INSTANCE" --type merge -p "{\"spec\":{\"topology\":{\"parameters\":{\"tokenLimitPerHour\":$LIMIT}}}}" >/dev/null
trap 'kubectl -n "$NS" patch instance "$INSTANCE" --type json -p "[{\"op\":\"remove\",\"path\":\"/spec/topology/parameters/tokenLimitPerHour\"}]" >/dev/null' EXIT
sleep 20  # the provider applies the BackendTrafficPolicy, Envoy picks it up

echo "tokenLimitPerHour=$LIMIT"
used=0
for i in $(seq 1 8); do
  out=$(curl -sk -w '\n%{http_code}' "$URI/v1/systemone" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$BODY")
  code=$(tail -1 <<<"$out")
  if [ "$code" = 200 ]; then
    used=$((used + $(sed '$d' <<<"$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["usage"]["input_tokens"])')))
  fi
  echo "request $i -> $code (tokens charged so far: $used)"
  [ "$code" = 429 ] && break
done
[ "$code" = 429 ]
echo "OK: the Gateway enforced the token quota on /typesafe/v1/systemone"
