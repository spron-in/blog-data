# Self-hosting TiDB on Kubernetes

Scripts, manifests and raw results for the blog post
[Self-Hosting TiDB on Kubernetes: HTAP, Scaling and Backups, Measured](https://openeverest.io/blog/self-hosting-tidb-on-kubernetes/).

TiDB clusters are [OpenEverest](https://openeverest.io) Instances, created by
[provider-tidb](https://github.com/openeverest/provider-tidb) on TiDB Operator v2. The load is
[go-tpc](https://github.com/pingcap/go-tpc) (TPC-C and CH-benCHmark) plus a few small Python tools,
all run from one `loadgen` pod inside the cluster.

## Test bed

| | |
|---|---|
| Kubernetes | A managed Kubernetes service, Kubernetes 1.36, Frankfurt |
| Database nodes | 6 × dedicated 16 vCPU / 64 GB, tainted `dedicated=tidb:NoSchedule` |
| Other nodes | 2 × dedicated 8 vCPU / 16 GB: OpenEverest, the operator and Prometheus on one, `loadgen` on the other |
| Storage | The cloud provider's network block storage, a StorageClass with reclaim policy `Delete` |
| Software | OpenEverest v2.0.0-dev.4, provider-tidb 0.2.2, TiDB Operator v2.0.1, TiDB 8.5.2 (7.5.5 for the upgrade) |

## Layout

| Path | What it is |
|---|---|
| `manifests/prepare-nodes.sh` | Taints and labels the database nodes |
| `manifests/loadgen.yaml` | The load generator pod (Python, pymysql, MariaDB client, go-tpc); set the node it runs on |
| `manifests/prepull.yaml` | DaemonSet that pulls every TiDB image onto the database nodes before the start-up timings |
| `manifests/backup-storage.yaml` | S3-compatible `BackupStorage` and its credentials (placeholders) |
| `scripts/common/gen.py` | Writes an `Instance` from a live `InstancePreset` (`tidb-standard`, `tidb-analytics`), pinned to the database nodes, volumes on `$STORAGE_CLASS`; `--version`, `--no-tls`, `--drop tiproxy` |
| `scripts/common/env.sh` | Turns an Instance's `<name>-conn` Secret into `/work/<name>.env` in `loadgen` (`H`, `PO`, `PW`, `CA`, `$MYSQL`, `$SSL`) |
| `scripts/common/setup-loadgen.sh` | Copies the Python tools and the CH query set into `loadgen:/work` |
| `scripts/common/inpod.sh` | Runs any test script below inside `loadgen`, detached, with an Instance's env |
| `scripts/common/wait.sh` | Prints an Instance's phase changes until it reaches a phase |
| `scripts/common/probe.py` | Write probe: one insert every 100 ms on its own connection, then checks every acknowledged write is in the table |
| `scripts/common/verify_probe.py` | Re-checks a probe's acknowledged writes later |
| `scripts/startup/` | Start-up timings: `runttr.sh` creates an Instance, `sqlpoll.py` records when SQL first works, `ttr.py` collects per-pod timings from pod conditions and events |
| `scripts/htap/` | TPC-C and CH-benCHmark data, TiFlash replicas (`tiflash-setup.sql`), the CH runs with analytics on TiKV, on TiFlash and on the optimizer's choice, single-query timings (`power.py`, 22 queries in `ch-queries.json`) and freshness (`freshness.py`) |
| `scripts/scale/scale-tpcc.sh` | 64 TPC-C clients for 90 min while scaling TiKV and TiDB |
| `scripts/ops/` | 32 TPC-C clients and the probe while losing a TiKV pod and taking a backup |
| `scripts/upgrade/` | 50-warehouse data; the upgrade through TiProxy (`proxy-*.sh`, change the version by hand at 5 min); `runupg.sh` for the upgrade with clients straight to TiDB |
| `scripts/tls/runtls.sh` | Alternating 10-min TPC-C runs (64 clients) on a cluster with and one without TLS |
| `results/` | Raw outputs of the runs in the post, one folder per section (below) |

The chart data in the post (`ttr.json`, `htap.json`, `timeline.json`) is next to the post itself.

## Run it

You need a Kubernetes cluster with OpenEverest and provider-tidb installed (see the post), `kubectl`,
and Python 3 on your machine. Every script uses the `tidb` namespace; set `NS` to change it. `gen.py`
puts the data volumes on the `STORAGE_CLASS` StorageClass (the cluster default if unset); pick one
with reclaim policy `Delete`, or deleted clusters leave their volumes behind.

```bash
kubectl create namespace tidb
manifests/prepare-nodes.sh <db-node-1> ... <db-node-6>
kubectl apply -f manifests/prepull.yaml          # wait until all pods are Running, then delete it
kubectl apply -f manifests/loadgen.yaml          # after setting the node in it
scripts/common/setup-loadgen.sh
```

**Start-up timings.** Each run creates an Instance, times it and deletes it again:

```bash
scripts/startup/runttr.sh tidb-standard ttr-std std-1 "Standard" standard
scripts/startup/runttr.sh tidb-analytics ttr-ana ana-1 "Analytics" analytics
```

**HTAP, scaling and day-2.** One `tidb-analytics` cluster with 100 warehouses:

```bash
python3 scripts/common/gen.py tidb-analytics htap | kubectl apply -f -
scripts/common/wait.sh htap Ready 900
scripts/common/env.sh htap
scripts/common/inpod.sh htap scripts/htap/tpcc-prepare.sh     # each step: wait for __EXIT=0 in its log
scripts/common/inpod.sh htap scripts/htap/ch-prepare.sh
kubectl -n tidb exec -i loadgen -- bash -c '. /work/htap.env; $MYSQL -D tpcc' < scripts/htap/tiflash-setup.sql
scripts/common/inpod.sh htap scripts/htap/tpcc-only.sh
scripts/common/inpod.sh htap scripts/htap/ch-tikv.sh          # then ch-tiflash.sh, ch-auto.sh
scripts/common/inpod.sh htap scripts/htap/power-tikv.sh       # then power-tiflash.sh
scripts/common/inpod.sh htap scripts/htap/fresh-idle.sh
scripts/common/inpod.sh htap scripts/scale/scale-tpcc.sh      # patch spec.components.*.replicas while it runs
scripts/common/inpod.sh htap scripts/ops/ops-tpcc.sh          # and ops-probe.sh next to it
```

Logs are in `loadgen:/work/<script>-<instance>.log`; `kubectl -n tidb exec loadgen -- tail -f <log>`.

**Upgrade.** A `tidb-standard` cluster on 7.5.5 with 50 warehouses. Through TiProxy, run `proxy-tpcc.sh`
and `proxy-probe.sh` and change `spec.version` to `8.5.2` five minutes in. Straight to TiDB, create the
cluster without TiProxy and let `runupg.sh` do it all:

```bash
python3 scripts/common/gen.py tidb-standard upg-direct --drop tiproxy --version 7.5.5 | kubectl apply -f -
scripts/common/wait.sh upg-direct Ready 900 && scripts/common/env.sh upg-direct
scripts/common/inpod.sh upg-direct scripts/upgrade/tpcc-prepare.sh
scripts/upgrade/runupg.sh upg-direct
```

**TLS.** Two `tidb-standard` clusters, one with `--no-tls`, 50 warehouses each:

```bash
python3 scripts/common/gen.py tidb-standard tls-on | kubectl apply -f -
python3 scripts/common/gen.py tidb-standard tls-off --no-tls | kubectl apply -f -
# wait, env.sh and upgrade/tpcc-prepare.sh for both, then:
scripts/tls/runtls.sh tls-off:1 tls-on:1 tls-off:2 tls-on:2 tls-off:3 tls-on:3
```

The six database nodes fit two `tidb-standard` clusters at a time, not three.

## Results

| Section of the post | Files |
|---|---|
| How long it takes | `startup/ttr-runs.jsonl`: 3 `tidb-standard` and 2 `tidb-analytics` start-ups on provider-tidb 0.2.2, per-pod timings in seconds since the `Instance` was created (`s` scheduled, `a` volume attached, `p` image ready, `r` ready, `x` restarts) |
| HTAP | `htap/tpcc-only.log`, `ch-tikv.log`, `ch-tiflash.log`, `ch-auto.log` (go-tpc output); `power-*.json` (single-query timings); `fresh-*.json` (freshness); `ch-tiflash-16gib-oom.log` is the run with the old 16 GiB TiFlash preset |
| Scaling out and in | `scale/scale-tiproxy-tpcc.log`; `scale-0.2.0-no-tiproxy-tpcc.log` is the run without TiProxy |
| Losing a TiKV pod, backups | `ops/ops-tpcc.log`, `probe-ops.jsonl` (every probe write: time, latency, error) |
| Rolling upgrade | `upgrade/upg-proxy/` (through TiProxy) and `upgrade/upg-direct/` (straight to TiDB): go-tpc output, every probe write, and for the direct run the Instance, pods and events (`meta` has the start time and when the version changed; `series.json` is what the chart uses) |
| What TLS costs | `tls/tls-{on,off}-run{1,2,3}.log`, `meta` (order and timings), `tls-summary.json`; `2026-10-26-single-runs/` are the first single runs, which agree |

The start-up, direct-upgrade and TLS results are from 27 October 2026 on provider-tidb 0.2.2. The
others are from 26 October, on the fixes from provider-tidb #69–#75 (`*-0.2.0-*` files on 0.2.0); the
later fixes in 0.2.2 only change TiKV below 8 GiB of memory, volumes below 100 GiB and PD start-up,
none of which those runs used. The per-node TiKV data and per-pod TiDB
queries in the scaling chart, and the Raft leaders in the node-loss chart, came from Prometheus
range queries, which are not included here.
