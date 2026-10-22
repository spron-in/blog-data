# OpenJev on KServe and OpenEverest

Artifacts for the blog post *A System 1 for Your Platform: OpenJev on KServe and OpenEverest*.

[OpenJev](https://huggingface.co/openjev/openjev) is an open-weights decision model: a typed question
in, a calibrated probability for every option out, one forward pass per question. Here
OpenJev Flash 9B (FP8) runs as an OpenEverest `Instance` through
[provider-kserve](https://github.com/openeverest/provider-kserve): vLLM as a custom container on
the GPU and OpenJev's helper (`shim.py`) as the `transformer-container` sidecar.

## Environment

* Akamai (Linode) LKE, Kubernetes 1.36: 3 × `g8-dedicated-16-8`, 1 × `g2-gpu-rtx4000a1-m` (RTX 4000 Ada, 20 GB, $0.67/h)
* OpenEverest v2.0.0-dev.4, cert-manager (jetstack chart), provider-kserve 0.4.2 (KServe 0.21) for the experiments
* The Envoy AI Gateway part: provider-kserve with `apiSchema: TypeSafe` support
  ([openeverest/provider-kserve](https://github.com/openeverest/provider-kserve), 0.4.3 or later), bundled
  Envoy Gateway v1.9.2 and Envoy AI Gateway v1.2.0, a self-signed certificate, Valkey as the rate-limit backend
* vLLM 0.29.0, `openjev/OpenJev-Flash-9B-FP8` at revision `ceda5115`, helper sha256 `81a22f1b…`

## Layout

| Path | What it is |
|---|---|
| `manifests/namespace.yaml` | `decisions` namespace and the PVC that caches Hugging Face downloads |
| `manifests/openjev.yaml` | The OpenJev `Instance`: vLLM + helper sidecar, pinned model revision and helper hash, published on the Envoy AI Gateway with `apiSchema: TypeSafe`; the gateway authenticates to the helper with the `openjev-shim` Secret (`backendAPIKeySecret`) |
| `manifests/provider-values.yaml` | provider-kserve Helm values: Envoy Gateway + AI Gateway, TLS, the rate-limit backend |
| `manifests/gateway-prereqs.yaml` | Self-signed `ClusterIssuer` and a minimal Valkey for token quotas, plus the cert-manager and CRD steps |
| `manifests/networkpolicy.yaml` | Only the helper port (3000) is reachable from other pods; vLLM (8080) stays private |
| `manifests/lab.yaml` | In-cluster Python pod with the Instance's connection Secret and the helper key mounted; used for the benchmarks and the issue triage (direct to the helper, `OPENJEV_URL`) |
| `manifests/incidents.yaml` | 12 deliberately broken workloads (+1 healthy control); the true cause is the `incident/cause` label on each Deployment |
| `manifests/incidents-heldout.yaml` | 7 more incidents, written after the v2 question text, to check it generalises |
| `scripts/openjev.py` | Minimal `/v1/systemone` client: direct to the helper (`OPENJEV_URL`) or through the gateway (connection Secret) |
| `scripts/gateway_e2e.sh` | Through the public Envoy AI Gateway: 401 without a key, 403 for another model, 200 with typed answers |
| `scripts/gateway_quota.sh` | Sets `tokenLimitPerHour`, repeats a decision until the gateway answers 429, removes the limit |
| `scripts/via-gateway-portforward.sh` | Runs a command against a port-forward of the gateway Service, for networks that cannot reach the LoadBalancer |
| `scripts/smoke.sh` | Port-forward, check 401 without a token, `/v1/version`, the model card's three-question request |
| `scripts/with-openjev.sh` | Run any local command with a port-forward and `OPENJEV_URL` / `OPENJEV_TOKEN` set |
| `scripts/bench.py` | Latency (short, cold/warm 1k and 4k states), throughput at concurrency 1–16, and `fanout` (1–16 questions per state) |
| `scripts/prepare_issues.py` | Builds `data/issues.jsonl`: 100 bug / 100 feature / 99 question issues from kserve/kserve with issue-template text removed |
| `scripts/triage_eval.py` | Runs the issue triage with criteria `--policy v0|v1|v2` |
| `scripts/analyze_triage.py` | Accuracy, confusion matrix, threshold curve, calibration, confident disagreements |
| `scripts/incident_triage.py` | Builds the state from `kubectl describe pod` + logs and asks five questions per pod (`--policy v1|v2`) |
| `scripts/triage_bot.py` | GitHub triage bot that uses the repository's own label descriptions as criteria; dry run unless `--apply` |
| `scripts/blog_widgets.py` | Compacts results into the data embedded in the post's interactive widgets |
| `data/` | Raw `gh issue list` exports and the cleaned `issues.jsonl` |
| `results/` | Raw outputs (`*.jsonl`) and printed reports (`*.txt`) of every run in the post; `gateway-e2e-0.4.3.txt` re-runs the gateway check on the released provider-kserve 0.4.3 |

## Reproduce

```bash
# Platform (OpenEverest v2 already installed): cert-manager with Gateway API support,
# the gateway CRDs, the issuer and the rate-limit Valkey, then the provider.
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true \
  --set config.apiVersion=controller.config.cert-manager.io/v1alpha1 \
  --set config.kind=ControllerConfiguration --set config.enableGatewayAPI=true --wait
helm template eg oci://docker.io/envoyproxy/gateway-crds-helm --version v1.9.2 \
  --set crds.gatewayAPI.enabled=true --set crds.envoyGateway.enabled=true \
  | kubectl apply --server-side --force-conflicts -f -
kubectl apply -f manifests/gateway-prereqs.yaml
# With your own domain, pass it as aiGateway.tls.hostname right away. On LKE without one,
# install with a placeholder, then switch to the LoadBalancer's DNS name:
helm install provider-kserve oci://ghcr.io/openeverest/charts/provider-kserve -n everest-system \
  -f manifests/provider-values.yaml --set aiGateway.tls.hostname=pending.invalid --wait
helm upgrade provider-kserve oci://ghcr.io/openeverest/charts/provider-kserve -n everest-system \
  --reuse-values --set aiGateway.tls.hostname=$(kubectl -n everest-system get svc \
      -l gateway.envoyproxy.io/owning-gateway-name=provider-kserve-ai-gateway \
      -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}') --wait

# OpenJev, published on the gateway
kubectl apply -f manifests/namespace.yaml
kubectl -n decisions create secret generic openjev-shim --from-literal=apiKey="$(openssl rand -hex 24)"
kubectl apply -f manifests/openjev.yaml -f manifests/networkpolicy.yaml
kubectl -n decisions wait pod -l serving.kserve.io/inferenceservice=openjev --for=condition=Ready --timeout=15m
./scripts/smoke.sh                      # direct to the helper through a port-forward
./scripts/gateway_e2e.sh                # through the public gateway
./scripts/gateway_quota.sh

# Benchmarks and issue triage, from inside the cluster
kubectl apply -f manifests/lab.yaml
kubectl -n decisions wait pod/lab --for=condition=Ready
kubectl -n decisions cp scripts lab:/work/scripts && kubectl -n decisions cp data lab:/work/data
kubectl -n decisions exec lab -- python scripts/bench.py
kubectl -n decisions exec lab -- python scripts/bench.py fanout
kubectl -n decisions exec lab -- python scripts/triage_eval.py --policy v1   # also v0, v2
kubectl -n decisions cp lab:/work/results results
python3 scripts/analyze_triage.py

# Incidents (run locally, needs kubectl and `pip install httpx`)
kubectl apply -f manifests/incidents.yaml -f manifests/incidents-heldout.yaml   # wait ~3 minutes
./scripts/with-openjev.sh python3 scripts/incident_triage.py --policy v1 --out results/incidents-all-v1.jsonl
./scripts/with-openjev.sh python3 scripts/incident_triage.py --policy v2 --out results/incidents-all-v2.jsonl

# Triage bot, dry run
./scripts/with-openjev.sh python3 scripts/triage_bot.py --repo openeverest/openeverest --label needs-triage --limit 30
```

## Results at a glance

| | |
|---|---|
| `apply` → first answer | 5 min 51 s (28 s volume, 1m36s image, 1m35s weights, 2m11s engine init) |
| Short decision | 67 ms p50 |
| 1k-token state: first read / new question on cached state | 471 ms / 70 ms |
| 4k-token state: first read / new question on cached state | 1,653 ms / 204 ms |
| Fresh 1k-token decisions, any concurrency | 2.1–2.4 per second |
| KServe issue kind, 299 issues, zero-shot | 79.3%; at p ≥ 0.90: 53% coverage, 91.2% accuracy |
| Criteria v0 / v1 / v2 on held-out 200 | 75.0% / 78.0% / 73.5% |
| Incidents, 19 pods | v1 17/19 (both misses: healthy pods with a start-up probe blip), v2 19/19 |
| Envoy AI Gateway | 401 without a key, 403 for another model, 200 with typed answers; tokens metered per key; 429 after 717 of 600 tokens; +4 ms p50 (68 → 72 ms) |

Node public IPs in captured logs are replaced with `203.0.113.10`.

OpenJev weights are CC BY-NC 4.0 (non-commercial); the helper and serving files are Apache 2.0.
