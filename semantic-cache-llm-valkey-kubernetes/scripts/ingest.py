"""Load the Valkey documentation into Milvus as embedded chunks."""
import io
import re
import tarfile

import httpx
from pymilvus import DataType, MilvusClient

DOCS_URL = "https://github.com/valkey-io/valkey-doc/archive/refs/heads/main.tar.gz"
COLLECTION = "valkey_docs"
CHUNK_CHARS = 1200
BATCH = 32


def conn(name, key):
    return open(f"/conn/{name}/{key}").read().strip()


def embed(client, texts):
    resp = client.post("/embeddings", json={"model": conn("minilm", "model"), "input": texts})
    resp.raise_for_status()
    return [d["embedding"] for d in resp.json()["data"]]


def chunks(title, text):
    paragraphs = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        paragraphs.extend(p[i:i + CHUNK_CHARS] for i in range(0, len(p), CHUNK_CHARS))
    current = ""
    for p in paragraphs:
        if current and len(current) + len(p) > CHUNK_CHARS:
            yield f"{title}\n\n{current}"
            current = ""
        current = f"{current}\n\n{p}" if current else p
    if current:
        yield f"{title}\n\n{current}"


def documents():
    raw = httpx.get(DOCS_URL, follow_redirects=True, timeout=120).content
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar.getmembers():
            if re.search(r"/topics/[^/]+\.md$", member.name):
                text = tar.extractfile(member).read().decode()
                title = re.search(r'^title: "?([^"\n]+)', text, re.M)
                body = re.sub(r"^---.*?---\n", "", text, flags=re.S)
                yield member.name.rsplit("/", 1)[1], title.group(1) if title else member.name, body


def main():
    milvus = MilvusClient(uri=conn("milvus", "uri"), token=conn("milvus", "token"))
    if milvus.has_collection(COLLECTION):
        milvus.drop_collection(COLLECTION)
    schema = milvus.create_schema(auto_id=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=384)
    schema.add_field("source", DataType.VARCHAR, max_length=256)
    schema.add_field("text", DataType.VARCHAR, max_length=8192)
    index = milvus.prepare_index_params()
    index.add_index("vector", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200})
    milvus.create_collection(COLLECTION, schema=schema, index_params=index)

    rows = [(source, c) for source, title, body in documents() for c in chunks(title, body)]
    print(f"{len(rows)} chunks")
    gateway = httpx.Client(base_url=conn("minilm", "uri"), headers={"Authorization": f"Bearer {conn('minilm', 'password')}"}, timeout=60)
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        vectors = embed(gateway, [text for _, text in batch])
        milvus.insert(COLLECTION, [{"vector": v, "source": s, "text": t[:8000]} for (s, t), v in zip(batch, vectors)])
    milvus.load_collection(COLLECTION)
    print("loaded", milvus.get_collection_stats(COLLECTION))


if __name__ == "__main__":
    main()
