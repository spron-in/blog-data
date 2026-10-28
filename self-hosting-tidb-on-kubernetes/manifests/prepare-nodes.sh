#!/bin/bash
# prepare-nodes.sh <node>...: reserve nodes for the database pods. common/gen.py adds the matching
# node selector and toleration to every component.
for n in "$@"; do
  kubectl taint node "$n" dedicated=tidb:NoSchedule --overwrite
  kubectl label node "$n" tidb-bench=db --overwrite
done
