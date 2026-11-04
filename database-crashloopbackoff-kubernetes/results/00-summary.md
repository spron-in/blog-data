# 00 - Plan and summary

Environment: k3d, single node, Kubernetes v1.37.1+k3s1, containerd 2.3.4, cgroup v2,
kernel 6.12 (arm64), 8 GB VM, `local-path` storage. Images: `postgres:18` (18.6), `postgres:17`,
`mysql:8.4` (8.4.13), `mysql:8.0` (8.0.46), `mysql:9.5` (9.5.0). Plain StatefulSets, no operator.

Every test manifest is generated from `00-baseline-*.yaml` by `scripts/gen.py`; every
diagnosis used `scripts/crashloop-triage.sh`.

## Summary

| #   | Engine | Cause                                         | Pod status                   | lastState     | Self-heals after fix?                |
|-----|--------|-----------------------------------------------|------------------------------|---------------|--------------------------------------|
| 10  | PG 18  | Typo in parameter name                        | CrashLoopBackOff             | Error/1       | Starts, but pg_hba never configured  |
| 11  | PG 18  | Missing shared_preload_libraries              | CrashLoopBackOff             | Error/1       | Yes                                  |
| 12  | MySQL  | Removed variable (query_cache_size)           | CrashLoopBackOff             | Error/1       | **No** - datadir unusable, wipe PVC  |
| 20  | PG 18  | shared_buffers > memory limit                 | CrashLoopBackOff             | OOMKilled/137 | Yes, after 2 more OOMs in recovery   |
| 21  | MySQL  | buffer pool > memory limit                    | OOMKilled -> CrashLoopBackOff | OOMKilled/137 | Half-init: root@localhost, no password |
| 22  | MySQL  | innodb_dedicated_server=ON                    | CrashLoopBackOff             | OOMKilled -> Error/1 | **No** - wipe PVC             |
| 30  | MySQL  | Liveness, no startupProbe, during init        | 1 restart                    | Error/137     | Yes (luck: init < grace period)      |
| 30b | MySQL  | Same + 60s seed script                        | Running 1/1                  | Error/137     | Silent partial seed                  |
| 31  | PG 18  | Liveness during crash recovery (113s needed)  | CrashLoopBackOff             | Completed/0   | Needs startupProbe + liveness timeout |
| 31' | PG 18  | 1s probe timeout under 200m CPU               | restarts                     | Completed/0   | Needs timeoutSeconds > 1             |
| 40  | PG 18  | Secret missing                                | CreateContainerConfigError   | -             | Yes                                  |
| 41  | PG 18  | Password empty                                | CrashLoopBackOff             | Error/1       | Yes                                  |
| 42  | MySQL  | Wrong key name in Secret                      | CrashLoopBackOff             | Error/1       | Yes                                  |
| 43  | PG 18  | Rotated password + authenticating probe       | CrashLoopBackOff             | Completed/0   | Revert Secret or ALTER ROLE          |
| 50  | PG 18  | StorageClass missing                          | Pending                      | -             | Yes                                  |
| 51  | PG 17  | lost+found in PGDATA                          | CrashLoopBackOff             | Error/1       | Yes (PGDATA subdir)                  |
| 52  | PG 18  | Old mountPath /var/lib/postgresql/data        | CrashLoopBackOff             | Error/1       | Yes (mount /var/lib/postgresql)      |
| 53  | MySQL  | lost+found in datadir                         | Running                      | -             | n/a - MySQL ignores it               |
| 54  | PG 18  | runAsUser 999, root-owned volume, no fsGroup  | CrashLoopBackOff             | Error/1       | Yes (fsGroup)                        |
| 55  | PG 18  | Disk full via forgotten replication slot      | CrashLoopBackOff             | Error/1       | Needs PVC expansion                  |
| 60  | PG     | 17 -> 18 image bump                           | CrashLoopBackOff             | Error/1       | Yes, image back to 17                |
| 61  | MySQL  | 8.4 -> 8.0 rollback                           | CrashLoopBackOff             | Error/1       | Image back to 8.4; 8.0 needs a pre-upgrade backup |
| 62  | MySQL  | 8.0 -> 9.5 skipping LTS                       | CrashLoopBackOff             | Error/1       | Yes, image back to 8.0               |

Backoff: 10s, 20s, 40s, 80s, 160s, then 300s flat (measured over 25 minutes).

## Themes

1. **The first boot is the most dangerous.** Tests 10, 12, 21, 22, 30b: anything that kills the
   container during the image entrypoint's init phase leaves a datadir that the next start
   treats as "already initialized". Outcomes range from permanent crash loops (MySQL) to a
   pod that is Ready but broken (PG: no remote access; MySQL: root without password; partial
   seed data).
2. **Kubernetes events never say OOMKilled.** Only `lastState.terminated.reason` does.
3. **137 is not always memory.** `OOMKilled/137` vs `Error/137` (liveness + grace-period SIGKILL).
   And a liveness-killed Postgres shows `Completed/0`.
4. **Some loops can't be fixed by the pod itself**: OOM in recovery, disk full in recovery,
   liveness shorter than recovery - each restart starts redo from the same LSN.
5. **Not everything that looks like it is a crash loop**: missing Secret ->
   CreateContainerConfigError, missing StorageClass -> Pending.
