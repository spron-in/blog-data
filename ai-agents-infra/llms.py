import os
from crewai import LLM

llm = LLM(model=os.getenv("MODEL_NAME", "gemini/gemini-2.0-flash"),
          api_key=os.getenv("LLM_API_KEY"),
          temperature=os.getenv("LLM_TEMPERATURE", 0.5),
          verbose=False)