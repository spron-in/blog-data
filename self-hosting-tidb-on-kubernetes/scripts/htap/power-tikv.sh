#!/bin/bash
# Each of the 22 CH queries alone on TiKV, 2 runs (power.py writes /work/power-tikv.json).
python3 /work/power.py tikv,tidb tikv 2
