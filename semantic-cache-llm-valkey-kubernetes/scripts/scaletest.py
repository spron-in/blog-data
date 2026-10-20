"""How Valkey memory and KNN latency grow with the number of cached answers."""
import os
import time

import numpy as np
import redis

DIM = 384
INDEX, PREFIX = "scaletest", "st:"


def conn(key):
    return open(f"/conn/vk/{key}").read().strip()


r = redis.Redis(host=conn("host"), port=6379, username=conn("username"), password=conn("password"),
                ssl=True, ssl_ca_certs="/conn/vk/ca.crt")
r.flushall()
time.sleep(1)


def mem():
    return r.info("memory")["used_memory"], r.info("search")["search_used_memory_bytes"]


base_used, base_search = mem()
r.execute_command("FT.CREATE", INDEX, "ON", "HASH", "PREFIX", "1", PREFIX, "SCHEMA",
                  "emb", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(DIM), "DISTANCE_METRIC", "COSINE")
rng = np.random.default_rng(1)
answer = os.urandom(600).hex()[:1000]
question = "x" * 80
print("entries  used_MB  search_MB  bytes/entry  knn_p50_ms  knn_p99_ms  server_p50_us")
n = 0
for target in (10_000, 50_000, 100_000, 200_000):
    while n < target:
        vecs = rng.standard_normal((1000, DIM)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        pipe = r.pipeline(transaction=False)
        for v in vecs:
            pipe.hset(f"{PREFIX}{n}", mapping={"q": question, "a": answer, "g": "g", "emb": v.tobytes()})
            n += 1
        pipe.execute()
    while int(dict(zip(*[iter(r.execute_command("FT.INFO", INDEX))] * 2))[b"num_docs"]) < n:
        time.sleep(0.5)
    lat = []
    for _ in range(300):
        q = rng.standard_normal(DIM).astype(np.float32)
        q /= np.linalg.norm(q)
        t = time.perf_counter()
        r.execute_command("FT.SEARCH", INDEX, "*=>[KNN 1 @emb $v AS dist]", "PARAMS", "2", "v", q.tobytes(),
                          "RETURN", "2", "a", "dist", "DIALECT", "2")
        lat.append(time.perf_counter() - t)
    used, search = mem()
    server = r.info("search")["search_hnsw_vector_index_search_latency_usec"]["p50"]
    print(f"{n:7d} {(used - base_used) / 2**20:8.0f} {(search - base_search) / 2**20:10.0f} "
          f"{(used - base_used) / n:12.0f} {np.percentile(lat, 50) * 1000:11.2f} {np.percentile(lat, 99) * 1000:11.2f} {server:14}")

r.flushall()
