# Test 1: default config, no maxmemory, no persistence (emptyDir), 1Gi limit

Instance: /tmp/valkey-mem-lab/test1-default-oom.yaml
Topology: replication, replicas: 0 (standalone primary)
Resources: 500m CPU / 1Gi memory, requests == limits (Guaranteed QoS)
No `storage` set -> /data is an emptyDir.
`enable-debug-command: local` set so DEBUG POPULATE could drive memory fast.

## Method
Looped `DEBUG POPULATE 5000 "k<i>_" 10000` (5000 keys of ~10KB value each round),
checking `INFO memory` (used_memory, used_memory_rss), DBSIZE and container
restart count after each round.

## Timeline (key rounds)
- round 1:  dbsize=6000    used_memory=55.4MB   rss=69.0MB
- round 10: dbsize=51000   used_memory=519.4MB  rss=537.7MB
- round 19: dbsize=96000   used_memory=982.1MB  rss=1005.1MB
- round 20: dbsize=101000  used_memory=1033.5MB rss=1057.1MB   (limit is 1Gi = 1073.7MB)
- round 21: container OOMKilled. New container up within ~1s. dbsize back to 0.

## Evidence
- `status.containerStatuses[].lastState.terminated`:
  `{"exitCode":137,"reason":"OOMKilled","startedAt":"...18:03:43Z","finishedAt":"...18:09:36Z"}`
- Pod events show only `Killing` / `Started` / `Created` — **no Kubernetes Event
  literally says "OOMKilled"**; that only shows up in `lastState`, confirming the
  well-known gap (`kubectl get events` won't surface it by name).
- QoS class: Guaranteed (requests == limits).
- After restart: `/data` still has `nodes.conf` (201 bytes) — the emptyDir
  **survived the in-place container restart**, so the node restarted with the
  same node ID. `rdb_saves:0`, `rdb_changes_since_last_save:0` — no RDB file
  was ever written, so DBSIZE came back as 0, not stale data.
  - Caveat/finding: the default `save 3600 1 300 100 60 10000` rule never
    fired despite >100k writes in ~6 minutes, i.e. the "60 10000" condition
    should have tripped. Root cause to check: `DEBUG POPULATE` may not
    increment `server.dirty` the way normal `SET` traffic does, so this
    specific loadgen method under-counts dirtiness. Needs a confirmation run
    with real `SET`/pipelined traffic to see whether a stale snapshot actually
    gets reloaded (as hypothesized), or whether in-memory-only data really can
    vanish with zero reload at all once no snapshot ever fires.

## Conclusion
Confirms the core scenario: no `maxmemory` means Valkey is unaware of the
container's memory limit, fills it, and the kernel OOM-kills the container.
The kubelet restarts it in under a second — far faster than any
`cluster-node-timeout`/failure-detection window — and the emptyDir survives
the restart, keeping `nodes.conf` (node identity) while *not* necessarily
keeping any data, depending on whether a background save ever ran.
