# Test 5 & 6: BGSAVE / AOF copy-on-write vs. container memory limit

## Config (both)
- Topology: `replication` single node, 5Gi PVC attached
- Resources: 2Gi limit = request (Guaranteed QoS)
- `maxmemory 1700mb`, `maxmemory-policy noeviction`, default `save` rules on
- Test 6 additionally sets `appendonly yes`
- Manifests: `test5-persistence-cow.yaml`, `test6-aof.yaml`

## Method
Loaded via `DEBUG POPULATE` up to ~155,000 keys (`used_memory` ≈ 1599MB, `used_memory_rss` ≈
1629MB — about 519MB of headroom under the 2Gi/2147MB limit, and still 184MB under the 1700MB
`maxmemory` ceiling). Then issued an explicit `BGSAVE` and sampled `INFO` every second.

## Result: instant OOM on the very first fork, in both tests, on different nodes
```
--- pre-bgsave memory ---
used_memory:1599132736        (≈1525 MB)
used_memory_rss:1628868608    (≈1553 MB)
mem_fragmentation_ratio:1.02
Background saving started
bgsave_tick=1 rdb_bgsave_in_progress:0 used_memory_rss:16384000 restarts=1
!!! RESTART during bgsave at tick 1
```
Both pods were killed and restarted (`restarts=1`) within the first ~1 second after `BGSAVE` was
issued — there was no gradual copy-on-write climb to observe, the container was gone by the first
sample. `rdb_saves:0` and `rdb_last_cow_size:0` after the restart confirm the save never completed.

For test 6, `aof_current_size:89` the whole time is a tell: **`DEBUG POPULATE` does not go through
normal command propagation**, so nothing was ever written to the AOF. This run measured the exact
same BGSAVE-fork phenomenon as test 5, not AOF overhead — see the follow-up measurement below.

## This is a genuinely surprising result
At the moment `BGSAVE` was issued there was ~519MB of headroom to the container limit and ~184MB of
headroom to `maxmemory`. A `fork()`-based snapshot should only grow RSS gradually, as copy-on-write
pages accumulate from concurrent writes — and there were **no writes happening** while the fork ran.
Instead the container was OOMKilled essentially instantly. The likely explanation is page-table and
allocator bookkeeping overhead for a process with ~1.5GB of live data spread across small (10-20
byte) `DEBUG POPULATE` keys/values — forking duplicates page tables, and with that many small
objects the page table itself can be large — rather than classic copy-on-write of payload data. I
don't have a confirmed root cause; this is reported as a measured anomaly, not a fully-explained one.

## Clean follow-up: real AOF overhead, isolated from the BGSAVE-fork issue
To measure genuine AOF overhead I re-used the test 6 pod after its restart, ran `FLUSHALL`, and
loaded it with real `valkey-benchmark -t set` traffic (so writes actually hit the AOF) instead of
`DEBUG POPULATE`:
```
dbsize: 50567
used_memory:       525,508,776   (≈501 MB)
used_memory_rss:   557,436,928   (≈532 MB)   →  +31MB RSS over used_memory (≈6%)
aof_current_size:  740,315,432   (≈706 MB)   →  larger than used_memory (full RESP command log,
                                                 not just final key/value sizes)
```
With real traffic, no OOM kill — 532MB RSS stayed comfortably under the 2Gi limit. The AOF file
being larger than `used_memory` is expected (it's an append-only command log, not a compact
snapshot), and the RSS/`used_memory` overhead here (~6%) is modest and unrelated to the fork
anomaly above.

## Takeaway for the post
- Don't trust "headroom under `maxmemory`" alone as a safety margin for `BGSAVE`/snapshotting —
  measured fork overhead here was large enough to erase hundreds of MB of apparent headroom
  instantly, for reasons not fully explained by classic copy-on-write.
- Validate persistence operations (`BGSAVE`, `BGREWRITEAOF`) under realistic memory pressure, not
  just "does normal traffic fit under the limit."
- `DEBUG POPULATE` is not a safe stand-in for AOF-overhead testing — it bypasses command
  propagation entirely.
