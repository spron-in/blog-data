"""RAG service with a Valkey semantic cache in front of the LLM."""
import asyncio
import os
import time
import uuid

import httpx
import numpy as np
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel
from pymilvus import MilvusClient

COLLECTION = "valkey_docs"
INDEX = "semcache"
PREFIX = "sc:"
DIM = 384
THRESHOLD = float(os.getenv("CACHE_THRESHOLD", "0.15"))
TTL = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
SYSTEM = ("You answer questions about Valkey using only the provided documentation excerpts. "
          "Be concise: at most 120 words. If the excerpts do not contain the answer, say so.")

REQUESTS = Counter("ask_requests_total", "Answered questions", ["result"])
FALSE_HITS = Counter("ask_false_hits_total", "Cache hits whose cached answer belongs to a different question group")
LATENCY = Histogram("ask_latency_seconds", "End-to-end /ask latency", ["result"],
                    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32))
STAGE = Histogram("ask_stage_seconds", "Latency per pipeline stage", ["stage"],
                  buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32))
TOKENS = Counter("ask_llm_tokens_total", "LLM tokens spent on cache misses", ["kind"])


def conn(name, key):
    return open(f"/conn/{name}/{key}").read().strip()


def gateway(name):
    return httpx.AsyncClient(base_url=conn(name, "uri"), timeout=120,
                             headers={"Authorization": f"Bearer {conn(name, 'password')}"},
                             limits=httpx.Limits(max_connections=64, max_keepalive_connections=64))


valkey = redis.Redis(host=conn("vk", "host"), port=int(conn("vk", "port")), username=conn("vk", "username"),
                     password=conn("vk", "password"), ssl=True, ssl_ca_certs="/conn/vk/ca.crt",
                     max_connections=64)
milvus = MilvusClient(uri=conn("milvus", "uri"), token=conn("milvus", "token"))
embedder = gateway("minilm")
llm = gateway("qwen")
app = FastAPI()
app.mount("/metrics", make_asgi_app())


class Ask(BaseModel):
    question: str
    group: str | None = None
    threshold: float | None = None
    use_cache: bool = True


class timed:
    def __init__(self, stage, timings):
        self.stage, self.timings = stage, timings

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, *exc):
        elapsed = time.perf_counter() - self.start
        STAGE.labels(self.stage).observe(elapsed)
        self.timings[self.stage] = round(elapsed * 1000, 1)


async def ensure_index():
    try:
        await valkey.execute_command("FT.INFO", INDEX)
    except redis.ResponseError:
        await valkey.execute_command(
            "FT.CREATE", INDEX, "ON", "HASH", "PREFIX", "1", PREFIX, "SCHEMA",
            "emb", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(DIM), "DISTANCE_METRIC", "COSINE")


@app.on_event("startup")
async def startup():
    await ensure_index()


async def embed(text):
    resp = await embedder.post("/embeddings", json={"model": conn("minilm", "model"), "input": [text]})
    resp.raise_for_status()
    return np.asarray(resp.json()["data"][0]["embedding"], dtype=np.float32).tobytes()


async def cache_lookup(vector):
    reply = await valkey.execute_command(
        "FT.SEARCH", INDEX, "*=>[KNN 1 @emb $v AS dist]", "PARAMS", "2", "v", vector,
        "RETURN", "3", "a", "g", "dist", "DIALECT", "2")
    if not reply or reply[0] == 0:
        return None
    fields = dict(zip(reply[2][::2], reply[2][1::2]))
    return {"answer": fields[b"a"].decode(), "group": fields.get(b"g", b"").decode(), "dist": float(fields[b"dist"])}


def retrieve(vector):
    hits = milvus.search(COLLECTION, data=[np.frombuffer(vector, dtype=np.float32).tolist()], limit=TOP_K,
                         output_fields=["text", "source"], search_params={"metric_type": "COSINE"})
    return [h["entity"] for h in hits[0]]


async def generate(question, context):
    excerpts = "\n\n---\n\n".join(c["text"] for c in context)
    resp = await llm.post("/chat/completions", json={
        "model": conn("qwen", "model"),
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"Documentation excerpts:\n\n{excerpts}\n\nQuestion: {question}"}],
        "temperature": 0,
        "max_tokens": 256,
    })
    resp.raise_for_status()
    body = resp.json()
    return body["choices"][0]["message"]["content"], body["usage"]


@app.post("/ask")
async def ask(req: Ask):
    start = time.perf_counter()
    timings = {}
    with timed("embed", timings):
        vector = await embed(req.question)

    nearest = None
    if req.use_cache:
        with timed("cache_lookup", timings):
            nearest = await cache_lookup(vector)
        threshold = THRESHOLD if req.threshold is None else req.threshold
        if nearest and nearest["dist"] <= threshold:
            false_hit = bool(req.group and nearest["group"] and nearest["group"] != req.group)
            if false_hit:
                FALSE_HITS.inc()
            REQUESTS.labels("hit").inc()
            LATENCY.labels("hit").observe(time.perf_counter() - start)
            return {"result": "hit", "answer": nearest["answer"], "dist": nearest["dist"],
                    "cached_group": nearest["group"], "false_hit": false_hit, "timings_ms": timings}

    with timed("retrieve", timings):
        context = await asyncio.to_thread(retrieve, vector)
    try:
        with timed("llm", timings):
            answer, usage = await generate(req.question, context)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 429:
            raise
        REQUESTS.labels("quota_exceeded").inc()
        return JSONResponse({"result": "quota_exceeded", "dist": nearest["dist"] if nearest else None},
                            status_code=429, headers={"Retry-After": e.response.headers.get("x-ratelimit-reset", "60")})
    TOKENS.labels("prompt").inc(usage["prompt_tokens"])
    TOKENS.labels("completion").inc(usage["completion_tokens"])

    if req.use_cache:
        with timed("cache_store", timings):
            key = f"{PREFIX}{uuid.uuid4().hex}"
            async with valkey.pipeline(transaction=False) as pipe:
                pipe.hset(key, mapping={"q": req.question, "a": answer, "g": req.group or "", "emb": vector})
                pipe.expire(key, TTL)
                await pipe.execute()

    REQUESTS.labels("miss").inc()
    LATENCY.labels("miss").observe(time.perf_counter() - start)
    return {"result": "miss", "answer": answer, "dist": nearest["dist"] if nearest else None,
            "sources": sorted({c["source"] for c in context}), "usage": usage, "timings_ms": timings}


@app.post("/reset")
async def reset():
    await valkey.flushall()
    await ensure_index()
    return {"ok": True}
