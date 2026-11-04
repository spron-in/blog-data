# 02 - OOMKilled (tests 20, 21, 22)

All containers ran on cgroup v2 with `memory.oom.group = 1` (checked on the node), so an OOM
kill takes out the whole container, not just the biggest process.

## Test 20 - PostgreSQL: shared_buffers (512MB) > memory limit (256Mi)

Manifest: `manifests/20-pg-oom-shared-buffers.yaml` (also `max_wal_size=4GB`,
`checkpoint_timeout=30min`, so lots of WAL piles up between checkpoints - common tuning).

The server starts fine: shared memory is only charged to the cgroup when pages are touched.

Load: `pgbench -i -s 40` (4M rows). It died while building the primary key:

```
creating primary keys...
command terminated with exit code 137
lastState: {"exitCode":137,"reason":"OOMKilled"}
```

Then the restart loop: each start runs crash recovery, which reads pages into the oversized
buffer pool, and gets OOM-killed again. No client traffic at all.

```
pg-0   0/1   CrashLoopBackOff   4 (17s ago)   3m13s
lastState: {"exitCode":137,"reason":"OOMKilled", startedAt 06:50:30, finishedAt 06:50:32}
LOG:  database system was interrupted while in recovery at 2026-11-04 06:49:37 UTC
HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
LOG:  redo starts at 0/1761998
```

Every attempt starts redo at the same LSN - no progress is ever made.
`kubectl get events` shows only `Startup probe failed` and `BackOff`; the word OOMKilled only
appears in `status.containerStatuses[].lastState`.

Fix tested: `shared_buffers=128MB` with the same 256Mi limit. Recovery still got OOM-killed
**twice more** before the third attempt finished (`redo done at 0/1B578D08 ... elapsed: 2.97 s`).
The likely reason is WAL reads and dirty page cache, which count against the same 256Mi cgroup. All
4,000,000 rows were intact afterwards. Lesson: half the limit is not enough headroom for a
recovering Postgres on a tiny pod; keep shared_buffers ~25% of the limit.

## Test 21 - MySQL: innodb_buffer_pool_size (1G) > memory limit (512Mi)

First surprise: it was OOM-killed **during first initialization** (4s after start), then came up
`1/1 Running` on restart 1. The data directory was half-initialized:

```
$ mysql -uroot -ps3cr3t-pass -h127.0.0.1
ERROR 1130 (HY000): Host '127.0.0.1' is not allowed to connect to this MySQL server
$ mysql -uroot            # no password!
user              host
root              localhost
mysql.infoschema  localhost ...
```

`--initialize-insecure` had completed (root@localhost, empty password) but the entrypoint never
got to set the password or create `root@'%'`. The pod is Ready (mysqladmin ping does not care),
remote clients cannot log in, and local root has no password.

Idle memory, read from the container cgroup:

```
memory.max      536870912
memory.current  523444224
anon            519680000   (~496 MiB of 512 MiB, idle)
@@innodb_buffer_pool_size = 1024 MB
```

Any query pushes it over. A simple create/insert loop:

```
06:52:57 Running 2
06:53:05 OOMKilled 2
06:53:13 CrashLoopBackOff 2
06:54:27 Running 3
```

## Test 22 - MySQL: innodb_dedicated_server=ON

Docker first (`-m 512m`, same cgroup v2 `memory.max` as a pod limit), VM has 8 GB RAM:

```
mysql:8.4: innodb_buffer_pool_size = 5376 MB, innodb_redo_log_capacity = 5120 MB
mysql:8.0: innodb_buffer_pool_size = 6144 MB, innodb_redo_log_capacity = 3072 MB
```

`innodb_dedicated_server` sizes from host RAM, not the container limit.

On Kubernetes (512Mi limit, node capacity 8024712Ki), polled once per second:

```
0 /
1 OOMKilled/137       <- first boot, inside --initialize
1 Error/1
2 Error/1
3 Error/1
```

Every attempt after the first:

```
[Entrypoint]: Initializing database files
[ERROR] [MY-010457] [Server] --initialize specified but the data directory has files in it. Aborting.
[ERROR] [MY-013236] [Server] The designated data directory /var/lib/mysql/ is unusable. You can remove all files that the server added to it.
```

Same failure pattern as test 12: the first boot died half way, and only a PVC wipe gets out of it.
