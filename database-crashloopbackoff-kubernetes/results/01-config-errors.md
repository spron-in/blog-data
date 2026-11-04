# 01 - Config errors (tests 10, 11, 12)

Backoff timing measurements are also here, because a config typo is the cleanest
"crash immediately on every start" case.

## Test 10 - PostgreSQL: typo in a parameter name

Manifest: `manifests/10-pg-bad-parameter.yaml` (`-c max_conections=200`).

```
pg-0   0/1   CrashLoopBackOff   3 (6s ago)   45s
postgres  restarts=3  last=Error/1
FATAL:  unrecognized configuration parameter "max_conections"
```

### Follow-up: the first boot was only half done

The very first container ran `initdb` successfully, then the entrypoint started its temporary
server with the same bad args, which failed. `PG_VERSION` already existed, so every later start
printed `Database directory appears to contain a database; Skipping initialization`.

After fixing the typo (removing `args`), the pod went `1/1 Running` with probes green, but:

```
$ psql -h pg-0.pg -U postgres
psql: error: ... FATAL:  no pg_hba.conf entry for host "10.42.0.23", user "postgres", database "postgres", no encryption
```

`pg_hba.conf` only contains the `trust` entries for local/127.0.0.1; the
`host all all all scram-sha-256` line the entrypoint appends (`pg_setup_hba_conf`) was never
written because that step ran `postgres -C password_encryption <bad args>` and failed.
Anything else the entrypoint does after that (POSTGRES_USER / POSTGRES_DB creation,
`/docker-entrypoint-initdb.d` scripts) is also skipped. Fix: wipe the PVC and re-init.

## Test 11 - PostgreSQL: shared_preload_libraries points at a missing extension

```
pg-0   0/1   CrashLoopBackOff   3 (3s ago)   46s
postgres  restarts=3  last=Error/1
FATAL:  could not access file "pg_cron": No such file or directory
LOG:  database system is shut down
```

## Test 12 - MySQL: removed variable in my.cnf (`query_cache_size`, gone since 8.0)

Attempt 0 (reproduced with plain `docker run` of the same image/entrypoint/cnf because kubelet
only keeps the newest container log; see `raw/t12-attempt0.log`):

```
[Entrypoint]: Initializing database files
[ERROR] [MY-000067] [Server] unknown variable 'query_cache_size=0'.
[ERROR] [MY-013236] [Server] The designated data directory /var/lib/mysql/ is unusable. You can remove all files that the server added to it.
[ERROR] [MY-010119] [Server] Aborting
```

Attempt 1+ (datadir is non-empty, so the entrypoint skips init):

```
[ERROR] [MY-010735] [Server] Could not open the mysql.plugin table. Please perform the MySQL upgrade procedure.
[ERROR] [MY-000067] [Server] unknown variable 'query_cache_size=0'.
```

**Fixing the ConfigMap does not recover the pod** (verified both in Docker and in Kubernetes
after `kubectl patch cm` + pod delete):

```
[ERROR] [MY-010326] [Server] Fatal error: Can't open and lock privilege tables: Table 'mysql.user' doesn't exist
[ERROR] [MY-010952] [Server] The privilege system failed to initialize correctly.
[ERROR] [MY-010119] [Server] Aborting
```

The only fix is deleting the PVC (or emptying the datadir) and initializing again.

## CrashLoopBackOff delay timing (Kubernetes v1.37.1, k3s)

`scripts/watch-restarts.sh` on test 11 for 25 minutes (`raw/backoff-watch.log`). Container start
times and gap to the previous start:

| restart | started  | gap   |
|---------|----------|-------|
| 0       | 06:46:47 | -     |
| 2       | 06:46:59 | ~12s  |
| 3       | 06:47:25 | ~26s  |
| 4       | 06:48:21 | ~56s  |
| 5       | 06:49:43 | ~82s  |
| 6       | 06:52:24 | ~161s |
| 7       | 06:57:30 | ~306s |
| 8       | 07:02:51 | ~321s |
| 9       | 07:08:05 | ~314s |

10s doubling, capped at 5 minutes (`back-off 5m0s restarting failed container`), plus a couple
of seconds of container start/exit time. 9 restarts in 21 minutes.

`ReduceDefaultCrashLoopBackOffDecay` (1s initial, 60s max) is still alpha / off by default in
the Kubernetes source as of this test. `KubeletCrashLoopBackOffMax` (beta, on by default since
1.35) lets an admin lower the cap per node via `crashLoopBackOff.maxContainerRestartPeriod` in
the KubeletConfiguration. Practical consequence: once you fix the cause, the pod may sit up to
5 minutes before trying again - `kubectl delete pod` resets the counter.
