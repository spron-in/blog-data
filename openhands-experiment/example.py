#!/usr/bin/env python3
"""Example usage of the Timeweb MCP Server client."""

import asyncio
import os
from timeweb_mcp_server.client import TimewebClient


async def main():
    """Example usage of the Timeweb client."""
    # Check if API token is set
    if not os.getenv("TIMEWEB_API_TOKEN"):
        print("Please set the TIMEWEB_API_TOKEN environment variable")
        print("Example: export TIMEWEB_API_TOKEN='your-token-here'")
        return
    
    try:
        # Initialize the client
        client = TimewebClient()
        
        print("Fetching list of virtual servers...")
        servers = await client.list_servers()
        
        if not servers:
            print("No virtual servers found.")
            return
        
        print(f"Found {len(servers)} virtual server(s):\n")
        
        for server in servers:
            print(f"ID: {server.id}")
            print(f"Name: {server.name}")
            print(f"Status: {server.status}")
            print(f"CPU: {server.cpu} cores")
            print(f"RAM: {server.ram} MB")
            print(f"Disk: {server.disk} GB")
            print(f"Location: {server.location}")
            if server.ip:
                print(f"IP: {server.ip}")
            if server.os:
                print(f"OS: {server.os}")
            print("-" * 40)
        
        # Example of getting a specific server (using the first server's ID)
        if servers:
            first_server_id = servers[0].id
            print(f"\nFetching details for server ID {first_server_id}...")
            
            server_details = await client.get_server(first_server_id)
            print(f"Server '{server_details.name}' details retrieved successfully!")
    
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
