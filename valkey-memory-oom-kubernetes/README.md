# Valkey memory / OOMKilled test lab (Kubernetes)

Raw material behind the Solanica blog post "Nine Ways to OOM-Kill Valkey on Kubernetes (So You
Don't Have To)". Everything here was run against a live 6-node managed Kubernetes cluster using
[OpenEverest](https://openeverest.io) `Instance` custom resources for Valkey (provider-valkey +
valkey-operator).

## Layout

- `manifests/` - the `Instance` YAML for each of the 9 scenarios, plus the shell-based load
  generators (`loadgen.sh`, `test5_6_loadgen.sh`, `test7_loadgen.sh`) that drove traffic and
  polled `INFO`/pod status into logs.
- `results/` - one markdown write-up per scenario (or group of scenarios), each with: config,
  method, raw evidence (timestamps, `INFO memory`/`INFO stats` snapshots, `kubectl` output), and
  an explicit "takeaway for the post" section. `00-plan.md` has the original test plan and a
  final summary table.

## Scenarios

1. Default config, no `maxmemory`, no persistence -> fills the container limit, OOMKilled.
2. `maxmemory` == container limit, `noeviction`.
3. `maxmemory` with real headroom, `noeviction`.
4. `allkeys-lru` eviction.
5. `BGSAVE` copy-on-write vs. container limit.
6. `appendonly yes` (AOF) overhead.
7. Replica full resync after a primary OOM kill (data-loss scenario).
8. Fragmentation and `activedefrag`.
9. Kubernetes QoS class (Burstable vs. Guaranteed) vs. node memory pressure.

## Reproducing

Each manifest is a `core.openeverest.io/v1alpha1` `Instance`. Apply one, grab the generated
password from the `<instance-name>-conn` secret, then use the matching loadgen script or
`valkey-benchmark`/`valkey-cli` directly. Note: one important finding from this lab is that
`DEBUG POPULATE` bypasses both the `maxmemory` OOM-deny check and AOF propagation - use real
`valkey-benchmark -t set` traffic (as the scripts do for the corrected runs) if you want results
that reflect real client behavior.
