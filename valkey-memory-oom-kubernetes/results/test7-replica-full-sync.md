# Test 7: Replica full-sync data loss after primary OOM

## Config
- Topology: `replication`, 1 primary + 1 replica, no PVC (emptyDir)
- Resources: 1Gi limit = request (Guaranteed QoS)
- `maxmemory 850mb`, `maxmemory-policy noeviction`
- Default `save` rules left ON (not disabled)
- Manifest: `test7-replica-full-sync.yaml`

## Timeline (all confirmed from pod status + container logs, not inferred)
1. Loaded primary to 75,000 keys via `DEBUG POPULATE` (~776MB `used_memory`, well under both
   `maxmemory` 850MB and the 1Gi limit). Replica confirmed `master_link_status:up`, in sync.
2. Forced a full resync once (`CLIENT KILL TYPE replica`) — primary logged `Full resync requested`,
   diskless RDB-to-socket transfer succeeded, replica reconnected. 20 ticks (20s) afterward,
   `used_memory` on the primary stayed flat (~776MB), no new writes were issued.
3. Script exited. ~11 minutes later (no monitoring running), the **primary container was OOMKilled**
   (`lastState.terminated.reason: OOMKilled`, `exitCode: 137`, confirmed via `kubectl get pod -o
   jsonpath`). It restarted in under a second and came back with `used_memory:3212960` (~3MB) —
   empty — but kept `role:master` and `connected_slaves:1` the whole time (the replica never
   dropped its connection to notice anything had happened).
4. To reproduce the cluster-level consequence, I deleted the replica pod so it would lose its
   in-memory replication state and request a brand-new full resync on reconnect (closest analogue
   to a replica restart). The primary's log shows it happily serving that resync from its now-empty
   dataset: `Full resync requested by replica ... Synchronization with replica ... succeeded`.
5. Result: **both primary and replica `DBSIZE` are now `0`.** All 75,000 keys are gone.
6. `kubectl get valkeycluster test7-replica-sync` still reports **`STATE: Ready  REASON:
   ClusterHealthy`** the entire time — before, during, and after the data loss. Nothing in the
   ValkeyCluster/ValkeyNode status reflects the OOM kill, the restart, or the data loss.

## What's confirmed vs. what's inferred
- **Confirmed by hard evidence**: primary OOMKilled while idle (no monitored write load at the time
  of death), restarted empty, resynced a replica from empty, `ClusterHealthy` stayed green through
  all of it.
- **Not confirmed / open question**: exactly what caused the primary to tip over the 1Gi limit
  ~11 minutes after it had been flat at 776MB with no new writes. The two most likely candidates,
  neither separately confirmed:
  - the default `save 60 10000`-class periodic background save (not disabled in this test) forking
    repeatedly over time;
  - cumulative/fragmenting overhead from repeated diskless replica resyncs (each one forks a RDB
    pipe-to-socket child).
  I did not have the monitoring loop running during that 11-minute gap, so I can't show the exact
  memory curve leading to the kill — only the before/after snapshots and the OOMKilled evidence.
  This is the one place in the whole test matrix where I'm reporting a real, verified *outcome*
  without a complete *mechanism* trace, and the writeup/blog post should say so explicitly.

## Why this matters
This is the single most dangerous result in the whole test matrix: a transient OOM kill (self-heals
in under a second at the pod level) can silently cascade into **permanent, total data loss across
the entire replica set**, while every piece of cluster status tooling says `Healthy`. No Kubernetes
Event, no ValkeyCluster condition, nothing short of literally diffing `DBSIZE` before and after would
catch this in production.
