import os
from crewai import Crew
from agents import postgresql_reader_agent
from tasks import postgresql_reader_task
import json
import sys

def process_inquiry_in_crew(assets, inquiry):

    crew = Crew(
                agents=[postgresql_reader_agent],
                tasks=[postgresql_reader_task],
                verbose=True)
    
    result = crew.kickoff(
                inputs={'user_assets': assets, 'inquiry': inquiry})
    
    print(result.raw)

assets = [
    {
        "type": "postgresql",
        "host": "MASKED",
        "port": "5432",
        "user": "aiuser",
        "database": "aitestdb",
        "password": "MASKED"
    }
]

inquiry = sys.argv[1]

process_inquiry_in_crew(assets, inquiry)
