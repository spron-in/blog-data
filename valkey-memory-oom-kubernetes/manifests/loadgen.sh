#!/bin/bash
# usage: loadgen.sh <namespace> <pod> <password> <outfile> <max_rounds>
NS=$1; POD=$2; PASS=$3; OUT=$4; MAXR=${5:-60}
> "$OUT"
for i in $(seq 1 $MAXR); do
  kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning DEBUG POPULATE 5000 "k${i}_" 10000 >/dev/null 2>&1
  MEM=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>/dev/null | tr -d '\r')
  USED=$(echo "$MEM" | grep -m1 '^used_memory:')
  RSS=$(echo "$MEM" | grep -m1 '^used_memory_rss:')
  DBSIZE=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning DBSIZE 2>/dev/null)
  EVICTED=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO stats 2>/dev/null | grep -m1 'evicted_keys:' | tr -d '\r')
  REJECTED=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning SET "probe_$i" "x" 2>&1 | tr -d '\r')
  RESTARTS=$(kubectl get pod -n $NS $POD -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  LINE="round=$i dbsize=$DBSIZE $USED $RSS $EVICTED write_probe=[$REJECTED] restarts=$RESTARTS"
  echo "$LINE" | tee -a "$OUT"
  if [ "$RESTARTS" != "0" ]; then
    echo "!!! RESTART DETECTED at round $i" | tee -a "$OUT"
    break
  fi
  # stop once memory growth has clearly plateaued near maxmemory for 5 rounds, caller can judge from stable used_memory
done
echo "DONE" >> "$OUT"
