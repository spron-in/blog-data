# Test 8: Fragmentation and `activedefrag`

## Config
- Instance: `test8-fragmentation`, 2Gi memory limit, no `maxmemory` set, no persistence.
- Real traffic throughout (no `DEBUG POPULATE`): `valkey-benchmark -t set -d 2000 -r 300000` (2KB values, default `key:<N>` naming).

## Method
1. Load ~190k keys of 2KB values with `valkey-benchmark`.
2. Delete a *scattered* subset — every even-numbered key suffix — via a server-side Lua `EVAL` using `SCAN`+`DEL`, not a contiguous range. Scattered deletion is what actually leaves holes in jemalloc's slabs; deleting a contiguous block tends to free whole slabs back to the OS on its own.
3. Watch `used_memory` / `used_memory_rss` / `mem_fragmentation_ratio` before and after `CONFIG SET activedefrag yes`.

## Results

**Baseline (fully loaded):** `used_memory` ≈ 403MB, RSS ≈ 431MB, ratio ≈ 1.07 — normal.

**After deleting ~half the keys (scattered):**
```
used_memory: ~205MB   (correctly reflects "live" data)
used_memory_rss: ~396MB   (barely moved)
mem_fragmentation_ratio: 1.93
```
Valkey freed the key/value objects internally, but jemalloc kept holding the underlying pages — classic external fragmentation. No command rejected writes and nothing looked wrong from `used_memory` alone; only the ratio revealed the problem.

**After `CONFIG SET activedefrag yes` (default thresholds):**
```
used_memory_rss: 396MB -> 335MB (ratio 1.93 -> 1.63) within ~10-20s
... then plateaued for 2+ minutes, active_defrag_hits stayed at 0
```
This plateau was initially puzzling: `activedefrag yes` was accepted, no errors in the logs, and the ratio was still far above 1.0. `MEMORY STATS` explained it: `allocator-fragmentation.bytes` had settled at ~102MB — just under the default `active-defrag-ignore-bytes` (104,857,600 bytes = 100MB). Active defrag treats anything below that floor as "not worth the CPU," so it quietly stopped.

**After lowering `active-defrag-ignore-bytes` to 1MB and raising the per-cycle budget (`active-defrag-cycle-min 5`, `active-defrag-cycle-max 75`):**
```
used_memory_rss: 335MB -> 235MB -> 233MB (ratio 1.63 -> 1.15 -> 1.14) within ~10s
active_defrag_hits: 0 -> 88,451
```
With the ignore-bytes floor out of the way, defrag immediately found and relocated tens of thousands of objects and brought the ratio down to near 1.0. No OOM, no restart, no client errors at any point in this test.

## Caveat
The default `active-defrag-ignore-bytes` (100MB) is sized for much bigger instances; on a 2Gi pod that's already a large fraction of the process's own footprint, so the default config can look like "defrag isn't working" on exactly the small/medium instance sizes this lab is testing. This is a tuning footgun worth calling out, not a bug.

## Takeaway for the post
`activedefrag` works, but its defaults assume a bigger server. On small instances the stock `active-defrag-ignore-bytes` can make active defrag silently stop short, leaving the fragmentation ratio elevated indefinitely. Providers packaging Valkey for smaller pods should consider scaling that threshold down, or at least surfacing `mem_fragmentation_ratio` and `active_defrag_hits` so this doesn't look like "defrag is broken."
