# 03 - Probes (tests 30, 30b, 31)

## Test 30 - MySQL: no startupProbe, impatient livenessProbe, first init

Manifest: `manifests/30-mysql-liveness-during-init.yaml` (250m CPU, liveness initialDelay 10s,
period 5s, failureThreshold 2, default timeoutSeconds 1).

Timeline from events and logs:

```
07:04:24 [Entrypoint]: Initializing database files
07:04:30 [Entrypoint]: Database files initialized / Starting temporary server (--skip-networking)
07:04:33 Liveness probe failed            (TCP ping can't reach the temp server)
07:04:38 Liveness probe failed
07:04:38 Killing: Container mysql failed liveness probe, will be restarted   (SIGTERM)
07:04:38 [Entrypoint]: Stopping temporary server   <- init carries on, SIGTERM was ignored
07:04:39 MySQL init process done. Ready for start up.
07:04:40 mysqld: ready for connections            (pod even became Ready)
07:05:08 terminationGracePeriodSeconds (30s) expires -> SIGKILL
lastState: Error/137
```

The entrypoint is a bash script running as PID 1 and has no SIGTERM handler, so the kill is
deferred until the grace period runs out. Here init finished inside those 30 seconds, so the
data survived (`root@%` present, password works) - by timing luck only.

Note: `Error/137` (killed by kubelet after grace period) vs `OOMKilled/137` - same exit code,
only `reason` tells them apart.

## Test 30b - Same probe + a 60s seed script in /docker-entrypoint-initdb.d

Seed: create `app.customers`, insert row 1, `SELECT SLEEP(60)` (stands in for loading a dump),
insert row 2, create `app.seed_complete`.

```
07:06:51 Killing: Container mysql failed liveness probe, will be restarted
... SIGKILL 30s later, mid-seed. Restart -> datadir exists -> init skipped.

$ kubectl -n t30b get pod
mysql-0   1/1   Running   1 (72s ago)   2m1s
$ mysql -e "show tables from app; select * from app.customers"
customers
id  name
1   first
```

Running and Ready, no error anywhere, row 2 and `seed_complete` missing. Kubernetes reported
nothing unusual beyond one restart.

## Test 31 - PostgreSQL: crash recovery longer than the liveness window

Manifest: `manifests/31-pg-liveness-during-recovery.yaml` (200m CPU, no startupProbe, liveness
initialDelay 10s / period 5s / failureThreshold 3 -> ~25s window; `max_wal_size=8GB`,
`checkpoint_timeout=60min`).

### Side finding first: probe timeout under CPU limit

Simply running `pgbench -i -s 60` inside that 200m pod got the server killed:

```
Liveness probe failed: command timed out: "pg_isready -U postgres -h 127.0.0.1" timed out after 1s
Killing: Container postgres failed liveness probe, will be restarted
lastState: Completed/0     (postgres handles SIGTERM as a clean fast shutdown)
```

A busy, healthy database killed because `pg_isready` did not get CPU within 1 second.

### Recovery loop

Procedure (so the probe doesn't interfere while generating WAL):

1. Apply `31-...loading-phase.yaml` (2 CPU, liveness timeout 30s, `updateStrategy: OnDelete`).
2. `pgbench -i -s 60` + `pgbench -c 4 -T 60` -> 811 MB of WAL since the last checkpoint.
3. Apply the strict spec (`31-...yaml` + `OnDelete`). Running pod is not replaced.
4. SIGKILL the postmaster from the node (`crictl inspect` for the host PID, `kill -9`), then
   `kubectl delete pod --grace-period=0 --force` so the replacement pod uses the strict spec.

```
07:17:04 crashed
07:17:08 0/1 Running 0
07:17:33 0/1 Running 1
07:17:58 0/1 Running 2
07:18:22 0/1 Running 3
07:18:47 0/1 Running 4
07:19:15 0/1 CrashLoopBackOff 4
07:20:09 0/1 Running 5
07:20:33 0/1 CrashLoopBackOff 5
07:22:03 0/1 Running 6
```

Each attempt:

```
LOG:  redo starts at 0/1761998
LOG:  redo in progress, elapsed time: 20.08 s, current LSN: 0/1DC83C50
FATAL:  the database system is not yet accepting connections
DETAIL:  Consistent recovery state has not been yet reached.
LOG:  received fast shutdown request
```

Always the same start LSN, always killed ~20s in, never finishes.

### Fix

Added a startupProbe (`pg_isready`, period 5s, failureThreshold 60):

```
LOG:  redo starts at 0/1761998
LOG:  redo done at 0/34219C80 system usage: CPU: user: 6.56 s, system: 9.02 s, elapsed: 113.18 s
LOG:  database system is ready to accept connections
```

Recovery needed **113 seconds**; the liveness window was 25. But the first `count(*)` after
recovery got the server killed again by the 1s liveness timeout (`terminating connection due
to administrator command`). Final fix = startupProbe **and** a tolerant liveness probe
(`timeoutSeconds: 5`, `failureThreshold: 6`, as in the baseline): stable, all 6,000,000
`pgbench_accounts` rows present.
