"""
Fabric MCP Server - Model Context Protocol server for Microsoft Fabric

This MCP server provides AI assistants (like GitHub Copilot) with tools to interact with 
Microsoft Fabric workspaces, lakehouses, and data through both REST APIs and SQL endpoints.

Available Tools:
- list_workspaces: Discover all accessible Fabric workspaces
- list_lakehouses: List lakehouses within a specific workspace  
- get_lakehouse_tables: Enumerate tables and views in a lakehouse
- get_table_schema: Retrieve detailed schema information for tables
- get_table_sample_data: Sample data from tables for exploration
- execute_custom_sql_query: Run custom SQL queries for analytics

Authentication: Uses Azure Service Principal with Power BI API scope
Requirements: FABRIC_CLIENT_ID, FABRIC_CLIENT_SECRET, FABRIC_TENANT_ID environment variables

Usage: Configure in VS Code via .vscode/mcp.json to enable Copilot integration
"""

import os
from typing import Any, Optional, Dict, List
import httpx
import msal
from dotenv import load_dotenv
from fastmcp import FastMCP
import pyodbc

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Fabric MCP Server")

# Configuration
CLIENT_ID = os.getenv("FABRIC_CLIENT_ID")
CLIENT_SECRET = os.getenv("FABRIC_CLIENT_SECRET")
TENANT_ID = os.getenv("FABRIC_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


class FabricAPIClient:
    """Centralized Fabric API client to reduce code duplication."""
    
    def __init__(self):
        self._token_cache = None
    
    def _get_access_token(self) -> str:
        """Get cached access token or acquire new one."""
        if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
            raise Exception("Missing required environment variables: FABRIC_CLIENT_ID, FABRIC_CLIENT_SECRET, FABRIC_TENANT_ID")
        
        app_msal = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET
        )
        result = app_msal.acquire_token_for_client(scopes=SCOPE)
        
        if "access_token" in result:
            return result["access_token"]
        else:
            error_msg = result.get('error_description', 'Unknown error')
            raise Exception(f"Could not acquire token: {error_msg}")
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Fabric API."""
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{FABRIC_API_BASE}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"API Error {response.status_code}: {response.text}")
    
    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make GET request to Fabric API."""
        return await self._make_request("GET", endpoint, **kwargs)
    
    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make POST request to Fabric API."""
        return await self._make_request("POST", endpoint, **kwargs)
    
    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make PUT request to Fabric API."""
        return await self._make_request("PUT", endpoint, **kwargs)
    
    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request to Fabric API."""
        return await self._make_request("DELETE", endpoint, **kwargs)


# Global API client instance
fabric_api = FabricAPIClient()


@mcp.tool()
async def list_workspaces() -> dict[str, Any]:
    """
    List all Microsoft Fabric workspaces accessible to the authenticated user.
    
    Returns a list of workspaces with their IDs and display names.
    Use this tool when you need to discover available workspaces or find a workspace ID.
    """
    data = await fabric_api.get("/workspaces")
    workspaces = [{"id": w["id"], "name": w["displayName"]} for w in data.get("value", [])]
    return {"workspaces": workspaces}


@mcp.tool()
async def list_lakehouses(workspace_id: str) -> dict[str, Any]:
    """
    List all lakehouses in a specific Microsoft Fabric workspace.
    
    Args:
        workspace_id: The ID of the workspace to query (use list_workspaces to find workspace IDs)
    
    Returns:
        Dictionary containing array of lakehouses with their IDs and display names.
        Use lakehouse IDs with other tools to explore tables and data.
    """
    data = await fabric_api.get(f"/workspaces/{workspace_id}/lakehouses")
    
    # Extract lakehouses from the response
    lakehouses_raw = data.get("value", [])
    
    # Process each lakehouse
    lakehouses = []
    for i, lakehouse in enumerate(lakehouses_raw):
        lakehouses.append({
            "id": lakehouse["id"], 
            "name": lakehouse["displayName"]
        })
    
    result = {"lakehouses": lakehouses}
    
    return result


@mcp.tool()
async def get_lakehouse_tables(workspace_id: str, lakehouse_id: str) -> dict[str, Any]:
    """
    Get all tables in a specific lakehouse for schema discovery.
    Only lakehouses without a schema are supported at this time.

    Args:
        workspace_id: The ID of the workspace containing the lakehouse
        lakehouse_id: The ID of the lakehouse to query tables from
    
    Returns:
        Dictionary containing array of tables with their names, types, formats, and locations.
        Use table names with get_table_schema and get_table_sample_data tools.
    """
    data = await fabric_api.get(f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables")
    tables = []
    
    for table in data.get("data", []):
        tables.append({
            "name": table.get("name"),
            "type": table.get("type", "table"),
            "format": table.get("format", "delta"),
            "location": table.get("location", f"Tables/{table.get('name')}")
        })
    
    return {"tables": tables}


class FabricSQLClient:
    """SQL client for querying Fabric lakehouse metadata via SQL endpoint."""
    
    def __init__(self):
        self._connections = {}
    
    def _get_connection_string(self, sql_endpoint: str, lakehouse_name: str) -> str:
        """Build ODBC connection string for Fabric lakehouse."""
        return f"Driver={{ODBC Driver 18 for SQL Server}};Server={sql_endpoint};Database={lakehouse_name};Authentication=ActiveDirectoryServicePrincipal;UID={CLIENT_ID};PWD={CLIENT_SECRET};Encrypt=yes;TrustServerCertificate=no;"
    
    async def _get_lakehouse_info(self, workspace_id: str, lakehouse_id: str) -> tuple[str, str]:
        """Get SQL endpoint and lakehouse name."""
        data = await fabric_api.get(f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
        
        sql_properties = data.get("properties", {}).get("sqlEndpointProperties", {})
        connection_string = sql_properties.get("connectionString")
        lakehouse_name = data.get("displayName", lakehouse_id)
        
        if not connection_string:
            raise Exception(f"No SQL endpoint found for lakehouse {lakehouse_id}")
        
        return connection_string, lakehouse_name
    
    async def execute_query(self, workspace_id: str, lakehouse_id: str, query: str) -> List[Dict[str, Any]]:
        """Execute SQL query against lakehouse and return results."""
        sql_endpoint, lakehouse_name = await self._get_lakehouse_info(workspace_id, lakehouse_id)
        connection_string = self._get_connection_string(sql_endpoint, lakehouse_name)
        
        try:
            with pyodbc.connect(connection_string) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                
                # Get column names
                columns = [column[0] for column in cursor.description]
                
                # Get all rows
                rows = cursor.fetchall()
                
                # Convert to list of dictionaries
                results = []
                for row in rows:
                    results.append(dict(zip(columns, row)))
                
                return results
                
        except Exception as e:
            raise Exception(f"SQL query failed: {str(e)}")


# Global SQL client instance
fabric_sql = FabricSQLClient()

@mcp.tool()
async def get_table_schema(workspace_id: str, lakehouse_id: str, table_name: str) -> dict[str, Any]:
    """
    Get detailed schema information for a specific table including column definitions.
    
    Args:
        workspace_id: The ID of the workspace containing the lakehouse
        lakehouse_id: The ID of the lakehouse containing the table
        table_name: The name of the table to analyze (use get_lakehouse_tables to find table names)
    
    Returns:
        Dictionary with table name and array of column definitions including data types,
        nullability, constraints, and positioning information.
    """
    # Simplified SQL query
    schema_query = f"""
    SELECT 
        COLUMN_NAME as column_name,
        DATA_TYPE as data_type,
        IS_NULLABLE as is_nullable,
        COLUMN_DEFAULT as default_value,
        CHARACTER_MAXIMUM_LENGTH as max_length,
        NUMERIC_PRECISION as precision,
        NUMERIC_SCALE as scale,
        ORDINAL_POSITION as position
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = '{table_name}'
    ORDER BY ORDINAL_POSITION
    """
    
    try:
        results = await fabric_sql.execute_query(workspace_id, lakehouse_id, schema_query)
        
        columns = []
        for row in results:
            columns.append({
                "name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"] == "YES",
                "is_primary_key": False,  # We'll handle this separately if needed
                "default_value": row["default_value"],
                "max_length": row["max_length"],
                "precision": row["precision"],
                "scale": row["scale"],
                "position": row["position"]
            })
        
        return {"table_name": table_name, "columns": columns}
        
    except Exception as e:
        return {"table_name": table_name, "columns": [], "error": str(e)}

@mcp.tool()
async def get_table_sample_data(workspace_id: str, lakehouse_id: str, table_name: str, limit: int = 10) -> dict[str, Any]:
    """
    Get sample data from a table to understand its content and structure.
    
    Args:
        workspace_id: The ID of the workspace containing the lakehouse
        lakehouse_id: The ID of the lakehouse containing the table
        table_name: The name of the table to sample
        limit: Number of rows to return (default: 10)
    """
    sample_query = f"SELECT TOP {limit} * FROM [{table_name}]"
    
    try:
        results = await fabric_sql.execute_query(workspace_id, lakehouse_id, sample_query)
        
        return {
            "table_name": table_name,
            "sample_rows": results,
            "row_count": len(results)
        }
        
    except Exception as e:
        return {
            "table_name": table_name,
            "sample_rows": [],
            "row_count": 0,
            "error": f"Failed to get sample data: {str(e)}"
        }

@mcp.tool()
async def execute_custom_sql_query(workspace_id: str, lakehouse_id: str, query: str) -> dict[str, Any]:
    """
    Execute a custom SQL query against the lakehouse and return results.
    
    Args:
        workspace_id: The ID of the workspace containing the lakehouse
        lakehouse_id: The ID of the lakehouse to query
        query: The SQL query to execute
    """
    try:
        results = await fabric_sql.execute_query(workspace_id, lakehouse_id, query)
        
        return {
            "query": query,
            "success": True,
            "row_count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {
            "query": query,
            "success": False,
            "error": str(e),
            "results": []
        }


# Entry point for running the MCP server
if __name__ == "__main__":
    mcp.run()
