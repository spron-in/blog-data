#!/usr/bin/env bash
# Run a command with the AI Gateway's Service port-forwarded to 127.0.0.1:8443
# and GATEWAY_CONNECT set, for clusters whose LoadBalancer is not reachable.
#   ./scripts/via-gateway-portforward.sh ./scripts/gateway_e2e.sh
set -euo pipefail
cd "$(dirname "$0")/.."
SVC=$(kubectl -n everest-system get svc -l gateway.envoyproxy.io/owning-gateway-name=provider-kserve-ai-gateway -o jsonpath='{.items[0].metadata.name}')
kubectl -n everest-system port-forward "svc/$SVC" 8443:443 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT
until nc -z 127.0.0.1 8443 2>/dev/null; do sleep 1; done
GATEWAY_CONNECT=127.0.0.1:8443 "$@"
