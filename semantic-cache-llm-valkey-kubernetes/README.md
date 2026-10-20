# Semantic caching for LLMs on Kubernetes

Code, manifests and raw results for the blog post
[Semantic Caching for LLMs on Kubernetes: Faster, Cheaper, and Sometimes Wrong](https://solanica.io/blog/semantic-cache-llm-valkey-kubernetes/).

A RAG service over the Valkey documentation (Milvus + Qwen2.5-7B on vLLM) with a Valkey
semantic cache (valkey-search) in front of the LLM. Every database and model is an
[OpenEverest](https://openeverest.io) Instance.

## Layout

| Path | What it is |
|---|---|
| `manifests/vk-quota.yaml` | `ai-demo` namespace and the Valkey Instance that stores the gateway's token-quota counters (TLS off) |
| `manifests/kserve-ratelimit-values.yaml` | provider-kserve Helm values that point the Envoy rate limiter at `vk-quota` |
| `manifests/instances.yaml` | `milvus-docs`, `vk-cache` (Valkey + search module), `minilm` (embeddings) and `qwen-7b` (LLM) |
| `manifests/bge-base.yaml` | Second embedding model, used only for the threshold comparison |
| `manifests/lab.yaml` | Python pod with every Instance's connection Secret mounted under `/conn/<name>`; scripts run here |
| `manifests/rag-app.yaml` | Deployment, Service and PodMonitor for the app |
| `app/app.py` | The service: `POST /ask` (embed → cache lookup → Milvus → LLM → cache write), `POST /reset`, `/metrics` |
| `scripts/ingest.py` | Downloads `valkey-doc`, chunks `topics/*.md`, embeds through the gateway, loads Milvus |
| `scripts/genq.py` | Has Qwen write a question, 3 rewordings and a near-miss for 60 doc chunks → `questions.json` |
| `scripts/evalthr.py` | Threshold study: caches one question per group, measures distances of rewordings and near-misses → `eval-<model>.json` |
| `scripts/loadgen.py` | Replays the question bank with Zipf popularity against `/ask` → `run-*.json` |
| `scripts/scaletest.py` | Fills a Valkey index with 10k-200k synthetic entries; reports memory and KNN latency |
| `scripts/analyze.py` | Summary table of all runs and threshold studies |
| `scripts/blogbuild.py` | Builds the post's chart (`cache-hits-by-threshold.svg`) and widget data (`threshold-study.json`) |
| `results/` | Raw outputs from the runs in the post, plus `prometheus/` range-query exports (5s step) |

## Prerequisites

- OpenEverest 2.0 with provider-valkey ≥ 0.1.9, provider-milvus ≥ 0.3.1 and provider-kserve ≥ 0.4.1,
  the AI Gateway enabled over HTTPS, and a GPU node for the LLM. See
  [Model-as-a-Service with OpenEverest](https://solanica.io/blog/model-as-a-service-with-openeverest/).
- Prometheus Operator, if you want the app's metrics.
- Storage classes and node placement are left to cluster defaults; add yours to the manifests.

## Run it

```bash
# 1. Quota store, then point the gateway's rate limiter at it
kubectl apply -f manifests/vk-quota.yaml
kubectl -n provider-kserve create secret generic ai-gateway-ratelimit-redis \
  --from-literal=password="$(kubectl -n ai-demo get secret vk-quota-conn -o jsonpath='{.data.password}' | base64 -d)"
helm upgrade provider-kserve oci://ghcr.io/openeverest/charts/provider-kserve -n provider-kserve \
  --reuse-values -f manifests/kserve-ratelimit-values.yaml

# 2. Documents, cache and models (wait for all to be Ready)
kubectl apply -f manifests/instances.yaml
kubectl apply -f manifests/bge-base.yaml   # optional, threshold comparison only
kubectl -n ai-demo get instances

# 3. Lab pod and scripts
kubectl apply -f manifests/lab.yaml
kubectl -n ai-demo wait --for=condition=Ready pod/lab --timeout=300s
kubectl cp scripts ai-demo/lab:/work/scripts
kubectl -n ai-demo exec lab -- python /work/scripts/ingest.py
kubectl -n ai-demo exec lab -- sh -c 'cd /work && python scripts/genq.py'   # writes /work/questions.json

# 4. The app
kubectl -n ai-demo create configmap rag-app --from-file=app/app.py
kubectl apply -f manifests/rag-app.yaml

# 5. Experiments (run long ones detached; the output lands in /work)
kubectl -n ai-demo exec lab -- python /work/scripts/evalthr.py minilm
kubectl -n ai-demo exec lab -- python /work/scripts/evalthr.py bge-base
kubectl -n ai-demo exec lab -- python /work/scripts/loadgen.py --no-cache --requests 300 --out /work/run-nocache.json
kubectl -n ai-demo exec lab -- python /work/scripts/loadgen.py --threshold 0.15 --out /work/run-t0.15.json
kubectl -n ai-demo exec lab -- python /work/scripts/scaletest.py   # flushes vk-cache
kubectl -n ai-demo exec lab -- python /work/scripts/analyze.py /work
```

`loadgen.py` calls `/reset` (FLUSHALL on `vk-cache`) before each cached run, so every run starts empty.
Ask a single question with:

```bash
kubectl -n ai-demo exec lab -- python -c "import httpx; print(httpx.post('http://rag-app:8000/ask', json={'question': 'How do I enable AOF?'}, timeout=120).json())"
```

## Rebuild the post's chart and widget data

```bash
python3 scripts/blogbuild.py results <solanicaio.github.io>/content/blog/semantic-cache-llm-valkey-kubernetes
```

## Notes

- The predictor topology defaults to 1,000 tokens per API key per hour; `instances.yaml` raises
  it so ingestion and load tests aren't rate limited.
- Batched embedding requests need provider-kserve with the larger gateway buffer
  ([provider-kserve#105](https://github.com/openeverest/provider-kserve/pull/105)); on older
  versions use smaller batches in `ingest.py`.
- Cleanup: `kubectl delete instance --all -n ai-demo`, then `kubectl delete ns ai-demo`.
  Before [provider-valkey#26](https://github.com/openeverest/provider-valkey/pull/26), Valkey
  volumes are kept after the Instance is deleted; delete the `valkey-*-data` PVCs yourself.
