"""Timeweb Cloud API client."""

import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel


class VirtualServer(BaseModel):
    """Virtual server model."""

    id: int
    name: str
    status: str
    cpu: int
    ram: int
    disk: int
    location: str
    ip: Optional[str] = None
    os: Optional[str] = None


class TimewebClient:
    """Timeweb Cloud API client."""

    def __init__(self, api_token: Optional[str] = None) -> None:
        """Initialize the client with API token."""
        self.api_token = api_token or os.getenv("TIMEWEB_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "API token is required. Set TIMEWEB_API_TOKEN environment variable."
            )

        self.base_url = "https://api.timeweb.cloud/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def list_servers(self) -> List[VirtualServer]:
        """List all virtual servers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/servers", headers=self.headers, timeout=30.0
            )
            response.raise_for_status()

            data = response.json()
            servers = []

            for server_data in data.get("servers", []):
                server = VirtualServer(
                    id=server_data["id"],
                    name=server_data["name"],
                    status=server_data["status"],
                    cpu=server_data["configuration"]["cpu"],
                    ram=server_data["configuration"]["ram"],
                    disk=server_data["configuration"]["disk"],
                    location=server_data["location"],
                    ip=server_data.get("main_ipv4"),
                    os=server_data.get("os", {}).get("name"),
                )
                servers.append(server)

            return servers

    async def get_server(self, server_id: int) -> VirtualServer:
        """Get a specific virtual server by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/servers/{server_id}",
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()

            data = response.json()
            server_data = data["server"]

            return VirtualServer(
                id=server_data["id"],
                name=server_data["name"],
                status=server_data["status"],
                cpu=server_data["configuration"]["cpu"],
                ram=server_data["configuration"]["ram"],
                disk=server_data["configuration"]["disk"],
                location=server_data["location"],
                ip=server_data.get("main_ipv4"),
                os=server_data.get("os", {}).get("name"),
            )
