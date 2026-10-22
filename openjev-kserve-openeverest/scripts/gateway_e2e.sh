#!/usr/bin/env bash
# End-to-end check of OpenJev on the Envoy AI Gateway (provider-kserve with
# apiSchema: TypeSafe), from outside the cluster through the public LoadBalancer.
#
# Everything comes from the Instance's connection Secret: base URL, model and
# API key. The Gateway uses a self-signed certificate for openjev.local, so
# curl connects that name to the LoadBalancer IP and skips verification (-k).
# GATEWAY_CONNECT=127.0.0.1:8443 goes through a port-forward of the Gateway's
# Service instead (same listener, TLS and SNI).
set -euo pipefail
NS=${NS:-decisions}
INSTANCE=${INSTANCE:-openjev}

conn() { kubectl -n "$NS" get secret "$INSTANCE-conn" -o jsonpath="{.data.$1}" | base64 -d; }
URI=$(conn uri)            # https://openjev.local/typesafe
MODEL=$(conn model)        # openjev
KEY=$(conn password)
HOST=$(conn host)
IP=$(kubectl -n everest-system get gateway provider-kserve-ai-gateway -o jsonpath='{.status.addresses[0].value}')
CONNECT=${GATEWAY_CONNECT:-$IP:443}
CURL=(curl -sk --connect-to "$HOST:443:$CONNECT" -H 'Content-Type: application/json')

body() {
  cat <<EOF
{"model": "$1",
 "state": "Customer message: I was charged twice for my order last week and nobody has replied.",
 "questions": {
   "route":   {"type": "choice", "instructions": "Which team should handle this?",
               "criteria": {"billing": null, "shipping": null, "technical": null}},
   "angry":   {"type": "noul",   "instructions": "Is the customer angry?"},
   "urgency": {"type": "score",  "instructions": "How urgent is this?",
               "criteria": ["can wait", "this week", "today", "right now"]}}}
EOF
}

echo "gateway: $URI (via $CONNECT), model: $MODEL"

code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URI/v1/systemone" -d "$(body "$MODEL")")
echo "no API key                -> $code (want 401)"; [ "$code" = 401 ]

code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URI/v1/systemone" -H "Authorization: Bearer $KEY" -d "$(body some-other-model)")
echo "key for another model     -> $code (want 403)"; [ "$code" = 403 ]

out=$("${CURL[@]}" -w '\n%{http_code} %{time_total}' "$URI/v1/systemone" -H "Authorization: Bearer $KEY" -d "$(body "$MODEL")")
code=$(tail -1 <<<"$out" | cut -d' ' -f1)
echo "valid key                 -> $code in $(tail -1 <<<"$out" | cut -d' ' -f2)s (want 200)"; [ "$code" = 200 ]
sed '$d' <<<"$out" | python3 -c '
import json, sys
r = json.load(sys.stdin)
a = r["answers"]
print("  route  :", a["route"]["choice"], a["route"]["probabilities"])
print("  angry  :", a["angry"]["noul"])
print("  urgency:", a["urgency"]["score"], a["urgency"]["probabilities"])
print("  usage  :", r["usage"])
assert set(a) == {"route", "angry", "urgency"} and r["usage"]["input_tokens"] > 0'

echo "OK: the helper accepted the key the Gateway injected (it rejects requests without one)"
