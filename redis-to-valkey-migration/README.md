# Redis → Valkey migration on Kubernetes

Data and tooling behind the Solanica blog post *Migrating Redis to Valkey on
Kubernetes: 50 GiB and 150 Million Keys, Zero Mismatches*.

Two migrations with the `redis-shake` engine of the OpenEverest
[migrations plugin](https://github.com/openeverest/plugin-migrations), from a
Redis 7.2.17 cluster (3 primaries) into an OpenEverest Valkey 9.0.6 instance
(3 shards), while a client wrote 2,000 changes/s to the source:

| Run | Dataset | Keys verified | Missing / different |
| --- | --- | --- | --- |
| A (`redis-50g`) | 50.2 GiB, 47.0M keys: sessions, hashes, lists, sets, counters, 20 × 1M-member sorted sets, 200 streams with consumer groups | 47,014,200 | 0 / 0 |
| B (`redis-150m`) | 20.5 GiB, 150M small strings | 150,316,491 | 0 / 0 |

## Layout

- `manifests/`: the Redis source (StatefulSet, cluster mode, default save
  points), the OpenEverest Valkey `Instance`, the tools pod, and the Helm
  values used for the plugin.
- `vktool/`: one Go binary with the load generators (`load-a`, `load-b`), the
  application writer (`writer`), the key-by-key verifier (`verify`), and the
  metrics poller (`poll`).
- `scripts/`: `run.sh` drives a run (writer + poller, create, cutover,
  verify) through the plugin API (`api.sh`); `make_charts.py` draws the charts.
- `results/`: per-run 5-second metrics (`*-metrics.csv`), event timestamps
  (`*.events`), verifier summaries (`*-verify.json`), writer logs, worker
  CPU/memory/disk (`worker-stats.csv`), and the SVG charts.

## Reproduce

```bash
# Source Redis cluster, then create the cluster from the pod IPs.
kubectl apply -f manifests/redis-source.yaml
IPS=$(kubectl -n redis-legacy get pods -l app=redis-source -o jsonpath='{range .items[*]}{.status.podIP}:6379 {end}')
kubectl -n redis-legacy exec redis-0 -- sh -c "redis-cli -a \$PW --no-auth-warning --cluster create $IPS --cluster-replicas 0 --cluster-yes"

# Target (needs OpenEverest with provider-valkey) and the plugin.
kubectl apply -f manifests/valkey-target.yaml
helm upgrade --install plugin-migrations-valkey <plugin-migrations>/charts/plugin-migrations \
  -n plugin-migrations-valkey --create-namespace -f manifests/plugin-migrations-values.yaml

# Tools pod (copy the src/dst Secrets into vk-bench first, see run notes below).
kubectl apply -f manifests/tools.yaml
(cd vktool && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o vktool .)
kubectl cp vktool/vktool vk-bench/tools:/work/vktool

# Load dataset A (or: load-b -count 150000000).
kubectl exec -n vk-bench tools -- /work/vktool load-a \
  -addr redis-0.redis.redis-legacy.svc.cluster.local:6379 -target-gb 50

# One run: writer + poller, create, wait for "replicating", cutover, verify.
scripts/run.sh start-bg redis-50g a
scripts/run.sh create redis-50g
scripts/run.sh worker-url redis-50g
scripts/run.sh status x
scripts/run.sh stop-writer redis-50g && scripts/run.sh cutover redis-50g
scripts/run.sh stop-poll redis-50g && scripts/run.sh verify redis-50g
```

Run notes:

- `api.sh` talks to the Everest API on `localhost:18080` and the plugin on
  `localhost:18081` (port-forward both). It logs in as `admin` with the
  initial password from the `everest-accounts` Secret.
- The tools pod expects Secrets `src` (key `password`, from `redis-auth`) and
  `dst` (a copy of the instance's `<name>-conn` Secret) in `vk-bench`.
- The verifier compares type, full value in canonical form (sorted hash
  fields and set members, sorted-set scores, stream entries plus consumer
  group pending count and last delivered ID), and `PEXPIRETIME`. Keys that
  expire within 60 s are skipped.
- `DBSIZE` is not a reliable comparison: Redis frees expired keys lazily, and
  with millions of long-TTL keys short-lived keys can stay counted long after
  they expire.
