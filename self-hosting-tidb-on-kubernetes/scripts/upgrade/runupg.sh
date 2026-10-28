#!/bin/bash
# runupg.sh <instance>: 22 min of TPC-C (32 clients, 50 warehouses) plus the write probe, upgrading the
# Instance 7.5.5 -> 8.5.2 at t=300s. Results go to results/upgrade/<instance>/.
set -u; cd $(dirname $0); n=$1; ns=${NS:-tidb}; out=../../results/upgrade/$n; mkdir -p $out
t0=$(kubectl -n $ns exec loadgen -- bash -c ". /work/$n.env; cd /work; rm -f probe-$n.*; \
  nohup go-tpc tpcc run -T 32 --warehouses 50 -H \$H -P \$PO -p \$PW \$SSL -D tpcc --interval 5s --time 22m --ignore-error > /work/$n-run.log 2>&1 & \
  nohup python3 /work/probe.py $n 1320 > /work/probe-$n.out 2>&1 & date +%s.%N")
echo "t0=$t0" | tee $out/meta
sleep $(python3 -c "import time;print(max(0,$t0+300-time.time()))")
a=$(python3 -c 'import time;print(time.time())'); kubectl -n $ns patch instances.core.openeverest.io $n --type merge -p '{"spec":{"version":"8.5.2"}}' >/dev/null; b=$(python3 -c 'import time;print(time.time())')
echo "patch=$(python3 -c "print(($a+$b)/2-$t0)") (call took $(python3 -c "print($b-$a)")s)" | tee -a $out/meta
sleep 20
until [ "$(kubectl -n $ns get instances.core.openeverest.io $n -o jsonpath='{.status.phase}' 2>/dev/null)" = Ready ]; do sleep 3; done
kubectl -n $ns get instances.core.openeverest.io $n -o json > $out/instance.json
kubectl -n $ns get pods -l core.openeverest.io/instance=$n -o json > $out/pods.json
kubectl -n $ns get events -o json > $out/events.json
echo "ready; waiting for the run to finish" | tee -a $out/meta
while kubectl -n $ns exec loadgen -- test ! -s /work/probe-$n.out 2>/dev/null; do sleep 15; done
sleep 30
for f in $n-run.log probe-$n.jsonl probe-$n.out; do kubectl -n $ns exec loadgen -- cat /work/$f > $out/$f; done
kubectl -n $ns get events -o json > $out/events-end.json
echo done | tee -a $out/meta
