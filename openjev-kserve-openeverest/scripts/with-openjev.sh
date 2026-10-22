#!/usr/bin/env bash
# Run a command with OpenJev reachable on 127.0.0.1:3000: port-forwards the
# Instance's predictor Service and exports OPENJEV_URL / OPENJEV_TOKEN.
#   ./scripts/with-openjev.sh python3 scripts/incident_triage.py --policy v2
set -euo pipefail
cd "$(dirname "$0")/.."
kubectl -n decisions port-forward svc/openjev-predictor 3000:80 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT
until curl -s -o /dev/null http://127.0.0.1:3000/; do sleep 1; done
export OPENJEV_URL=http://127.0.0.1:3000 PYTHONPATH=scripts
export OPENJEV_TOKEN=$(kubectl -n decisions get secret openjev-shim -o jsonpath='{.data.apiKey}' | base64 -d)
"$@"
