#!/bin/bash
# The write probe next to ops-tpcc.sh (one insert every 100 ms, then checks every acknowledged write).
python3 /work/probe.py ops 3600
