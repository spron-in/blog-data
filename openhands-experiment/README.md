# Timeweb Cloud MCP Server

A Model Context Protocol (MCP) server for interacting with Timeweb Cloud virtual servers. This server provides tools to list and retrieve information about your virtual servers through the Timeweb Cloud API.

## Features

- **List Virtual Servers**: Get a comprehensive list of all your virtual servers
- **Get Server Details**: Retrieve detailed information about a specific server by ID
- **Async Support**: Built with async/await for efficient API calls
- **Type Safety**: Full type hints and Pydantic models for data validation
- **Error Handling**: Robust error handling for API failures

## Installation

### Prerequisites

- Python 3.8 or higher
- Timeweb Cloud API token

### Install from source

1. Clone the repository:
```bash
git clone <repository-url>
cd timeweb-mcp-server
```

2. Install the package:
```bash
pip install -e .
```

Or install with development dependencies:
```bash
pip install -e ".[dev]"
```

## Configuration

### API Token

You need a Timeweb Cloud API token to use this server. You can obtain one from your Timeweb Cloud control panel.

Set your API token as an environment variable:
```bash
export TIMEWEB_API_TOKEN="your-api-token-here"
```

Alternatively, you can pass the token directly when initializing the client (not recommended for production).

## Usage

### Running the MCP Server

Start the server using the command line:
```bash
timeweb-mcp-server
```

Or run directly with Python:
```bash
python -m timeweb_mcp_server.server
```

### Available Tools

#### 1. list_servers

Lists all virtual servers in your Timeweb Cloud account.

**Parameters**: None

**Example Response**:
```
Virtual Servers:

ID: 12345
Name: web-server-01
Status: on
CPU: 2 cores
RAM: 4096 MB
Disk: 50 GB
Location: ru-1
IP: 192.168.1.100
OS: Ubuntu 20.04

----------------------------------------

ID: 12346
Name: database-server
Status: off
CPU: 4 cores
RAM: 8192 MB
Disk: 100 GB
Location: ru-2
IP: 192.168.1.101
OS: CentOS 8
```

#### 2. get_server

Retrieves detailed information about a specific virtual server.

**Parameters**:
- `server_id` (integer, required): The ID of the server to retrieve

**Example Response**:
```
Server Details:

ID: 12345
Name: web-server-01
Status: on
CPU: 2 cores
RAM: 4096 MB
Disk: 50 GB
Location: ru-1
IP: 192.168.1.100
OS: Ubuntu 20.04
```

### Integration with MCP Clients

This server follows the Model Context Protocol specification and can be integrated with any MCP-compatible client, such as Claude Desktop or other AI assistants that support MCP.

Example MCP client configuration:
```json
{
  "mcpServers": {
    "timeweb": {
      "command": "timeweb-mcp-server",
      "env": {
        "TIMEWEB_API_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

## Development

### Setting up the development environment

1. Clone the repository
2. Install development dependencies:
```bash
pip install -e ".[dev]"
```

### Running tests

Run the test suite:
```bash
pytest
```

Run tests with coverage:
```bash
pytest --cov=timeweb_mcp_server
```

### Code formatting

Format code with Black:
```bash
black timeweb_mcp_server tests
```

### Type checking

Run type checking with mypy:
```bash
mypy timeweb_mcp_server
```

## API Reference

### TimewebClient

The main client class for interacting with the Timeweb Cloud API.

```python
from timeweb_mcp_server.client import TimewebClient

# Initialize with environment variable
client = TimewebClient()

# Or initialize with token directly
client = TimewebClient("your-api-token")

# List all servers
servers = await client.list_servers()

# Get specific server
server = await client.get_server(12345)
```

### VirtualServer Model

Pydantic model representing a virtual server:

```python
class VirtualServer(BaseModel):
    id: int
    name: str
    status: str
    cpu: int
    ram: int
    disk: int
    location: str
    ip: Optional[str] = None
    os: Optional[str] = None
```

## Error Handling

The server handles various error conditions:

- **Missing API Token**: Returns clear error message when token is not provided
- **API Errors**: HTTP errors from the Timeweb API are caught and returned as error messages
- **Invalid Parameters**: Parameter validation errors are handled gracefully
- **Network Issues**: Connection timeouts and network errors are handled

## Security

- API tokens are read from environment variables for security
- All API requests use HTTPS
- No sensitive information is logged

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Check the [Issues](https://github.com/your-repo/timeweb-mcp-server/issues) page
- Review the Timeweb Cloud API documentation
- Ensure your API token has the necessary permissions

## Changelog

### v0.1.0
- Initial release
- Basic server listing functionality
- Individual server details retrieval
- Full test coverage
- MCP protocol compliance
