# Database CrashLoopBackOff test lab (PostgreSQL + MySQL on Kubernetes)

Raw material behind the Solanica blog post "CrashLoopBackOff: Why Databases Crash-Loop on
Kubernetes and How to Fix It". Every failure was reproduced on purpose on a local k3d cluster
(Kubernetes v1.37.1) with plain StatefulSets running the official `postgres` and `mysql` images.

## Layout

- `manifests/00-baseline-*.yaml` - known-good PostgreSQL 18 and MySQL 8.4 StatefulSets
  (startupProbe, tolerant liveness probe, fsGroup, Guaranteed QoS).
- `manifests/NN-*.yaml` - one file per test, generated from the baseline by `scripts/gen.py`, so
  each differs from the baseline only by the failure it reproduces (the reason is in the first
  comment line).
- `scripts/crashloop-triage.sh <pod> [ns]` - status, per-container `lastState`, events, and
  `logs --previous` in one go. This is the script used for every diagnosis.
- `scripts/watch-restarts.sh` - polls a pod and logs status/restart changes (backoff timing).
- `results/00-summary.md` - environment, summary table, recurring themes.
- `results/01..06-*.md` - per-group write-ups with the raw evidence.
- `results/raw/` - unedited triage output and logs.

## Groups

1. Config errors (10-12) + measured backoff timing
2. OOMKilled (20-22)
3. Probes (30, 30b, 31)
4. Secrets (40-43)
5. Storage / PVC (50-55)
6. Version changes (60-62)

## Reproducing

```bash
k3d cluster create crashloop-lab --image rancher/k3s:v1.37.1-k3s1 --k3s-arg "--disable=traefik@server:0"
python3 scripts/gen.py                       # regenerate manifests (needs PyYAML)
kubectl create ns t10
kubectl -n t10 apply -f manifests/10-pg-bad-parameter.yaml
scripts/crashloop-triage.sh pg-0 t10
```

Tests 20, 21, 31, 43, 55 and 60-62 need an extra action after the pod is up (load data, rotate
a Secret, change the image, crash the postmaster). The exact steps are in the matching
`results/` file.
