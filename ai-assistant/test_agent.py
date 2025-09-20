import argparse
import requests
import json

def call_ai_agent(agent_access_id, message, token=None):
    """
    Calls the AI agent API with a given message.

    Args:
        agent_access_id (str): The access ID of the agent.
        message (str): The message to send to the agent.
        token (str, optional): The Bearer token for authorization.
    """
    url = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_access_id}/call"
    
    headers = {
        'Content-Type': 'application/json'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
        
    data = {
        'message': message,
        'parent_message_id': ''  # Keep this empty as it's optional for a new conversation
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
        
        # Parse the JSON response
        response_data = response.json()
        
        print("Response from AI Agent:")
        # Use ensure_ascii=False to decode Unicode characters properly
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        
    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error: {err}")
        print(f"Response Body: {response.text}")
    except requests.exceptions.RequestException as err:
        print(f"An error occurred: {err}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Call an AI agent with a message.")
    parser.add_argument("message", type=str, help="The message to send to the AI agent.")
    parser.add_argument("--agent_access_id", type=str, required=True, help="The access ID of the AI agent.")
    parser.add_argument("--token", type=str, help="The optional Bearer token for authorization.")
    
    args = parser.parse_args()

    call_ai_agent(args.agent_access_id, args.message, args.token)
