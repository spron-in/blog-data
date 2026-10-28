#!/bin/bash
# runtls.sh <instance>:<run> ...: 10-minute TPC-C runs (64 clients, 50 warehouses), one after another.
# Each run starts detached in the loadgen pod and is polled, so a dropped kubectl stream can't make runs overlap.
# We ran: runtls.sh tls-off:1 tls-on:1 tls-off:2 tls-on:2 tls-off:3 tls-on:3
set -u; cd $(dirname $0); ns=${NS:-tidb}; out=../../results/tls; mkdir -p $out
for job in "$@"; do n=${job%%:*}; i=${job##*:}; f=/work/$n-run$i.log
  echo "$(date -u +%H:%M:%S) start $n run$i" | tee -a $out/meta
  until kubectl -n $ns exec loadgen -- bash -c ". /work/$n.env; rm -f $f; nohup bash -c \"go-tpc tpcc run -T 64 --warehouses 50 -H \$H -P \$PO -p \$PW \$SSL -D tpcc --interval 10s --time 10m > $f 2>&1; echo __EXIT=\\\$? >> $f\" >/dev/null 2>&1 &"; do sleep 5; done
  sleep 590
  until kubectl -n $ns exec loadgen -- grep -q __EXIT $f 2>/dev/null; do sleep 10; done
  until kubectl -n $ns exec loadgen -- cat $f > $out/$n-run$i.log 2>/dev/null; do sleep 5; done
  echo "$(date -u +%H:%M:%S) end $n run$i: $(grep -E '^tpmC|__EXIT' $out/$n-run$i.log | tr '\n' ' ')" | tee -a $out/meta
  sleep 60
done
echo done | tee -a $out/meta
