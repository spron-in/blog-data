"""Offline threshold study: seed one question per group, query paraphrases and near-misses."""
import json
import sys

import httpx
import numpy as np
import redis

EMBEDDER = sys.argv[1] if len(sys.argv) > 1 else "minilm"
INDEX, PREFIX = f"eval_{EMBEDDER}", f"ev:{EMBEDDER}:"


def conn(name, key):
    return open(f"/conn/{name}/{key}").read().strip()


gw = httpx.Client(base_url=conn(EMBEDDER, "uri"), headers={"Authorization": f"Bearer {conn(EMBEDDER, 'password')}"}, timeout=120)
vk = redis.Redis(host=conn("vk", "host"), port=6379, username=conn("vk", "username"), password=conn("vk", "password"),
                 ssl=True, ssl_ca_certs="/conn/vk/ca.crt")


def embed(texts):
    out = []
    for i in range(0, len(texts), 32):
        r = gw.post("/embeddings", json={"model": conn(EMBEDDER, "model"), "input": texts[i:i + 32]})
        r.raise_for_status()
        out += [np.asarray(d["embedding"], dtype=np.float32) for d in r.json()["data"]]
    return out


bank = json.load(open("/work/questions.json"))
base = [g for g in bank if "near_miss_of" not in g]
near = [g for g in bank if "near_miss_of" in g]
seeds = embed([g["variants"][0] for g in base])
dim = len(seeds[0])

try:
    vk.execute_command("FT.DROPINDEX", INDEX)
except redis.ResponseError:
    pass
vk.execute_command("FT.CREATE", INDEX, "ON", "HASH", "PREFIX", "1", PREFIX, "SCHEMA",
                   "emb", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE")
for g, v in zip(base, seeds):
    vk.hset(f"{PREFIX}{g['group']}", mapping={"g": g["group"], "emb": v.tobytes()})


def nearest(v):
    r = vk.execute_command("FT.SEARCH", INDEX, "*=>[KNN 1 @emb $v AS dist]", "PARAMS", "2", "v", v.tobytes(),
                           "RETURN", "2", "g", "dist", "DIALECT", "2")
    f = dict(zip(r[2][::2], r[2][1::2]))
    return f[b"g"].decode(), float(f[b"dist"])


rows = []
para = [(g["group"], q) for g in base for q in g["variants"][1:]]
for (group, q), v in zip(para, embed([q for _, q in para])):
    ng, d = nearest(v)
    rows.append({"kind": "paraphrase", "group": group, "q": q, "nearest": ng, "dist": d})
for g, v in zip(near, embed([g["variants"][0] for g in near])):
    ng, d = nearest(v)
    rows.append({"kind": "near_miss", "group": g["group"], "of": g["near_miss_of"], "q": g["variants"][0], "nearest": ng, "dist": d})

json.dump(rows, open(f"/work/eval-{EMBEDDER}.json", "w"), indent=1)
print(f"{EMBEDDER}: dim {dim}")
print("thr   para_hit  para_wrong  nearmiss_hit")
for t in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5):
    p = [r for r in rows if r["kind"] == "paraphrase"]
    n = [r for r in rows if r["kind"] == "near_miss"]
    hit = sum(r["dist"] <= t and r["nearest"] == r["group"] for r in p) / len(p)
    wrong = sum(r["dist"] <= t and r["nearest"] != r["group"] for r in p) / len(p)
    nm = sum(r["dist"] <= t for r in n) / len(n)
    print(f"{t:<5} {hit:8.1%} {wrong:10.1%} {nm:12.1%}")
for k in ("paraphrase", "near_miss"):
    d = np.array([r["dist"] for r in rows if r["kind"] == k])
    print(k, "dist p10/p50/p90:", np.round(np.percentile(d, [10, 50, 90]), 3))
