#!/bin/bash
# Each of the 22 CH queries alone on TiFlash, 2 runs (power.py writes /work/power-tiflash.json).
python3 /work/power.py tiflash,tidb tiflash 2
