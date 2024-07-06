import getpass
import os
import sys

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent


if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Provide your Google API Key")

dbname="pagila"
username=os.environ["PG_USERNAME"]
password=os.environ["PG_PASSWORD"]
hostname="localhost"
port="5432"

postgres_uri = f"postgresql+psycopg2://{username}:{password}@{hostname}:{port}/{dbname}"

db = SQLDatabase.from_uri(postgres_uri)
prompt = sys.argv[1]

llm = ChatGoogleGenerativeAI(model="gemini-pro")
agent_executor = create_sql_agent(llm, db=db, verbose=True)
response = agent_executor.invoke({"input": prompt})

print(response)
