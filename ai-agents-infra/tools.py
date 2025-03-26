
import json
import yaml
import psycopg2
import paramiko
import base64
import io
import requests
from typing import Type, List, Optional
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

class PostgreSQLCommandInput(BaseModel):
    """Input for executing PostgreSQL commands securely."""
    command: str = Field(..., description="The SQL command to execute (e.g., 'SELECT * FROM users LIMIT 10').")
    host: str = Field(..., description="The PostgreSQL server host address.")
    port: int = Field(5432, description="The PostgreSQL server port (default: 5432).")
    user: str = Field(..., description="The PostgreSQL username.")
    password: str = Field(..., description="The PostgreSQL password.")
    database: str = Field(..., description="The PostgreSQL database name to use.")

class PostgreSQLTool(BaseTool):
    name: str = "PostgreSQL Command Executor"
    description: str = "Executes PostgreSQL commands securely and returns the results in a readable format."
    args_schema: Type[BaseModel] = PostgreSQLCommandInput

    def _run(self, command: str, host: str, port: int, user: str, password: str, database: str) -> str:
        try:
            # Establish connection to PostgreSQL
            connection = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=database
            )
            
            # Set autocommit to false for better control
            connection.autocommit = False
            
            # Execute the command
            with connection.cursor() as cursor:
                cursor.execute(command)
                
                # For SELECT queries, fetch results
                if command.strip().lower().startswith("select") or \
                   command.strip().lower().startswith("show") or \
                   command.strip().lower().startswith("explain"):
                    columns = [desc[0] for desc in cursor.description]
                    result = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    return json.dumps(result, indent=2, default=str)  # default=str handles datetime objects
                
                # For UPDATE, INSERT, DELETE queries
                connection.commit()
                return json.dumps({
                    "affected_rows": cursor.rowcount,
                    "message": f"Command executed successfully. Affected rows: {cursor.rowcount}"
                }, indent=2)
                
        except psycopg2.Error as e:
            # Rollback in case of error
            if 'connection' in locals():
                connection.rollback()
            
            return json.dumps({
                "error": f"PostgreSQL Error: {str(e)}",
                "code": e.pgcode if hasattr(e, 'pgcode') else None
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
        finally:
            if 'connection' in locals():
                connection.close()

class LinuxCommandInput(BaseModel):
    """Input for executing Linux commands securely via SSH."""
    command: str = Field(..., description="The Linux command to execute (e.g., 'ls -l /home').")
    host: str = Field(..., description="The Linux server host address.")
    user: str = Field(..., description="The Linux username.")
    ssh_private_key_base64: str = Field(..., description="The SSH private key encoded in base64.")
    ssh_key_passphrase: str = Field(None, description="The passphrase for the SSH private key (optional).")

class SSHTool(BaseTool):
    name: str = "Linux Command Executor"
    description: str = "Executes Linux commands securely via SSH using private keys provided as base64 and returns the results. Supports optional passphrase."
    args_schema: Type[BaseModel] = LinuxCommandInput

    def _run(self, command: str, host: str, user: str, ssh_private_key_base64: str, ssh_key_passphrase: str = None) -> str:
        try:

            
            private_key_decoded = base64.b64decode(ssh_private_key_base64.strip())
            private_key_string = private_key_decoded.decode() #decode to string.

            if ssh_key_passphrase:
                private_key = paramiko.RSAKey.from_private_key(io.StringIO(private_key_string.strip()), password=ssh_key_passphrase)
            else:
                private_key = paramiko.RSAKey.from_private_key(io.StringIO(private_key_string.strip()))

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Be cautious with this in production

            client.connect(hostname=host, username=user, pkey=private_key)

            stdin, stdout, stderr = client.exec_command(command)

            output = stdout.read().decode()
            error = stderr.read().decode()

            client.close()

            if error:
                return json.dumps({"error": error, "output": output}, indent=2)
            else:
                return json.dumps({"output": output}, indent=2)

        except paramiko.AuthenticationException as e:
            return json.dumps({"error": f"Authentication failed. Check your credentials and passphrase: {str(e)}"}, indent=2)
        except paramiko.SSHException as e:
            return json.dumps({"error": f"SSH error: {str(e)}"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

class DigitalOceanAPIInput(BaseModel):
    """Input for executing DigitalOcean API calls."""
    endpoint: str = Field(..., description="The DigitalOcean API endpoint (e.g., '/v2/images?private=true').")
    method: str = Field(..., description="The HTTP method (GET, POST, PUT, DELETE).")
    api_token: str = Field(..., description="The DigitalOcean API token.")
    data: dict = Field({}, description="The JSON data for POST or PUT requests (optional).")

class DigitalOceanAPITool(BaseTool):
    name: str = "DigitalOcean API Executor"
    description: str = "Executes DigitalOcean API calls using a token and returns the JSON response."
    args_schema: Type[BaseModel] = DigitalOceanAPIInput

    def _run(self, endpoint: str, method: str, api_token: str, data: dict) -> str:
        try:
            url = f"https://api.digitalocean.com{endpoint}"
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }

            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                return json.dumps({"error": "Invalid HTTP method."}, indent=2)

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            return json.dumps(response.json(), indent=2)

        except requests.exceptions.HTTPError as e:
            try:
                error_details = e.response.json() # Try to parse DigitalOcean error.
                return json.dumps({"error": f"HTTP Error: {error_details}"}, indent=2)
            except:
                return json.dumps({"error": f"HTTP Error: {str(e)}"}, indent=2) #If not json, return the string.
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Request Error: {str(e)}"}, indent=2)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON response from DigitalOcean API."}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

class DigitalOceanEndpointSearchInput(BaseModel):
    """Input for searching DigitalOcean API endpoints."""
    search_term: str = Field(..., description="The term to search for within the DigitalOcean API specification (e.g., 'droplets', 'load balancers').")
    confirmation_prompt: Optional[str] = Field(None, description="Optional prompt to confirm if the found endpoint is the correct one.")

class DigitalOceanEndpointSearchResult(BaseModel):
    """Result of searching DigitalOcean API endpoints."""
    endpoints: List[dict] = Field(..., description="A list of matching API endpoints with descriptions.")

class DigitalOceanEndpointSearchTool(BaseTool):
    name: str = "DigitalOcean Endpoint Searcher"
    description: str = "Searches the DigitalOcean API specification for endpoints matching a search term and returns the results."
    args_schema: Type[BaseModel] = DigitalOceanEndpointSearchInput
    return_direct: bool = False

    def _run(self, search_term: str, confirmation_prompt: Optional[str] = None) -> str:
        try:
            spec_url = "https://api-engineering.nyc3.cdn.digitaloceanspaces.com/spec-ci/DigitalOcean-public.v2.yaml"
            response = requests.get(spec_url)
            response.raise_for_status()  # Raise HTTPError for bad responses

            spec_data = yaml.safe_load(response.text)
            paths = spec_data.get("paths", {})
            results = []

            for path, path_data in paths.items():
                if search_term.lower() in path.lower():
                    description = path_data.get("get", {}).get("summary", "No description available.")
                    if description == 'None':
                      description = "No description available."
                    results.append({"path": path, "description": description})
                for method_data in path_data.values():
                    if isinstance(method_data, dict):
                        description = method_data.get("summary", "No description available.")
                        if description == 'None':
                          description = "No description available."
                        if search_term.lower() in description.lower():
                            results.append({"path": path, "description": description})

            if confirmation_prompt and results:
                # Add confirmation prompt to the output
                confirmation_message = f"{confirmation_prompt}\n\nMatching Endpoints:\n{json.dumps(results, indent=2)}"
                return confirmation_message

            return json.dumps(results, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Request Error: {str(e)}"}, indent=2)
        except yaml.YAMLError as e:
            return json.dumps({"error": f"YAML Error: {str(e)}"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)