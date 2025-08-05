"""Timeweb Cloud MCP Server."""

import asyncio
import json
import logging
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
)

from .client import TimewebClient, VirtualServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the MCP server
app: Server = Server("timeweb-mcp-server")


@app.list_tools()
async def list_tools(request: ListToolsRequest) -> ListToolsResult:
    """List available tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name="list_servers",
                description="List all virtual servers in Timeweb Cloud",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="get_server",
                description="Get details of a specific virtual server by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "server_id": {
                            "type": "integer",
                            "description": "The ID of the server to retrieve",
                        }
                    },
                    "required": ["server_id"],
                },
            ),
        ]
    )


@app.call_tool()
async def call_tool(request: CallToolRequest) -> CallToolResult:
    """Handle tool calls."""
    try:
        # Check if tool exists first
        if request.params.name not in ["list_servers", "get_server"]:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text=f"Unknown tool: {request.params.name}"
                    )
                ]
            )

        # For get_server, validate arguments before initializing client
        if request.params.name == "get_server":
            if not request.params.arguments:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text", text="Error: server_id is required"
                        )
                    ]
                )
            server_id = request.params.arguments.get("server_id")
            if not isinstance(server_id, int):
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text", text="Error: server_id must be an integer"
                        )
                    ]
                )

        # Initialize client only after validation
        client = TimewebClient()

        if request.params.name == "list_servers":
            servers = await client.list_servers()

            # Format the response
            if not servers:
                content = "No virtual servers found."
            else:
                content = "Virtual Servers:\n\n"
                for server in servers:
                    content += f"ID: {server.id}\n"
                    content += f"Name: {server.name}\n"
                    content += f"Status: {server.status}\n"
                    content += f"CPU: {server.cpu} cores\n"
                    content += f"RAM: {server.ram} MB\n"
                    content += f"Disk: {server.disk} GB\n"
                    content += f"Location: {server.location}\n"
                    if server.ip:
                        content += f"IP: {server.ip}\n"
                    if server.os:
                        content += f"OS: {server.os}\n"
                    content += "\n" + "-" * 40 + "\n\n"

            return CallToolResult(content=[TextContent(type="text", text=content)])

        elif request.params.name == "get_server":
            # We already validated arguments above, so this is safe
            server_id = request.params.arguments["server_id"]  # type: ignore
            server = await client.get_server(server_id)

            content = f"Server Details:\n\n"
            content += f"ID: {server.id}\n"
            content += f"Name: {server.name}\n"
            content += f"Status: {server.status}\n"
            content += f"CPU: {server.cpu} cores\n"
            content += f"RAM: {server.ram} MB\n"
            content += f"Disk: {server.disk} GB\n"
            content += f"Location: {server.location}\n"
            if server.ip:
                content += f"IP: {server.ip}\n"
            if server.os:
                content += f"OS: {server.os}\n"

            return CallToolResult(content=[TextContent(type="text", text=content)])
        
        # This should never be reached due to the validation above
        return CallToolResult(
            content=[TextContent(type="text", text="Internal error")]
        )

    except Exception as e:
        logger.error(f"Error calling tool {request.params.name}: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def main() -> None:
    """Main entry point for the server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
