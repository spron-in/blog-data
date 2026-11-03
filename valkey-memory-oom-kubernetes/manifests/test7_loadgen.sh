#!/bin/bash
# usage: test7_loadgen.sh <namespace> <primary_pod> <replica_pod> <password> <outfile> <max_rounds> <target_mb>
NS=$1; PRIMARY=$2; REPLICA=$3; PASS=$4; OUT=$5; MAXR=${6:-20}; TARGET_MB=${7:-700}
> "$OUT"
for i in $(seq 1 $MAXR); do
  kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning DEBUG POPULATE 5000 "k${i}_" 10000 >/dev/null 2>&1
  USED=$(kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>/dev/null | grep -m1 '^used_memory:' | tr -d '\r' | cut -d: -f2)
  USED_MB=$((USED/1024/1024))
  DBSIZE=$(kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning DBSIZE 2>/dev/null)
  RESTARTS_P=$(kubectl get pod -n $NS $PRIMARY -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  echo "round=$i dbsize=$DBSIZE used_memory_mb=$USED_MB primary_restarts=$RESTARTS_P" | tee -a "$OUT"
  if [ "$RESTARTS_P" != "0" ]; then echo "!!! PRIMARY RESTART at round $i" | tee -a "$OUT"; break; fi
  if [ "$USED_MB" -ge "$TARGET_MB" ]; then echo "=== target reached ===" | tee -a "$OUT"; break; fi
done

echo "--- confirm replica in sync before forcing resync ---" | tee -a "$OUT"
kubectl exec -n $NS $REPLICA -- valkey-cli -a $PASS --no-auth-warning INFO replication 2>&1 | grep -E "master_link_status|master_sync_in_progress" | tee -a "$OUT"
kubectl exec -n $NS $REPLICA -- valkey-cli -a $PASS --no-auth-warning DBSIZE | tee -a "$OUT"

echo "--- forcing full resync: killing replica link on primary ---" | tee -a "$OUT"
kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning CLIENT KILL TYPE replica 2>&1 | tee -a "$OUT"

for j in $(seq 1 20); do
  sleep 2
  MEM_P=$(kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning INFO memory 2>/dev/null | grep -E '^used_memory:|^used_memory_rss:|^mem_replication_backlog' | tr '\r\n' '  ')
  SYNCFULL=$(kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning INFO stats 2>/dev/null | grep -m1 'sync_full:' | tr -d '\r')
  R_P=$(kubectl get pod -n $NS $PRIMARY -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  R_R=$(kubectl get pod -n $NS $REPLICA -o jsonpath='{.status.containerStatuses[?(@.name=="server")].restartCount}' 2>/dev/null)
  REPL_LINK=$(kubectl exec -n $NS $REPLICA -- valkey-cli -a $PASS --no-auth-warning INFO replication 2>/dev/null | grep -m1 'master_link_status:' | tr -d '\r')
  echo "tick=$j $MEM_P $SYNCFULL primary_restarts=$R_P replica_restarts=$R_R $REPL_LINK" | tee -a "$OUT"
  if [ "$R_P" != "0" ] || [ "$R_R" != "0" ]; then
    echo "!!! RESTART DETECTED (primary=$R_P replica=$R_R) at tick $j" | tee -a "$OUT"
  fi
done

echo "--- final dbsize check (primary vs replica) ---" | tee -a "$OUT"
kubectl exec -n $NS $PRIMARY -- valkey-cli -a $PASS --no-auth-warning DBSIZE 2>&1 | tee -a "$OUT"
kubectl exec -n $NS $REPLICA -- valkey-cli -a $PASS --no-auth-warning DBSIZE 2>&1 | tee -a "$OUT"
echo "DONE" | tee -a "$OUT"
