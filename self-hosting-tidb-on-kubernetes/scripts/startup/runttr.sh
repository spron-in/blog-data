#!/bin/bash
# runttr.sh <preset> <name> <id> <label> <presetkey>: one startup run, appended to results/startup/ttr-runs.jsonl.
# Creates the Instance from the preset, records when SQL first works and when it is Ready, collects
# per-pod timings (ttr.py), then deletes it and waits until its volumes are gone.
set -u; cd $(dirname $0); preset=$1 name=$2 id=$3 label=$4 pk=$5; ns=${NS:-tidb}; out=../../results/startup; mkdir -p $out
python3 ../common/gen.py $preset $name | kubectl apply -f - >/dev/null
# time zero is the server's creationTimestamp: a slow API call must not count
t0=$(kubectl -n $ns get instances.core.openeverest.io $name -o jsonpath='{.metadata.creationTimestamp}' | python3 -c 'import sys,datetime;print(datetime.datetime.fromisoformat(sys.stdin.read().strip().replace("Z","+00:00")).timestamp())')
for i in $(seq 1 120); do kubectl -n $ns get secret $name-tidb-root $name-tls-ca >/dev/null 2>&1 && break; sleep 0.5; done
kubectl -n $ns get secret $name-tidb-root -o jsonpath='{.data.password}' | base64 -d | kubectl -n $ns exec -i loadgen -- sh -c 'cat > /work/poll-pw'
kubectl -n $ns get secret $name-tls-ca -o jsonpath='{.data.ca\.crt}' | base64 -d | kubectl -n $ns exec -i loadgen -- sh -c 'cat > /work/poll-ca.crt'
kubectl -n $ns exec loadgen -- sh -c "rm -f /work/sql-$id; nohup python3 /work/sqlpoll.py $name-tidb.$ns /work/sql-$id >/dev/null 2>&1 &"
while true; do
  p=$(kubectl -n $ns get instances.core.openeverest.io $name -o jsonpath='{.status.phase}' 2>/dev/null)
  [ "$p" = Ready ] && break; sleep 1
done
# ready: when the Instance's PodsReady condition turned True (server time)
ready=$(kubectl -n $ns get instances.core.openeverest.io $name -o json | python3 -c "
import json,sys,datetime
c=[x for x in json.load(sys.stdin)['status']['conditions'] if x['type']=='PodsReady' and x['status']=='True'][0]
print(f\"{datetime.datetime.fromisoformat(c['lastTransitionTime'].replace('Z','+00:00')).timestamp()-$t0:.1f}\")")
for i in $(seq 1 120); do sqlabs=$(kubectl -n $ns exec loadgen -- cat /work/sql-$id 2>/dev/null) && [ -n "$sqlabs" ] && break; sleep 2; done
sql=$(python3 -c "print(f'{$sqlabs-$t0:.1f}')")
NS=$ns python3 ttr.py $name $t0 $ready $sql $id "$label" $pk | tee -a $out/ttr-runs.jsonl | python3 -c "
import json,sys;r=json.load(sys.stdin);print(r['id'],'ready',r['ready'],'sql',r['sql'],'restarts',sum(p['x'] for p in r['pods']),'pull-max',max((p['p'] or 0)-(p['a'] or p['s'] or 0) for p in r['pods']))"
kubectl -n $ns delete instances.core.openeverest.io $name --wait=false >/dev/null
while kubectl -n $ns get instances.core.openeverest.io $name >/dev/null 2>&1; do sleep 3; done
while [ "$(kubectl get pv --no-headers 2>/dev/null | grep -c " $ns/$name-\| $ns/data-$name-")" != 0 ]; do sleep 5; done
