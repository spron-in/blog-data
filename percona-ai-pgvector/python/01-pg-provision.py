import psycopg2
from pgvector.psycopg2 import register_vector
import config
conn = psycopg2.connect(
    user=config.PGUSER,
    password=config.PGPASSWORD,
    database=config.PGDATABASE,
    host=config.PGHOST,
    port=config.PGPORT,
)
cur = conn.cursor()
cur.execute("SET search_path TO " + 'test')
conn.commit()

cur.execute("""
  create table perconavec (
    id bigserial primary key,
    content text,
    url text,
    embedding vector(1024)
  );
""")
conn.commit()

cur.execute("""
   create or replace function match_documents (
      query_embedding vector(1024),
      match_threshold float,
      match_count int
    )
    returns table (
      id bigint,
      content text,
      url text,
      similarity float
    )
    language sql stable
     as $$
    select
      perconavec.id,
      perconavec.content,
      perconavec.url,
      1 - (perconavec.embedding <=> query_embedding) as similarity
    from perconavec
    where
      perconavec.embedding <=> query_embedding < 1 - match_threshold
      order by perconavec.embedding <=> query_embedding
    limit match_count;
    $$;
""")
conn.commit()

cur.execute("""
    create index on perconavec using ivfflat (embedding vector_cosine_ops)
    with
      (lists = 100);
""")
conn.commit()

cur.close()
conn.close()
