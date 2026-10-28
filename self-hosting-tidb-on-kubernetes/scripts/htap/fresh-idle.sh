#!/bin/bash
# Freshness on an idle cluster: write to TiKV, read through TiFlash right away, 1000 times.
python3 /work/freshness.py idle 1000
