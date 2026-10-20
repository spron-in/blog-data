"""Build the question bank: per doc chunk, a question, paraphrases and a near-miss."""
import asyncio
import json
import random

import httpx
from pymilvus import MilvusClient

COLLECTION = "valkey_docs"
SAMPLES = 60
PROMPT = """Here is an excerpt from the Valkey documentation:

<excerpt>
{text}
</excerpt>

Write JSON with these keys:
- "question": a question a developer would ask that this excerpt answers.
- "paraphrases": 3 rewordings of that same question, varied in wording and length, same meaning.
- "near_miss": a question that reuses much of the same vocabulary but asks for something different,
  so the answer to "question" would be wrong for it.
Return only the JSON object."""


def conn(name, key):
    return open(f"/conn/{name}/{key}").read().strip()


async def generate(client, sem, chunk):
    async with sem:
        resp = await client.post("/chat/completions", json={
            "model": conn("qwen", "model"),
            "messages": [{"role": "user", "content": PROMPT.format(text=chunk["text"][:2500])}],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "max_tokens": 400,
        })
        resp.raise_for_status()
        item = json.loads(resp.json()["choices"][0]["message"]["content"])
        item["source"] = chunk["source"]
        return item


async def main():
    milvus = MilvusClient(uri=conn("milvus", "uri"), token=conn("milvus", "token"))
    chunks = milvus.query(COLLECTION, filter="id > 0", output_fields=["source", "text"], limit=16384)
    by_source = {}
    for c in chunks:
        if len(c["text"]) > 400:
            by_source.setdefault(c["source"], []).append(c)
    random.seed(7)
    sources = random.sample(sorted(by_source), min(SAMPLES, len(by_source)))
    picked = [random.choice(by_source[s]) for s in sources]

    client = httpx.AsyncClient(base_url=conn("qwen", "uri"), headers={"Authorization": f"Bearer {conn('qwen', 'password')}"}, timeout=180)
    sem = asyncio.Semaphore(8)
    results = await asyncio.gather(*(generate(client, sem, c) for c in picked), return_exceptions=True)
    bank = []
    for i, item in enumerate(results):
        if isinstance(item, Exception) or not item.get("question") or len(item.get("paraphrases", [])) < 3 or not item.get("near_miss"):
            print("skip", i, item)
            continue
        bank.append({"group": f"g{i}", "source": item["source"], "variants": [item["question"], *item["paraphrases"][:3]]})
        bank.append({"group": f"g{i}n", "source": item["source"], "variants": [item["near_miss"]], "near_miss_of": f"g{i}"})
    json.dump(bank, open("/work/questions.json", "w"), indent=1)
    print(len(bank), "groups")


if __name__ == "__main__":
    asyncio.run(main())
