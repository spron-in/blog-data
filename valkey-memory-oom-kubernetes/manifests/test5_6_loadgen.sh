#!/bin/bash
# usage: test5_6_loadgen.sh <namespace> <pod> <password> <outfile> <max_rounds> <target_mb>
NS=$1; POD=$2; PASS=$3; OUT=$4; MAXR=${5:-40}; TARGET_MB=${6:-1500}
> "$OUT"
for i in $(seq 1 $MAXR); do
  kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning DEBUG POPULATE 5000 "k${i}_" 10000 >/dev/null 2>&1
  MEM=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>/dev/null | tr -d '\r')
  USED=$(echo "$MEM" | grep -m1 '^used_memory:' | cut -d: -f2)
  USED_MB=$((USED/1024/1024))
  RSS=$(echo "$MEM" | grep -m1 '^used_memory_rss:')
  DBSIZE=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning DBSIZE 2>/dev/null)
  RESTARTS=$(kubectl get pod -n $NS $POD -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  echo "round=$i dbsize=$DBSIZE used_memory_mb=$USED_MB $RSS restarts=$RESTARTS" | tee -a "$OUT"
  if [ "$RESTARTS" != "0" ]; then echo "!!! RESTART at round $i" | tee -a "$OUT"; exit 0; fi
  if [ "$USED_MB" -ge "$TARGET_MB" ]; then echo "=== target reached, triggering BGSAVE ===" | tee -a "$OUT"; break; fi
done

echo "--- pre-bgsave memory ---" | tee -a "$OUT"
kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>&1 | grep -E "used_memory:|used_memory_rss:|mem_fragmentation_ratio" | tee -a "$OUT"
kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning BGSAVE 2>&1 | tee -a "$OUT"
for j in 1 2 3 4 5 6 7 8; do
  sleep 1
  INPROG=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO persistence 2>/dev/null | grep -m1 'rdb_bgsave_in_progress:' | tr -d '\r')
  RSS=$(kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>/dev/null | grep -m1 '^used_memory_rss:' | tr -d '\r')
  RESTARTS=$(kubectl get pod -n $NS $POD -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  echo "bgsave_tick=$j $INPROG $RSS restarts=$RESTARTS" | tee -a "$OUT"
  if [ "$RESTARTS" != "0" ]; then echo "!!! RESTART during bgsave at tick $j" | tee -a "$OUT"; break; fi
done
echo "--- post-bgsave persistence info ---" | tee -a "$OUT"
kubectl exec -n $NS $POD -- valkey-cli -a $PASS --no-auth-warning INFO persistence 2>&1 | grep -E "rdb_|aof_" | tee -a "$OUT"
echo "DONE" | tee -a "$OUT"
