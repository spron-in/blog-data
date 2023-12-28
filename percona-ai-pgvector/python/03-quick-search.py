from sentence_transformers import SentenceTransformer
model = SentenceTransformer('WhereIsAI/UAE-Large-V1')
import sys
import config

def create_embedding(content):
    embeddings = model.encode(content, device='cuda', show_progress_bar=True)
    return(embeddings)

text = [sys.argv[1]]
embeddings = create_embedding(text)

import psycopg2
from pgvector.psycopg2 import register_vector
conn = psycopg2.connect(
    user=config.PGUSER,
    password=config.PGPASSWORD,
    database=config.PGDATABASE,
    host=config.PGHOST,
    port=config.PGPORT,
)
cur = conn.cursor()
cur.execute("SET search_path TO " + 'test')
register_vector(conn)

cur.callproc('match_documents', (embeddings[0], 0, 5))

row = cur.fetchone()
while row is not None: 
    print(row[3],row[2])
    row = cur.fetchone()

cur.close()
conn.close()
