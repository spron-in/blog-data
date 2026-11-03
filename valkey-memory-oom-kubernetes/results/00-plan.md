# Valkey memory/OOMKilled test plan (LKE, OpenEverest Instances)

Namespace: valkey-mem-lab

## Scenarios
1. default-oom: no maxmemory, no storage (emptyDir), 1Gi limit -> fill until OOMKilled, observe restart/reload.
2. maxmemory-at-limit: maxmemory == pod limit, no storage.
3. maxmemory-headroom: maxmemory ~85-90% of limit, compare stability.
4. eviction-noeviction vs allkeys-lru: push past maxmemory, record OOM command error / eviction behavior.
5. persistence-cow: storage enabled (PVC), default save rules, measure RSS spike during BGSAVE fork.
6. aof: appendonly yes, measure extra RSS / page cache charge.
7. replica-full-sync: replication topology (1 primary + 1 replica), fill primary near limit, force full resync, watch replica buffer + primary OOM behavior.
8. fragmentation: load small keys, delete half, observe RSS not dropping; test activedefrag.

Each test logs to /tmp/valkey-mem-lab/results/<test-id>.md with: Instance YAML used, timeline of `kubectl get pod -w`/`describe pod` lastState, valkey INFO memory/stats snapshots, and conclusion. Progress appended as it runs so nothing is lost mid-run.

## Final status (all 9 scenarios complete)

| # | Scenario | File | Result |
|---|----------|------|--------|
| 1 | Default config, no maxmemory, no persistence | test1-default-oom.md | OOMKilled ~1033MB/1Gi limit |
| 2 | maxmemory == limit | test2-3-4-maxmemory-eviction.md | OOMKilled before eviction kicked in |
| 3 | maxmemory with headroom, noeviction | test2-3-4-maxmemory-eviction.md | Correctly rejects writes, no restart |
| 4 | allkeys-lru | test2-3-4-maxmemory-eviction.md | Evicts correctly, no restart |
| 5 | BGSAVE copy-on-write | test5-6-bgsave-cow.md | Instant OOM anomaly (see caveats) |
| 6 | AOF overhead | test5-6-bgsave-cow.md | ~6% RSS overhead, no OOM |
| 7 | Replica full sync after primary OOM | test7-replica-full-sync.md | Confirmed total data loss, status stayed Ready/ClusterHealthy |
| 8 | Fragmentation / activedefrag | test8-fragmentation.md | activedefrag works but default ignore-bytes threshold stalls it on small instances |
| 9 | QoS vs node memory pressure | test9-qos-node-pressure.md | Burstable Valkey evicted/OOMKilled before a bigger Guaranteed neighbor |

Namespace `valkey-mem-lab` and all Instances/PVCs deleted after each writeup was saved to disk.
Two Linode Block Storage volumes backing test5/test6 PVCs used `Retain` reclaim policy; the
Kubernetes PV objects were deleted, but the underlying cloud volumes are NOT auto-deleted by
that policy and were not independently reachable from this environment (no linode-cli). These
should be checked and removed manually in the Linode/Akamai cloud console to avoid lingering cost.
