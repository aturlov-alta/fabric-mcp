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

Authentication: Supports both interactive (device code flow) and service principal authentication
Requirements: See README.md for setup instructions

Usage: Configure in VS Code via mcp.json to enable Copilot integration
"""

from typing import Any
from dotenv import load_dotenv
from fastmcp import FastMCP

from fabric_auth import create_auth_provider_from_env
from fabric_api_client import FabricAPIClient
from fabric_sql_client import FabricSQLClient

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Fabric MCP Server")

# Initialize authentication and clients
auth_provider = create_auth_provider_from_env()
fabric_api = FabricAPIClient(auth_provider)
fabric_sql = FabricSQLClient(auth_provider, fabric_api)


# ============================================================================
# MCP Tools - Fabric Workspace and Lakehouse Operations
# ============================================================================

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
    for lakehouse in lakehouses_raw:
        lakehouses.append({
            "id": lakehouse["id"], 
            "name": lakehouse["displayName"]
        })
    
    return {"lakehouses": lakehouses}


@mcp.tool()
async def get_lakehouse_tables(workspace_id: str, lakehouse_id: str) -> dict[str, Any]:
    """
    Get all tables in a specific lakehouse for schema discovery.
    Works with both schema-enabled and schema-less lakehouses.

    Args:
        workspace_id: The ID of the workspace containing the lakehouse
        lakehouse_id: The ID of the lakehouse to query tables from
    
    Returns:
        Dictionary containing array of tables with their schemas, names, and types.
        Use table names with get_table_schema and get_table_sample_data tools.
    """
    # Use SQL query to discover tables (works for both schema-enabled and schema-less lakehouses)
    query = """
    SELECT 
        TABLE_SCHEMA as schema_name,
        TABLE_NAME as table_name,
        TABLE_TYPE as table_type
    FROM INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """
    
    try:
        results = await fabric_sql.execute_query(workspace_id, lakehouse_id, query)
        
        tables = []
        for row in results:
            tables.append({
                "schema": row.get("schema_name"),
                "name": row.get("table_name"),
                "type": row.get("table_type", "BASE TABLE"),
                "full_name": f"{row.get('schema_name')}.{row.get('table_name')}"
            })
        
        return {"tables": tables}
        
    except Exception as e:
        return {
            "tables": [],
            "error": f"Failed to retrieve tables: {str(e)}"
        }


# ============================================================================
# MCP Tools - SQL Query Operations
# ============================================================================

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
                "is_primary_key": False,
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
async def get_table_sample_data(
    workspace_id: str,
    lakehouse_id: str,
    table_name: str,
    limit: int = 10
) -> dict[str, Any]:
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
async def execute_custom_sql_query(
    workspace_id: str,
    lakehouse_id: str,
    query: str
) -> dict[str, Any]:
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


# ============================================================================
# MCP Tools - Authentication Management
# ============================================================================

@mcp.tool()
async def sign_out() -> dict[str, str]:
    """
    Sign out and clear cached authentication tokens.
    
    Use this tool to remove stored credentials and force re-authentication
    on the next request. Only applicable for interactive authentication mode.
    
    Returns:
        Dictionary with status and message indicating the result of sign-out operation.
    """
    from fabric_auth import InteractiveAuthProvider
    
    if isinstance(auth_provider, InteractiveAuthProvider):
        was_deleted = auth_provider.clear_token_cache()
        if was_deleted:
            return {
                "status": "success",
                "message": "Signed out successfully. You will be prompted to authenticate on the next request."
            }
        else:
            return {
                "status": "success",
                "message": "No cached tokens found. Already signed out."
            }
    else:
        return {
            "status": "not_applicable",
            "message": "Sign out is not applicable for service principal authentication mode."
        }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    mcp.run()
