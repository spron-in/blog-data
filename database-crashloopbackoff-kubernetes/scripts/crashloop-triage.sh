#!/usr/bin/env bash
# Usage: crashloop-triage.sh <pod> [namespace]
# Prints the four things you need to diagnose a CrashLoopBackOff database pod:
# current state, the last termination (reason + exit code), recent events,
# and the logs of the *previous* (crashed) container.
set -uo pipefail

POD="${1:?usage: $0 <pod> [namespace]}"
NS="${2:-default}"
K="kubectl -n $NS"

echo "### status"
$K get pod "$POD" -o wide

echo
echo "### per-container state / lastState"
$K get pod "$POD" -o jsonpath='{range .status.initContainerStatuses[*]}init/{.name}{"\trestarts="}{.restartCount}{"\tstate="}{.state}{"\tlast="}{.lastState.terminated.reason}{"/"}{.lastState.terminated.exitCode}{"\n"}{end}{range .status.containerStatuses[*]}{.name}{"\trestarts="}{.restartCount}{"\tstate="}{.state}{"\tlast="}{.lastState.terminated.reason}{"/"}{.lastState.terminated.exitCode}{"\n"}{end}'

echo
echo "### events"
$K get events --field-selector "involvedObject.name=$POD" --sort-by=.lastTimestamp \
  -o custom-columns='LAST:.lastTimestamp,TYPE:.type,REASON:.reason,MESSAGE:.message' | tail -15

echo
echo "### logs --previous (last 25 lines)"
$K logs "$POD" --previous --tail=25 2>&1 || true
