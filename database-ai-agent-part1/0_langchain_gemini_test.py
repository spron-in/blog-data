import getpass
import os
from langchain_google_genai import ChatGoogleGenerativeAI

if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Provide your Google API Key")

llm = ChatGoogleGenerativeAI(model="gemini-pro")
result = llm.invoke("What can you tell me about Percona?")
print(result.content)
