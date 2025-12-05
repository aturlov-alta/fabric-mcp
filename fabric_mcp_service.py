"""Service layer for Fabric MCP tools.

This module encapsulates all business logic for REST and SQL operations,
allowing main.py to focus solely on MCP tool definitions and wiring.

The service handles:
- Authentication setup (interactive or service principal via create_auth_provider_from_env)
- REST API calls to discover Fabric workspaces and lakehouses
- SQL queries against lakehouse SQL endpoints for schema discovery and data exploration
- Error handling and response formatting for all operations

Usage:
    service = FabricMCPService()
    workspaces = await service.list_workspaces()
"""

from typing import Any
import re
from dotenv import load_dotenv

from fabric_auth import create_auth_provider_from_env, InteractiveAuthProvider
from fabric_api_client import FabricAPIClient
from fabric_sql_client import FabricSQLClient


class FabricMCPService:
    """Provides business logic for Fabric-related MCP operations.
    
    Encapsulates:
    - Fabric REST API interactions (workspaces, lakehouses)
    - Lakehouse SQL query execution (schema discovery, data sampling)
    - Authentication management (sign out)
    
    All errors are caught and returned as part of response dictionaries
    to integrate cleanly with MCP tool definitions.
    """
    
    # SQL identifier validation pattern: starts with letter, followed by alphanumeric/underscores
    # Optionally supports schema.table notation with a single dot
    _SQL_IDENTIFIER_PATTERN = r'^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)?$'

    def __init__(self) -> None:
        """Initialize service with auth provider and API/SQL clients.
        
        Loads environment variables and creates:
        - auth_provider: Interactive (device code) or service principal auth
        - fabric_api: REST client for Fabric APIs
        - fabric_sql: SQL client for lakehouse queries
        """
        load_dotenv()
        self.auth_provider = create_auth_provider_from_env()
        self.fabric_api = FabricAPIClient(self.auth_provider)
        self.fabric_sql = FabricSQLClient(self.auth_provider, self.fabric_api)
    
    @classmethod
    def _validate_sql_identifier(cls, identifier: str) -> bool:
        """Validate that a SQL identifier contains only safe characters.
        
        Validation rules:
        - Must start with a letter (a-zA-Z)
        - Can contain letters, numbers, and underscores after the first character
        - Maximum length of 256 characters
        - Optionally supports schema.table notation with a single dot separator
        - Both schema and table parts must follow the same naming rules
        
        Args:
            identifier: The SQL identifier to validate (table name, schema name, etc.)
            
        Returns:
            bool: True if the identifier is safe, False otherwise
        """
        # Must not be empty and should follow reasonable naming conventions
        if not identifier or len(identifier) > 256:
            return False
        
        return bool(re.match(cls._SQL_IDENTIFIER_PATTERN, identifier))
    
    @staticmethod
    def _get_invalid_identifier_error(identifier: str) -> str:
        """Get standardized error message for invalid SQL identifiers.
        
        Args:
            identifier: The invalid SQL identifier
            
        Returns:
            str: Descriptive error message
        """
        return (
            f"Invalid SQL identifier format. Identifier must start with a letter, "
            f"contain only alphanumeric characters and underscores, and optionally "
            f"use a single dot for schema.table notation (max 256 chars). Got: {identifier}"
        )

    # Workspace and lakehouse operations
    async def list_workspaces(self) -> dict[str, Any]:
        """Fetch all accessible Fabric workspaces via REST API.
        
        Returns:
            dict: {"workspaces": [{"id": str, "name": str}, ...]}
        """
        data = await self.fabric_api.get("/workspaces")
        workspaces = [{"id": w["id"], "name": w["displayName"]} for w in data.get("value", [])]
        return {"workspaces": workspaces}

    async def list_lakehouses(self, workspace_id: str) -> dict[str, Any]:
        """Fetch all lakehouses in a workspace via REST API.
        
        Args:
            workspace_id: Workspace ID from list_workspaces()
        
        Returns:
            dict: {"lakehouses": [{"id": str, "name": str}, ...]}
        """
        data = await self.fabric_api.get(f"/workspaces/{workspace_id}/lakehouses")
        lakehouses_raw = data.get("value", [])
        lakehouses = [{"id": lh["id"], "name": lh["displayName"]} for lh in lakehouses_raw]
        return {"lakehouses": lakehouses}

    async def get_lakehouse_tables(self, workspace_id: str, lakehouse_id: str) -> dict[str, Any]:
        """Discover all tables in a lakehouse using SQL-based discovery.
        
        Uses INFORMATION_SCHEMA.TABLES to work with both schema-enabled and
        schema-less lakehouses (unlike REST API which only supports schema-less).
        
        Args:
            workspace_id: Workspace ID
            lakehouse_id: Lakehouse ID from list_lakehouses()
        
        Returns:
            dict: {
                "tables": [
                    {"schema": str, "name": str, "type": str, "full_name": str},
                    ...
                ]
            } or {"tables": [], "error": str} on failure
        """
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
            results = await self.fabric_sql.execute_query(workspace_id, lakehouse_id, query)
            tables = [
                {
                    "schema": row.get("schema_name"),
                    "name": row.get("table_name"),
                    "type": row.get("table_type", "BASE TABLE"),
                    "full_name": f"{row.get('schema_name')}.{row.get('table_name')}"
                }
                for row in results
            ]
            return {"tables": tables}
        except Exception as e:  # pragma: no cover - passthrough for MCP tool
            return {"tables": [], "error": f"Failed to retrieve tables: {str(e)}"}

    # SQL operations
    async def get_table_schema(self, workspace_id: str, lakehouse_id: str, table_name: str) -> dict[str, Any]:
        """Retrieve detailed column metadata from INFORMATION_SCHEMA.
        
        Supports both qualified (schema.table) and unqualified (table) names.
        Returns column definitions including data types, nullability, precision, and position.
        
        Args:
            workspace_id: Workspace ID
            lakehouse_id: Lakehouse ID
            table_name: Table name ('schema.table' or 'table')
        
        Returns:
            dict: {
                "table_name": str,
                "columns": [
                    {"name": str, "data_type": str, "is_nullable": bool, ...},
                    ...
                ]
            } or {"table_name": str, "columns": [], "error": str} on failure
        """
        # Validate table_name to prevent SQL injection
        if not self._validate_sql_identifier(table_name):
            return {
                "table_name": table_name,
                "columns": [],
                "error": self._get_invalid_identifier_error(table_name),
            }
        
        # Parse schema.table format if provided
        dot_count = table_name.count(".")
        if dot_count == 1:
            schema_name, table_only = table_name.split(".", 1)
            schema_filter = f"TABLE_SCHEMA = '{schema_name}' AND TABLE_NAME = '{table_only}'"
        elif dot_count == 0:
            schema_filter = f"TABLE_NAME = '{table_name}'"
        else:
            return {
                "table_name": table_name,
                "columns": [],
                "error": (
                    "Invalid table name format. "
                    "Expected 'table' or 'schema.table', got: '{}'".format(table_name)
                ),
            }

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
        WHERE {schema_filter}
        ORDER BY ORDINAL_POSITION
        """
        try:
            results = await self.fabric_sql.execute_query(workspace_id, lakehouse_id, schema_query)
            columns = [
                {
                    "name": row["column_name"],
                    "data_type": row["data_type"],
                    "is_nullable": row["is_nullable"] == "YES",
                    "is_primary_key": False,
                    "default_value": row["default_value"],
                    "max_length": row["max_length"],
                    "precision": row["precision"],
                    "scale": row["scale"],
                    "position": row["position"],
                }
                for row in results
            ]
            return {"table_name": table_name, "columns": columns}
        except Exception as e:  # pragma: no cover - passthrough for MCP tool
            return {"table_name": table_name, "columns": [], "error": str(e)}

    async def get_table_sample_data(
        self,
        workspace_id: str,
        lakehouse_id: str,
        table_name: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Sample rows from a table for data exploration.
        
        Useful for understanding data content, format, and volume.
        Supports both qualified (schema.table) and unqualified (table) names.
        
        Args:
            workspace_id: Workspace ID
            lakehouse_id: Lakehouse ID
            table_name: Table name ('schema.table' or 'table')
            limit: Number of rows to return (default: 10)
        
        Returns:
            dict: {
                "table_name": str,
                "sample_rows": [dict, ...],
                "row_count": int
            } or {..., "row_count": 0, "error": str} on failure
        """
        # Validate limit parameter to prevent SQL injection
        if not isinstance(limit, int) or limit <= 0:
            return {
                "table_name": table_name,
                "sample_rows": [],
                "row_count": 0,
                "error": f"Invalid limit value. Must be a positive integer, got: {limit}",
            }
        
        # Validate table_name to prevent SQL injection
        if not self._validate_sql_identifier(table_name):
            return {
                "table_name": table_name,
                "sample_rows": [],
                "row_count": 0,
                "error": self._get_invalid_identifier_error(table_name),
            }
        
        # Construct SQL with proper schema qualification if provided
        if "." in table_name:
            parts = table_name.split(".", 1)  # Split into at most 2 parts
            qualified_name = "].[".join(parts)
            sample_query = f"SELECT TOP {limit} * FROM [{qualified_name}]"
        else:
            sample_query = f"SELECT TOP {limit} * FROM [{table_name}]"

        try:
            results = await self.fabric_sql.execute_query(workspace_id, lakehouse_id, sample_query)
            return {"table_name": table_name, "sample_rows": results, "row_count": len(results)}
        except Exception as e:  # pragma: no cover - passthrough for MCP tool
            return {
                "table_name": table_name,
                "sample_rows": [],
                "row_count": 0,
                "error": f"Failed to get sample data: {str(e)}",
            }

    async def execute_custom_sql_query(
        self, workspace_id: str, lakehouse_id: str, query: str
    ) -> dict[str, Any]:
        """Execute arbitrary SQL queries for analytics and reporting.
        
        Useful for custom analysis, joins across tables, aggregations, etc.
        User is responsible for query correctness and performance.
        
        Args:
            workspace_id: Workspace ID
            lakehouse_id: Lakehouse ID
            query: SQL query string
        
        Returns:
            dict: {
                "query": str,
                "success": bool,
                "row_count": int,
                "results": [dict, ...]
            } or {..., "success": False, "error": str} on failure
        """
        try:
            results = await self.fabric_sql.execute_query(workspace_id, lakehouse_id, query)
            return {
                "query": query,
                "success": True,
                "row_count": len(results),
                "results": results,
            }
        except Exception as e:  # pragma: no cover - passthrough for MCP tool
            return {"query": query, "success": False, "error": str(e), "results": []}

    # Auth management
    def sign_out(self) -> dict[str, str]:
        """Clear cached authentication tokens (interactive auth only).
        
        Removes the token cache file, forcing re-authentication on next API call.
        No-op for service principal authentication (which doesn't cache tokens).
        
        Returns:
            dict: {
                "status": str ("success" or "not_applicable"),
                "message": str
            }
        """
        if isinstance(self.auth_provider, InteractiveAuthProvider):
            was_deleted = self.auth_provider.clear_token_cache()
            if was_deleted:
                return {
                    "status": "success",
                    "message": "Signed out successfully. You will be prompted to authenticate on the next request.",
                }
            return {"status": "success", "message": "No cached tokens found. Already signed out."}
        return {
            "status": "not_applicable",
            "message": "Sign out is not applicable for service principal authentication mode.",
        }
