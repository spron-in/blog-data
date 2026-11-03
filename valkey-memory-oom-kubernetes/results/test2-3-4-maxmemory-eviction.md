# Tests 2, 3, 4: maxmemory + eviction policy behavior (1Gi limit)

## Important methodology note (applies to all three)
The initial load generator used `DEBUG POPULATE` to bulk-insert keys. That command **does not go
through Valkey's normal OOM/command-deny check** the way client commands like `SET` do. Result:
under `noeviction`, `DEBUG POPULATE` kept writing straight past `maxmemory` until the container's
real cgroup limit triggered a kernel OOM kill — which made tests 2 and 3 both OOM-kill at the same
~1033MB point, regardless of their different `maxmemory` settings (1000mb vs 850mb). That's an
artifact of the load generator, not of `maxmemory` itself. I re-validated test 3 with real traffic
(`valkey-benchmark -t set`, a normal client command) — see below. Test 4 (`allkeys-lru`) was
unaffected because eviction is enforced by a separate mechanism (`performEvictions`, part of the
server cron) that runs regardless of which command is writing, so its original run stands.

## Test 2: `maxmemory` ≈ container limit (1000mb maxmemory under 1Gi/1073MB limit, noeviction)
- Config: `maxmemory 1000mb` (1048MB), `maxmemory-policy noeviction`, no persistence.
- Raw run (via `DEBUG POPULATE`): OOMKilled at `used_memory` ≈ 1033MB, container restarted.
- Caveat: this run is subject to the methodology issue above — load kept growing past 1000mb maxmemory
  because `DEBUG POPULATE` bypassed the OOM check, so the kill came from the raw 1Gi cgroup limit, not
  necessarily from `maxmemory` enforcement.
- Conclusion to use in the post: with only ~24MB of headroom between `maxmemory` and the container
  limit, there usually isn't enough room for Valkey's own non-dataset overhead (connection buffers,
  replication backlog, client output buffers, fragmentation) — so even *if* `maxmemory` correctly
  rejects writes right at 1000mb, the container can still be killed by overhead stacked on top of
  that 1000mb. This matches conventional guidance (leave real headroom, not just a few percent) but
  I'm flagging that this specific run's numbers are not fully clean evidence on their own.

## Test 3: `maxmemory` with real headroom (850mb maxmemory under 1Gi/1073MB limit, noeviction)
- Raw run (via `DEBUG POPULATE`): also OOMKilled at ~1033MB — same artifact as test 2, not a real
  `maxmemory` failure.
- **Corrected run** with `valkey-benchmark -a <pass> -t set -n 200000 -d <bytes> -r <range> -c
  <clients> --threads <n> -q` (real client traffic) after `FLUSHALL`:
  - `used_memory` climbed to `890,949,032` bytes, essentially exactly at
    `maxmemory:891,289,600` (850mb → 850×1024×1024, confirming `mb` = MiB, not decimal MB).
  - Then started failing with `Error from server: OOM command not allowed when used memory >
    'maxmemory'.` (`errorstat_OOM:count=12` from `INFO errorstats`).
  - `DBSIZE` stabilized at 86,081 keys.
  - **No container restart** (`restartCount` unchanged from the earlier DEBUG-POPULATE-induced kill).
- Conclusion: with real headroom (850MB `maxmemory` under a 1Gi limit, ~173MB/16% margin) and real
  client traffic, `noeviction` does exactly what it's supposed to: politely reject new writes with an
  `OOM` error instead of letting the container get killed.

## Test 4: `allkeys-lru` (850mb maxmemory under 1Gi limit)
- Ran via `DEBUG POPULATE` — unaffected by the methodology issue since eviction runs independent of
  which command is writing.
- `evicted_keys` climbed steadily as load continued; `used_memory`/`DBSIZE` stayed capped near the
  850mb ceiling throughout. No OOM kill, no restart.
- Conclusion: `allkeys-lru` behaved as expected — oldest/least-recently-used keys were evicted to
  make room, keeping memory under control automatically.

## Takeaway for the post
- `maxmemory` + `noeviction` really does prevent OOM kills, *if* you give it genuine headroom under
  the container limit and your traffic is made of normal client commands.
- Admin/bulk paths (`DEBUG POPULATE`, and by extension things like replication stream application,
  `MIGRATE`, Lua scripts) are not guaranteed to respect the same OOM-deny check as ordinary commands
  — worth a callout since people do sometimes bulk-load data by paths other than plain `SET`.
- `allkeys-lru` is the simplest way to guarantee the container itself never gets OOMKilled from
  dataset growth, at the cost of being willing to silently drop data.
