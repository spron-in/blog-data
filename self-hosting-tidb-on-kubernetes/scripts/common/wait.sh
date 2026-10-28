#!/bin/bash
# wait.sh <instance> <phase> <timeout-s> [start-epoch]: print phase/message changes until the Instance reaches <phase>
n=$1; ns=${NS:-tidb}; want=$2; to=$3; start=${4:-$(date -u +%s)}; last=""
while true; do
  now=$(date -u +%s); el=$((now-start))
  p=$(kubectl -n $ns get instances.core.openeverest.io $n -o jsonpath='{.status.phase}' 2>/dev/null)
  m=$(kubectl -n $ns get instances.core.openeverest.io $n -o jsonpath='{.status.message}' 2>/dev/null | cut -c1-160)
  [ "$p|$m" != "$last" ] && echo "[$el s] $p :: $m" && last="$p|$m"
  [ "$p" = "$want" ] && echo "REACHED $want after ${el}s" && exit 0
  [ $el -gt $to ] && echo "TIMEOUT after ${el}s (phase=$p)" && exit 1
  sleep 3
done
