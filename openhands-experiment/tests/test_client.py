"""Tests for Timeweb Cloud API client."""

import os
import pytest
from unittest.mock import patch
import httpx

from timeweb_mcp_server.client import TimewebClient, VirtualServer


class TestTimewebClient:
    """Test cases for TimewebClient."""

    def test_init_with_token(self):
        """Test client initialization with token."""
        client = TimewebClient("test-token")
        assert client.api_token == "test-token"
        assert client.base_url == "https://api.timeweb.cloud/api/v1"
        assert client.headers["Authorization"] == "Bearer test-token"

    def test_init_with_env_token(self):
        """Test client initialization with environment variable."""
        with patch.dict(os.environ, {"TIMEWEB_API_TOKEN": "env-token"}):
            client = TimewebClient()
            assert client.api_token == "env-token"

    def test_init_without_token(self):
        """Test client initialization without token raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API token is required"):
                TimewebClient()

    @pytest.mark.asyncio
    async def test_list_servers_success(self):
        """Test successful server listing."""
        mock_response_data = {
            "servers": [
                {
                    "id": 1,
                    "name": "test-server-1",
                    "status": "on",
                    "configuration": {"cpu": 2, "ram": 4096, "disk": 50},
                    "location": "ru-1",
                    "main_ipv4": "192.168.1.1",
                    "os": {"name": "Ubuntu 20.04"},
                },
                {
                    "id": 2,
                    "name": "test-server-2",
                    "status": "off",
                    "configuration": {"cpu": 4, "ram": 8192, "disk": 100},
                    "location": "ru-2",
                    "main_ipv4": "192.168.1.2",
                    "os": {"name": "CentOS 8"},
                },
            ]
        }

        client = TimewebClient("test-token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = httpx.Response(
                200,
                json=mock_response_data,
                request=httpx.Request("GET", "http://test.com"),
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            servers = await client.list_servers()

            assert len(servers) == 2

            assert servers[0].id == 1
            assert servers[0].name == "test-server-1"
            assert servers[0].status == "on"
            assert servers[0].cpu == 2
            assert servers[0].ram == 4096
            assert servers[0].disk == 50
            assert servers[0].location == "ru-1"
            assert servers[0].ip == "192.168.1.1"
            assert servers[0].os == "Ubuntu 20.04"

            assert servers[1].id == 2
            assert servers[1].name == "test-server-2"
            assert servers[1].status == "off"

    @pytest.mark.asyncio
    async def test_list_servers_empty(self):
        """Test listing servers when none exist."""
        mock_response_data = {"servers": []}

        client = TimewebClient("test-token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = httpx.Response(
                200,
                json=mock_response_data,
                request=httpx.Request("GET", "http://test.com"),
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            servers = await client.list_servers()

            assert len(servers) == 0

    @pytest.mark.asyncio
    async def test_get_server_success(self):
        """Test successful server retrieval."""
        mock_response_data = {
            "server": {
                "id": 1,
                "name": "test-server",
                "status": "on",
                "configuration": {"cpu": 2, "ram": 4096, "disk": 50},
                "location": "ru-1",
                "main_ipv4": "192.168.1.1",
                "os": {"name": "Ubuntu 20.04"},
            }
        }

        client = TimewebClient("test-token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = httpx.Response(
                200,
                json=mock_response_data,
                request=httpx.Request("GET", "http://test.com"),
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            server = await client.get_server(1)

            assert server.id == 1
            assert server.name == "test-server"
            assert server.status == "on"
            assert server.cpu == 2
            assert server.ram == 4096
            assert server.disk == 50
            assert server.location == "ru-1"
            assert server.ip == "192.168.1.1"
            assert server.os == "Ubuntu 20.04"

    @pytest.mark.asyncio
    async def test_api_error(self):
        """Test API error handling."""
        client = TimewebClient("test-token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = httpx.Response(401)
            mock_response.raise_for_status = lambda: (_ for _ in ()).throw(
                httpx.HTTPStatusError(
                    "401 Unauthorized", request=None, response=mock_response
                )
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            with pytest.raises(httpx.HTTPStatusError):
                await client.list_servers()


class TestVirtualServer:
    """Test cases for VirtualServer model."""

    def test_virtual_server_creation(self):
        """Test VirtualServer model creation."""
        server = VirtualServer(
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

        assert server.id == 1
        assert server.name == "test-server"
        assert server.status == "on"
        assert server.cpu == 2
        assert server.ram == 4096
        assert server.disk == 50
        assert server.location == "ru-1"
        assert server.ip == "192.168.1.1"
        assert server.os == "Ubuntu 20.04"

    def test_virtual_server_optional_fields(self):
        """Test VirtualServer with optional fields."""
        server = VirtualServer(
            id=1,
            name="test-server",
            status="on",
            cpu=2,
            ram=4096,
            disk=50,
            location="ru-1",
        )

        assert server.ip is None
        assert server.os is None
