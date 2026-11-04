# 05 - Storage / PVC (tests 50-55)

## Test 50 - StorageClass does not exist

Not a crash loop - the pod is never scheduled:

```
pg-0   0/1   Pending   0   59s
Warning  FailedScheduling  0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims.
```

## Test 51 - postgres:17, volume root is PGDATA, volume contains lost+found

Freshly formatted ext4 block volumes (EBS, PD, Azure Disk, RBD, ...) always have `lost+found`
in their root; local-path doesn't, so an initContainer creates it.

```
pg-0   0/1   CrashLoopBackOff   1 (10s ago)   58s
last=Error/1
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
initdb: detail: It contains a lost+found directory, perhaps due to it being a mount point.
initdb: hint: Using a mount point directly as the data directory is not recommended.
```

Fix: point `PGDATA` at a subdirectory (e.g. `/var/lib/postgresql/data/pgdata`), or on 18+ mount
the parent `/var/lib/postgresql`.

## Test 52 - postgres:18 with the pre-18 mountPath (/var/lib/postgresql/data)

Fresh, **empty** volume:

```
pg-0   0/1   CrashLoopBackOff   3 (5s ago)   58s
last=Error/1
Error: in 18+, these Docker images are configured to store database data in a
       format which is compatible with "pg_ctlcluster" (specifically, using
       major-version-specific directory names).  ...
       Counter to that, there appears to be PostgreSQL data in:
         /var/lib/postgresql/data (unused mount/volume)
       This is usually the result of upgrading the Docker image without
       upgrading the underlying database using "pg_upgrade" (which requires both
       versions).
       The suggested container configuration for 18+ is to place a single mount
       at /var/lib/postgresql ...
```

The message says "there appears to be PostgreSQL data" and talks about upgrades, but the volume
is brand new. The entrypoint treats *any* mount at `/var/lib/postgresql/data` as a leftover
(`mountpoint -q /var/lib/postgresql/data`). Fix: mount at `/var/lib/postgresql` (or set PGDATA
explicitly).

## Test 53 - MySQL 8.4 with lost+found in the datadir

Negative result: MySQL initializes fine, `root@%` and `root@localhost` exist, password works.
MySQL 8.x ignores `lost+found`.

## Test 54 - Non-root postgres on a root-owned volume, no fsGroup

```
pg-0   0/1   CrashLoopBackOff   3 (7s ago)   59s
last=Error/1
mkdir: cannot create directory '/var/lib/postgresql/18': Permission denied
```

Fix: `securityContext.fsGroup: 999` (baseline has it), or an initContainer that chowns.

## Test 55 - Disk full (forgotten replication slot)

A 300Mi tmpfs `emptyDir` stands in for a small PVC (local-path does not enforce sizes).
Survives container restarts, which is all that matters here.

1. `pgbench -i -s 30` into 300Mi -> data file extension fails gracefully:
   `ERROR: could not extend file "base/5/16403" with FileFallocate(): No space left on device`.
   No crash, the COPY rolls back. (The aborted COPY's pages stay on disk until vacuum.)
2. `pg_create_physical_replication_slot('forgotten_replica', true)` - a slot whose replica never
   comes back holds all WAL.
3. Tiny updates + `pg_switch_wal()`:

```
PANIC:  could not write to file "pg_wal/xlogtemp.753": No space left on device
```

Restart -> crash recovery replays WAL, which re-extends data files:

```
LOG:  database system was interrupted while in recovery at 2026-11-04 07:07:45 UTC
LOG:  redo starts at 0/1761998
FATAL:  could not extend file "base/5/16403": No space left on device
CONTEXT:  WAL redo at 0/181BCF8 for Heap2/MULTI_INSERT+INIT: ...
LOG:  startup process (PID 34) exited with exit code 1
LOG:  shutting down due to startup process failure
pg-0   0/1   CrashLoopBackOff   1 (8s ago)   3m34s
```

The server can't start, so you can't drop the slot or vacuum from SQL. Fix: expand the PVC
(StorageClass with `allowVolumeExpansion: true`), let it start, then
`SELECT pg_drop_replication_slot('forgotten_replica')`. Don't `rm` files in `pg_wal`.
