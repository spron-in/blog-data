#!/bin/bash
# run.sh <step> <run-name> [args]   steps: start-bg | create | worker-url | status | cutover | stop-bg | verify
set -e
D=$(dirname "$0"); RUN=$2
SRC=redis-0.redis.redis-legacy.svc.cluster.local:6379
DST=valkey-shop-valkey.valkey-shop.svc.cluster.local:6379
DSTF="-dst-addr $DST -dst-user default -dst-tls -dst-cert /dst/tls.crt -dst-key /dst/tls.key"
X="kubectl exec -n vk-bench tools --"
ts() { date -u +%FT%TZ; }
case $1 in
start-bg)  # writer + poller
  DATASET=${3:-a}
  $X sh -c "cd /work && mkdir -p $RUN && nohup ./vktool writer -addr $SRC -dataset $DATASET -rate 2000 > $RUN/writer.log 2>&1 &"
  $X sh -c "cd /work && nohup ./vktool poll -src-addr $SRC $DSTF -worker /work/$RUN/worker-url -out $RUN/metrics.csv -interval 5s > $RUN/poll.log 2>&1 &"
  echo "$(ts) background started" | tee -a $D/$RUN.events ;;
create)
  PW=$(kubectl get secret -n redis-legacy redis-auth -o jsonpath='{.data.password}' | base64 -d)
  FLUSH=${3:-false}
  $D/api.sh POST /api/migrations "{\"name\":\"$RUN\",\"engine\":\"redis-shake\",\"source\":{\"type\":\"external\",\"uri\":\"redis://default:$PW@$SRC\"},\"target\":{\"type\":\"instance\",\"k8sCluster\":\"main\",\"namespace\":\"valkey-shop\",\"name\":\"shop-valkey\"},\"options\":{\"flushTarget\":$FLUSH,\"excludeKeyPrefixes\":[]}}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id"), d.get("phase"), d.get("error",""))'
  echo "$(ts) migration created" | tee -a $D/$RUN.events ;;
worker-url)
  IP=$(kubectl get pods -n plugin-migrations-valkey -o wide --no-headers | grep -v "^plugin-migrations-valkey-" | awk '{print $6}' | head -1)
  $X sh -c "printf http://$IP:2243 > /work/$RUN/worker-url"; echo "worker $IP" ;;
status)
  $D/api.sh GET /api/migrations | python3 -c 'import json,sys; [print(m["id"], m["phase"], json.dumps(m["progress"]), m.get("message",""), m.get("error",""), m.get("allowedActions")) for m in json.load(sys.stdin)["migrations"]]' ;;
cutover)
  ID=$($D/api.sh GET /api/migrations | python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['migrations'] if m['name']=='$RUN'][0])")
  echo "$(ts) cutover requested" | tee -a $D/$RUN.events
  $D/api.sh POST /api/migrations/$ID/cutover | head -c 300; echo ;;
stop-writer)
  PID=$($X sh -c "ps | grep 'vktool writer' | grep -v grep | awk '{print \$1}'")
  $X kill $PID; sleep 2; echo "$(ts) writer stopped" | tee -a $D/$RUN.events; $X tail -1 /work/$RUN/writer.log ;;
stop-poll)
  PID=$($X sh -c "ps | grep 'vktool poll' | grep -v grep | awk '{print \$1}'")
  $X kill $PID; echo "$(ts) poller stopped" | tee -a $D/$RUN.events ;;
verify)
  echo "$(ts) verify started" | tee -a $D/$RUN.events
  $X sh -c "cd /work && nohup ./vktool verify -src-addr $SRC $DSTF -workers 64 -out $RUN/verify.json > $RUN/verify.log 2>&1 &" ;;
esac
