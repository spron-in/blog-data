#!/bin/bash
# Freshness under load (start tpcc-only.sh or ch-tiflash.sh alongside).
python3 /work/freshness.py load 1000
