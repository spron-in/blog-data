#!/bin/bash
# inpod.sh <instance> <script> [args...]: run a test script inside the loadgen pod, detached, after
# sourcing /work/<instance>.env (written by env.sh). Prints the log path; the log ends with __EXIT=<code>.
#   common/inpod.sh htap htap/ch-tiflash.sh
#   kubectl -n tidb exec loadgen -- tail -f /work/ch-tiflash-htap.log
set -eu; ns=${NS:-tidb}; n=$1; s=$2; shift 2; b=$(basename $s .sh); args="$*"
kubectl -n $ns exec -i loadgen -- sh -c "cat > /work/$b.sh" < $s
kubectl -n $ns exec loadgen -- bash -c "cd /work; nohup bash -c '. /work/$n.env; bash /work/$b.sh $args; echo __EXIT=\$?' > /work/$b-$n.log 2>&1 &"
echo /work/$b-$n.log
