# 04 - Secrets (tests 40, 41, 42, 43)

## Test 40 - Secret does not exist (typo in secretKeyRef name)

Not a crash loop - the container is never created:

```
pg-0   0/1   CreateContainerConfigError   0   59s
state: {"waiting":{"message":"secret \"pg-secrets\" not found","reason":"CreateContainerConfigError"}}
Warning  Failed  Error: secret "pg-secrets" not found
```

## Test 41 - Secret exists, password value is empty

(e.g. `kubectl create secret generic pg-secret --from-literal=POSTGRES_PASSWORD=$PG_PASS` with
`PG_PASS` unset.)

```
pg-0   0/1   CrashLoopBackOff   3 (13s ago)   58s
last=Error/1
Error: Database is uninitialized and superuser password is not specified.
```

## Test 42 - MySQL: Secret has MYSQL_PASSWORD (app user) instead of MYSQL_ROOT_PASSWORD

```
mysql-0   0/1   CrashLoopBackOff   3 (9s ago)   58s
last=Error/1
[ERROR] [Entrypoint]: Database is uninitialized and password option is not specified
```

## Test 43 - Rotating the password in the Secret

Run 1 (liveness probe = `psql -h 127.0.0.1 -U postgres -c 'SELECT 1'` with `PGPASSWORD` from
the Secret): rotate Secret, delete pod -> **nothing happens**, pod stays Running. The official
image's `pg_hba.conf`:

```
local   all  all                 trust
host    all  all  127.0.0.1/32   trust
host    all  all  ::1/128        trust
...
host all all all scram-sha-256
```

Localhost never checks the password. A real client over the network:

```
FATAL:  password authentication failed for user "postgres"
```

The `POSTGRES_PASSWORD` env var is only used by `initdb` on the first boot; changing the Secret
does not change the database password, it only breaks everyone who reads the new value.

Run 2 (`manifests/43-pg-rotated-password-probe.yaml`, probe authenticates against `$POD_IP`):

```
07:06:xx  Secret rotated -> pod keeps running (env vars are only read at container start)
07:09:59  pod deleted (stands in for a node drain / rollout)
07:11:51  Killing: Container postgres failed liveness probe, will be restarted
          Liveness probe failed: psql: error: connection to server at "10.42.0.91", port 5432 failed:
          FATAL:  password authentication failed for user "postgres"
...
pg-0   0/1   CrashLoopBackOff   9 (44s ago)   15m
lastState: Completed/0
state: back-off 5m0s restarting failed container=postgres
```

A crash loop whose last termination is `Completed`, exit code `0` - postgres shut down cleanly
on SIGTERM every time. Nothing in `lastState` hints at an error; the reason is only in the
`Unhealthy` event text.

Note for MySQL: `mysqladmin ping` exits 0 even on `Access denied`, which makes it a safe
liveness probe regardless of password rotation:

```
$ mysqladmin ping -h 127.0.0.1 -uroot -pwrong
mysqladmin: connect to server at '127.0.0.1' failed
error: 'Access denied for user 'root'@'127.0.0.1' (using password: YES)'
exit=0
```
