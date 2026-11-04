#!/usr/bin/env python3
"""Generate every test manifest from the two baseline files.

Each test = baseline + a small, explicit patch, so the YAML in manifests/ only
differs from 00-baseline-*.yaml by the failure we are reproducing.
Run from the repo folder:  python3 scripts/gen.py
"""
import copy
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAN = ROOT / "manifests"
BASE = {
    "pg": list(yaml.safe_load_all((MAN / "00-baseline-postgres.yaml").read_text())),
    "mysql": list(yaml.safe_load_all((MAN / "00-baseline-mysql.yaml").read_text())),
}


def kind(docs, k):
    return next(d for d in docs if d["kind"] == k)


def sts(docs):
    return kind(docs, "StatefulSet")


def ctr(docs):
    return sts(docs)["spec"]["template"]["spec"]["containers"][0]


def podspec(docs):
    return sts(docs)["spec"]["template"]["spec"]


TESTS = {}


def test(filename, base, comment):
    def deco(fn):
        TESTS[filename] = (base, comment, fn)
        return fn
    return deco


# --------------------------------------------------------------------------
# Config errors
# --------------------------------------------------------------------------
@test("10-pg-bad-parameter.yaml", "pg",
      "Typo in a postgresql.conf parameter name -> FATAL on start, exit 1.")
def _(d):
    ctr(d)["args"] = ["-c", "shared_buffers=128MB", "-c", "max_conections=200"]


@test("11-pg-missing-preload-library.yaml", "pg",
      "shared_preload_libraries points at an extension that is not in the image.")
def _(d):
    ctr(d)["args"] = ["-c", "shared_preload_libraries=pg_stat_statements,pg_cron"]


@test("12-mysql-bad-parameter.yaml", "mysql",
      "Unknown variable in my.cnf (mounted from a ConfigMap) -> mysqld aborts, exit 1.")
def _(d):
    d.insert(0, {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": "mysql-config"},
        "data": {"custom.cnf": "[mysqld]\ninnodb_buffer_pool_size=256M\nquery_cache_size=0\n"},
    })
    podspec(d)["volumes"] = [{"name": "config", "configMap": {"name": "mysql-config"}}]
    ctr(d)["volumeMounts"].append({"name": "config", "mountPath": "/etc/mysql/conf.d"})


# --------------------------------------------------------------------------
# OOMKilled
# --------------------------------------------------------------------------
@test("20-pg-oom-shared-buffers.yaml", "pg",
      "shared_buffers (512MB) larger than the container memory limit (256Mi).")
def _(d):
    c = ctr(d)
    c["resources"] = {"requests": {"cpu": "500m", "memory": "256Mi"},
                      "limits": {"cpu": "500m", "memory": "256Mi"}}
    c["args"] = ["-c", "shared_buffers=512MB", "-c", "max_wal_size=4GB",
                 "-c", "checkpoint_timeout=30min"]


@test("21-mysql-oom-buffer-pool.yaml", "mysql",
      "innodb_buffer_pool_size (1G) larger than the container memory limit (512Mi).")
def _(d):
    c = ctr(d)
    c["resources"] = {"requests": {"cpu": "1", "memory": "512Mi"},
                      "limits": {"cpu": "1", "memory": "512Mi"}}
    c["args"] = ["--innodb-buffer-pool-size=1G"]


@test("22-mysql-dedicated-server.yaml", "mysql",
      "innodb_dedicated_server=ON sizes the buffer pool from *node* RAM, not the container limit.")
def _(d):
    c = ctr(d)
    c["resources"] = {"requests": {"cpu": "1", "memory": "512Mi"},
                      "limits": {"cpu": "1", "memory": "512Mi"}}
    c["args"] = ["--innodb-dedicated-server=ON"]


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------
@test("30-mysql-liveness-during-init.yaml", "mysql",
      "No startupProbe + an impatient livenessProbe: kubelet kills mysqld during first init.")
