"""Tests for MCP server."""

import pytest
from unittest.mock import AsyncMock, patch

from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from timeweb_mcp_server.server import list_tools, call_tool
from timeweb_mcp_server.client import VirtualServer


class TestMCPServer:
    """Test cases for MCP server."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools."""
        request = ListToolsRequest(method="tools/list")
        result = await list_tools(request)

        assert len(result.tools) == 2

        tool_names = [tool.name for tool in result.tools]
        assert "list_servers" in tool_names
        assert "get_server" in tool_names

        # Check list_servers tool
        list_servers_tool = next(
            tool for tool in result.tools if tool.name == "list_servers"
        )
        assert (
            list_servers_tool.description == "List all virtual servers in Timeweb Cloud"
        )
        assert list_servers_tool.inputSchema["type"] == "object"
        assert list_servers_tool.inputSchema["required"] == []

        # Check get_server tool
        get_server_tool = next(
            tool for tool in result.tools if tool.name == "get_server"
        )
        assert (
            get_server_tool.description
            == "Get details of a specific virtual server by ID"
        )
        assert "server_id" in get_server_tool.inputSchema["properties"]
        assert get_server_tool.inputSchema["required"] == ["server_id"]

    @pytest.mark.asyncio
    async def test_call_tool_list_servers_success(self):
        """Test successful list_servers tool call."""
        mock_servers = [
            VirtualServer(
                id=1,
                name="test-server-1",
                status="on",
                cpu=2,
                ram=4096,
                disk=50,
                location="ru-1",
                ip="192.168.1.1",
                os="Ubuntu 20.04",
            ),
            VirtualServer(
                id=2,
                name="test-server-2",
                status="off",
                cpu=4,
                ram=8192,
                disk=100,
                location="ru-2",
            ),
        ]

        with patch("timeweb_mcp_server.server.TimewebClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.list_servers.return_value = mock_servers
            mock_client_class.return_value = mock_client

            request = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="list_servers", arguments={}),
            )
            result = await call_tool(request)

            assert len(result.content) == 1
            content = result.content[0].text

            assert "Virtual Servers:" in content
            assert "test-server-1" in content
            assert "test-server-2" in content
            assert "ID: 1" in content
            assert "ID: 2" in content
            assert "Status: on" in content
            assert "Status: off" in content
            assert "CPU: 2 cores" in content
            assert "CPU: 4 cores" in content
            assert "RAM: 4096 MB" in content
            assert "RAM: 8192 MB" in content
            assert "IP: 192.168.1.1" in content
            assert "OS: Ubuntu 20.04" in content

    @pytest.mark.asyncio
    async def test_call_tool_list_servers_empty(self):
        """Test list_servers tool call with no servers."""
        with patch("timeweb_mcp_server.server.TimewebClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.list_servers.return_value = []
            mock_client_class.return_value = mock_client

            request = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="list_servers", arguments={}),
            )
            result = await call_tool(request)

            assert len(result.content) == 1
            content = result.content[0].text
            assert content == "No virtual servers found."

    @pytest.mark.asyncio
    async def test_call_tool_get_server_success(self):
        """Test successful get_server tool call."""
        mock_server = VirtualServer(
            id=1,
            name="test-server",
            status="on",
            cpu=2,
            ram=4096,
            disk=50,
            location="ru-1",
            ip="192.168.1.1",
            os="Ubuntu 20.04",
        )

        with patch("timeweb_mcp_server.server.TimewebClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get_server.return_value = mock_server
            mock_client_class.return_value = mock_client

            request = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="get_server", arguments={"server_id": 1}
                ),
            )
            result = await call_tool(request)

            assert len(result.content) == 1
            content = result.content[0].text

            assert "Server Details:" in content
            assert "ID: 1" in content
            assert "Name: test-server" in content
            assert "Status: on" in content
            assert "CPU: 2 cores" in content
            assert "RAM: 4096 MB" in content
            assert "Disk: 50 GB" in content
            assert "Location: ru-1" in content
            assert "IP: 192.168.1.1" in content
            assert "OS: Ubuntu 20.04" in content

    @pytest.mark.asyncio
    async def test_call_tool_get_server_invalid_id(self):
        """Test get_server tool call with invalid server ID."""
        request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="get_server", arguments={"server_id": "invalid"}
            ),
        )
        result = await call_tool(request)

        assert len(result.content) == 1
        content = result.content[0].text
        assert "Error: server_id must be an integer" in content

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self):
        """Test calling unknown tool."""
        request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="unknown_tool", arguments={}),
        )
        result = await call_tool(request)

        assert len(result.content) == 1
        content = result.content[0].text
        assert "Unknown tool: unknown_tool" in content

    @pytest.mark.asyncio
    async def test_call_tool_client_error(self):
        """Test tool call with client error."""
        with patch("timeweb_mcp_server.server.TimewebClient") as mock_client_class:
            mock_client_class.side_effect = ValueError("API token is required")

            request = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="list_servers", arguments={}),
            )
            result = await call_tool(request)

            assert len(result.content) == 1
            content = result.content[0].text
            assert "Error: API token is required" in content
