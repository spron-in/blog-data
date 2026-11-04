# 06 - Version changes (tests 60, 61, 62)

Each one: apply the manifest, create a marker object, then `kubectl set image`.

## Test 60 - postgres:17 -> postgres:18 (PGDATA pinned to /var/lib/postgresql/data/pgdata)

```
pg-0   0/1   CrashLoopBackOff   3 (46s ago)   82s
last=Error/1
FATAL:  database files are incompatible with server
DETAIL:  The data directory was initialized by PostgreSQL version 17, which is not compatible with this version 18.6 (Debian 18.6-1.pgdg13+2).
```

Major versions need `pg_upgrade` (or dump/restore, or logical replication). Rolling the image
back to 17 recovers it - nothing was written (verified with the same image/volume layout in
Docker: marker table still there).

## Test 61 - mysql:8.4 -> mysql:8.0 ("rollback")

```
mysql-0   0/1   CrashLoopBackOff   3 (40s ago)   82s
last=Error/1
[ERROR] [MY-014061] [InnoDB] Invalid MySQL server downgrade: Cannot downgrade from 80413 to 80046. Downgrade is only permitted between patch releases.
[ERROR] [MY-010334] [Server] Failed to initialize DD Storage Engine
[ERROR] [MY-010020] [Server] Data Dictionary initialization failed.
```

Once 8.4 has started on the datadir, the data dictionary is upgraded; going back means restoring
a backup taken before the upgrade.

## Test 62 - mysql:8.0 -> mysql:9.5 (skipping 8.4 LTS)

```
mysql-0   0/1   CrashLoopBackOff   2 (9s ago)   82s
last=Error/1
[ERROR] [MY-014060] [Server] Invalid MySQL server upgrade: Cannot upgrade from 80046 to 90500. Upgrade to next major version is only allowed from the last LTS release, which version 80046 is not.
[ERROR] [MY-010020] [Server] Data Dictionary initialization failed.
```

Path: 8.0 -> 8.4 LTS -> 9.x. Here the refusal happens before anything is changed, so setting
the image back to 8.0 works (verified in Docker: 8.0 starts again, `keepme` database intact).