def _(d):
    c = ctr(d)
    c.pop("startupProbe")
    c["resources"] = {"requests": {"cpu": "250m", "memory": "1Gi"},
                      "limits": {"cpu": "250m", "memory": "1Gi"}}
    c["livenessProbe"] = {
        "exec": {"command": ["mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]},
        "initialDelaySeconds": 10, "periodSeconds": 5, "failureThreshold": 2,
    }


@test("30b-mysql-liveness-during-seed.yaml", "mysql",
      "Same impatient livenessProbe, plus a slow /docker-entrypoint-initdb.d seed script (60s).")
def _(d):
    c = ctr(d)
    c.pop("startupProbe")
    c["livenessProbe"] = {
        "exec": {"command": ["mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]},
        "initialDelaySeconds": 10, "periodSeconds": 5, "failureThreshold": 2,
    }
    d.insert(0, {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": "mysql-seed"},
        "data": {"01-seed.sql": (
            "CREATE DATABASE app;\n"
            "CREATE TABLE app.customers (id INT PRIMARY KEY, name VARCHAR(64));\n"
            "INSERT INTO app.customers VALUES (1,'first');\n"
            "-- stands in for loading a large dump\n"
            "SELECT SLEEP(60);\n"
            "INSERT INTO app.customers VALUES (2,'second');\n"
            "CREATE TABLE app.seed_complete (ok INT);\n"
        )},
    })
    podspec(d)["volumes"] = [{"name": "seed", "configMap": {"name": "mysql-seed"}}]
    c["volumeMounts"].append({"name": "seed", "mountPath": "/docker-entrypoint-initdb.d"})


@test("31-pg-liveness-during-recovery.yaml", "pg",
      "No startupProbe: crash recovery takes longer than the liveness window -> killed mid-redo, forever.")
def _(d):
    c = ctr(d)
    c.pop("startupProbe")
    c["resources"] = {"requests": {"cpu": "200m", "memory": "1Gi"},
                      "limits": {"cpu": "200m", "memory": "1Gi"}}
    c["args"] = ["-c", "shared_buffers=256MB", "-c", "max_wal_size=8GB",
                 "-c", "checkpoint_timeout=60min"]
    c["livenessProbe"] = {
        "exec": {"command": ["pg_isready", "-U", "postgres", "-h", "127.0.0.1"]},
        "initialDelaySeconds": 10, "periodSeconds": 5, "failureThreshold": 3,
    }


# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------
@test("40-pg-missing-secret.yaml", "pg",
      "secretKeyRef points at a Secret that does not exist -> CreateContainerConfigError (not a crash loop).")
def _(d):
    ctr(d)["env"][0]["valueFrom"]["secretKeyRef"]["name"] = "pg-secrets"


@test("41-pg-empty-password.yaml", "pg",
      "Secret exists but the value is empty (e.g. created from an unset shell variable).")
def _(d):
    kind(d, "Secret")["stringData"]["POSTGRES_PASSWORD"] = ""


@test("42-mysql-wrong-secret-key.yaml", "mysql",
      "envFrom a Secret whose key is MYSQL_PASSWORD (app user) instead of MYSQL_ROOT_PASSWORD.")
def _(d):
    kind(d, "Secret")["stringData"] = {"MYSQL_PASSWORD": "s3cr3t-pass"}
    c = ctr(d)
    c.pop("env")
    c["envFrom"] = [{"secretRef": {"name": "mysql-secret"}}]


@test("43-pg-rotated-password-probe.yaml", "pg",
      "Liveness probe authenticates with the password from the Secret. Rotate the Secret, restart -> killed.")
def _(d):
    c = ctr(d)
    c["env"].append({"name": "PGPASSWORD", "valueFrom": copy.deepcopy(c["env"][0]["valueFrom"])})
    c["env"].append({"name": "POD_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.podIP"}}})
    # The official image trusts 127.0.0.1 in pg_hba.conf, so a localhost probe never
    # checks the password. Probing the pod IP behaves like a real client.
    probe = ["sh", "-c", 'psql -h "$POD_IP" -U postgres -c "SELECT 1"']
    c["livenessProbe"]["exec"]["command"] = probe
    c["livenessProbe"]["failureThreshold"] = 3


# --------------------------------------------------------------------------
# Storage / PVC
# --------------------------------------------------------------------------
LOST_FOUND = {
    # Simulates a freshly formatted ext4 block volume (EBS, PD, Azure Disk, Ceph RBD...),
    # whose root always contains lost+found. local-path volumes do not.
    "name": "simulate-ext4", "image": "busybox:1.37",
    "command": ["sh", "-c", "mkdir -p /data/lost+found"],
}


@test("50-pvc-pending.yaml", "pg",
      "volumeClaimTemplate asks for a StorageClass that does not exist -> Pending (not a crash loop).")
def _(d):
    sts(d)["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"] = "fast-ssd"


@test("51-pg17-lost-found.yaml", "pg",
      "postgres:17, PGDATA == volume root, volume root contains lost+found -> initdb refuses.")
def _(d):
    c = ctr(d)
    c["image"] = "postgres:17"
    c["volumeMounts"][0]["mountPath"] = "/var/lib/postgresql/data"
    podspec(d)["initContainers"] = [dict(LOST_FOUND, volumeMounts=[{"name": "data", "mountPath": "/data"}])]


@test("52-pg18-old-mount-path.yaml", "pg",
      "postgres:18 with the pre-18 mountPath /var/lib/postgresql/data copied from an old manifest.")
def _(d):
    ctr(d)["volumeMounts"][0]["mountPath"] = "/var/lib/postgresql/data"


@test("53-mysql-lost-found.yaml", "mysql",
      "mysql:8.4, datadir == volume root, volume root contains lost+found.")
def _(d):
    podspec(d)["initContainers"] = [dict(LOST_FOUND, volumeMounts=[{"name": "data", "mountPath": "/data"}])]


@test("54-pg-volume-permissions.yaml", "pg",
      "Non-root postgres (runAsUser 999) on a root-owned volume with no fsGroup.")
def _(d):
    ps = podspec(d)
    ps["securityContext"] = {"runAsUser": 999, "runAsGroup": 999, "runAsNonRoot": True}
    ps["initContainers"] = [{
        "name": "simulate-root-owned", "image": "busybox:1.37",
        "command": ["sh", "-c", "chown 0:0 /data && chmod 755 /data"],
        "securityContext": {"runAsUser": 0, "runAsNonRoot": False},
        "volumeMounts": [{"name": "data", "mountPath": "/data"}],
    }]


@test("55-pg-disk-full.yaml", "pg",
      "Data volume runs out of space. A 300Mi tmpfs stands in for a small PVC (local-path ignores size).")
def _(d):
    c = ctr(d)
    c["resources"] = {"requests": {"cpu": "500m", "memory": "1Gi"},
                      "limits": {"cpu": "500m", "memory": "1Gi"}}
    c["args"] = ["-c", "shared_buffers=128MB"]
    sts(d)["spec"].pop("volumeClaimTemplates")
    podspec(d)["volumes"] = [{"name": "data", "emptyDir": {"medium": "Memory", "sizeLimit": "300Mi"}}]


# --------------------------------------------------------------------------
# Version changes (apply, load, then change the image - see results/)
# --------------------------------------------------------------------------
@test("60-pg17-then-18.yaml", "pg",
      "Start on postgres:17 with PGDATA pinned; later bump the image to postgres:18.")
def _(d):
    c = ctr(d)
    c["image"] = "postgres:17"
    c["env"].append({"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"})
    c["volumeMounts"][0]["mountPath"] = "/var/lib/postgresql/data"


@test("61-mysql84-then-80.yaml", "mysql",
      "Start on mysql:8.4; later 'roll back' the image to mysql:8.0.")
def _(d):
    pass


@test("62-mysql80-then-95.yaml", "mysql",
      "Start on mysql:8.0; later jump straight to mysql:9.5 (skipping 8.4 LTS).")
def _(d):
    ctr(d)["image"] = "mysql:8.0"


def main():
    for filename, (base, comment, fn) in TESTS.items():
        docs = copy.deepcopy(BASE[base])
        fn(docs)
        out = f"# {comment}\n# Generated by scripts/gen.py from 00-baseline-{'postgres' if base == 'pg' else 'mysql'}.yaml\n"
        out += yaml.safe_dump_all(docs, sort_keys=False, default_flow_style=None, width=120)
        (MAN / filename).write_text(out)
        print("wrote", filename)


if __name__ == "__main__":
    main()
