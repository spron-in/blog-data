import os
from crewai import Crew
from agents import postgresql_reader_agent, linux_admin_agent, digitalocean_agent
from tasks import postgresql_reader_task, linux_admin_task, digitalocean_task
import json
import sys

def process_inquiry_in_crew(assets, inquiry):

    crew = Crew(
                agents=[postgresql_reader_agent, linux_admin_agent, digitalocean_agent],
                tasks=[postgresql_reader_task, linux_admin_task, digitalocean_task],
                verbose=True)
    
    result = crew.kickoff(
                inputs={'user_assets': assets, 'inquiry': inquiry})
    
    print(result.raw)

assets = [
    {
        "name": "mysuperdb",
        "type": "postgresql",
        "host": "MASKED",
        "port": "5432",
        "user": "aiuser",
        "database": "aitestdb",
        "password": "MASKED",
        "metadata": {
            "runs_on": "do_test_server",
        }
    },
    {
        "name": "do_test_server",
        "type": "linux",
        "host": "MASKED",
        "user": "root",
        "base64_ssh_private_key": "MASKED",
        "ssh_private_key_passphrase": "MASKED",
        "metadata": {
            "virtual_machine_type": "Digital Ocean droplet",
            "droplet_name": "test-ai-agents"
        }
    },
    {
        "name": "Digital Ocean Cloud",
        "type": "Digital Ocean API",
        "token": "MASKED"
    }
]

inquiry = sys.argv[1]

process_inquiry_in_crew(assets, inquiry)
