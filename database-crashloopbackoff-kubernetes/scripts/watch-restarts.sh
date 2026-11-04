#!/usr/bin/env bash
# Usage: watch-restarts.sh <pod> <namespace> <seconds> > log
# Polls a pod every 2s and prints a line whenever restartCount or the
# displayed status changes. Used to measure the CrashLoopBackOff delays.
set -uo pipefail
POD="$1"; NS="$2"; DURATION="${3:-600}"
END=$(( $(date +%s) + DURATION ))
prev=""
while [ "$(date +%s)" -lt "$END" ]; do
  line=$(kubectl -n "$NS" get pod "$POD" --no-headers 2>/dev/null | awk '{print $3, $4}')
  if [ "$line" != "$prev" ]; then
    echo "$(date -u +%H:%M:%S) $line"
    prev="$line"
  fi
  sleep 2
done
