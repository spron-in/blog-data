from sentence_transformers import SentenceTransformer
model = SentenceTransformer('WhereIsAI/UAE-Large-V1')
from transformers import pipeline, AutoTokenizer, AutoConfig, AutoModelForQuestionAnswering
import sys
import config
import torch

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

cur.callproc('match_documents', (embeddings[0], 0.5, 50))

row = cur.fetchone()
documents = []
while row is not None: 
    print(row[3],row[2])
    documents.append(row[1])
    row = cur.fetchone()

cur.close()
conn.close()

def generate_response(context, query, model_name):



	# Encode context and query
	context = f"""
	You are a database expert. Given the following sections from 
	Percona blog posts and documentation answer the question. If you can't find the answer - say that you don't know
	{context}
	"""
	
	QA_input = {
		'question': query,
		'context': context
	}
	"""
	model = AutoModelForQuestionAnswering.from_pretrained(model_name)
	tokenizer = AutoTokenizer.from_pretrained(model_name)

	inputs = tokenizer.encode(QA_input['question'], QA_input['context'])
	start_scores, end_scores = model(torch.tensor([inputs]))
	all_tokens = tokenizer.convert_ids_to_tokens(inputs)

	start = torch.argmax(start_scores)
	end = torch.argmax(end_scores)+1
	
	response = ''.join(all_tokens[start:end]).replace('▁',' ').strip()
	"""

	prompt = f"""
	question: {query}
	context: {context}
	"""
#	qa = pipeline('question-answering', model=model_name, tokenizer=model_name, top_k=3)
	qa = pipeline('text2text-generation', do_sample=True, model=model_name, tokenizer=model_name, top_k=3)
	response = qa(prompt)

	return response

# Example usage
query = text[0]
#model_name = "deepset/roberta-base-squad2"
model_name = "google/flan-t5-large"
context = "\n".join(documents)

print(context)
print("#################################### ANSWER BELOW ################################")
response = generate_response(context, query, model_name)
print(response)
