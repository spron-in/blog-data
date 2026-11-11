#!/bin/bash
# usage: api.sh METHOD PATH [JSON]   (plugin API through localhost:18081)
P=$(kubectl get secret -n everest-system everest-accounts -o jsonpath='{.data.users\.yaml}' | base64 -d | python3 -c 'import yaml,sys; print(yaml.safe_load(sys.stdin)["admin"]["passwordHash"])')
T=$(curl -s -m 10 -X POST localhost:18080/v1/auth/token -H 'content-type: application/json' \
  -d "{\"grant_type\":\"password\",\"username\":\"admin\",\"password\":\"$P\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')
[ -z "$T" ] && { echo "login failed" >&2; exit 1; }
if [ -n "$3" ]; then
  curl -s -m ${API_TIMEOUT:-30} -X "$1" "localhost:18081$2" -H "Authorization: Bearer $T" -H 'content-type: application/json' -d "$3"
else
  curl -s -m ${API_TIMEOUT:-30} -X "$1" "localhost:18081$2" -H "Authorization: Bearer $T"
fi
echo
