#!/bin/bash
# setup-loadgen.sh: copy the Python tools and query set into the loadgen pod's /work.
set -eu; ns=${NS:-tidb}; cd $(dirname $0)/..
for f in common/probe.py common/verify_probe.py htap/freshness.py htap/power.py htap/ch-queries.json startup/sqlpoll.py; do
  kubectl -n $ns exec -i loadgen -- sh -c "mkdir -p /work && cat > /work/$(basename $f)" < $f
done
