# Microsoft Fabric REST API Reference

This document catalogs the Microsoft Fabric REST APIs used by the fabric-mcp server. API endpoints and response structures are verified through manual testing and documented here as the official Fabric API documentation evolves.

**Last Updated**: December 5, 2025  
**Base URL**: `https://api.fabric.microsoft.com/v1`  
**Authentication**: Bearer token (obtained via MSAL)

---

## Workspaces

### List Workspaces
- **Endpoint**: `GET /workspaces`
- **Status**: ✅ Verified
- **Description**: Returns all workspaces accessible to the authenticated user
- **Query Parameters**: None
- **Response Structure**:
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "description": "string (optional)",
        "type": "Workspace",
        "state": "Active"
      }
    ]
  }
  ```
- **Notes**:
  - Includes all workspace types (personal, shared, organizational)
  - Authenticated user must have at least Read access to workspace
  - Does not include workspaces where user has no permissions

---

## Lakehouses

### List Lakehouses
- **Endpoint**: `GET /workspaces/{workspaceId}/lakehouses`
- **Status**: ✅ Verified
- **Description**: Returns all lakehouses in a workspace
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
- **Query Parameters**: None
- **Response Structure**:
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "description": "string (optional)",
        "type": "Lakehouse",
        "createdDate": "ISO 8601 datetime",
        "lastUpdatedTime": "ISO 8601 datetime"
      }
    ]
  }
  ```
- **Notes**:
  - Returns basic lakehouse metadata only
  - Must call detail endpoint to get SQL endpoint information
  - Empty array if workspace contains no lakehouses

### Get Lakehouse Details
- **Endpoint**: `GET /workspaces/{workspaceId}/lakehouses/{lakehouseId}`
- **Status**: ✅ Verified
- **Description**: Returns detailed information for a specific lakehouse including SQL endpoint
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
  - `lakehouseId`: Lakehouse ID (UUID)
- **Query Parameters**: None
- **Response Structure**:
  ```json
  {
    "id": "string (UUID)",
    "workspaceId": "string (UUID)",
    "displayName": "string",
    "description": "string (optional)",
    "type": "Lakehouse",
    "createdDate": "ISO 8601 datetime",
    "lastUpdatedTime": "ISO 8601 datetime",
    "properties": {
      "sqlEndpointProperties": {
        "connectionString": "Server=<server>.datawarehouse.fabric.microsoft.com;Database=<lakehouse_name>;",
        "id": "string (UUID)",
        "displayName": "string"
      }
    }
  }
  ```
- **Notes**:
  - Connection string contains SQL Server endpoint details
  - `sqlEndpointProperties.connectionString` is the key field for database connectivity
  - May include additional properties depending on lakehouse configuration
  - Requires individual API calls per lakehouse (no batch endpoint)

---

## Warehouses

### List Warehouses
- **Endpoint**: `GET /workspaces/{workspaceId}/warehouses`
- **Status**: ❓ Status TBD - Research Needed
- **Alternative Endpoint**: `GET /workspaces/{workspaceId}/items?type=Warehouse`
- **Description**: Returns all warehouses in a workspace
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
- **Query Parameters** (items endpoint):
  - `type`: Filter by item type (e.g., `Warehouse`)
- **Response Structure** (Primary):
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "description": "string (optional)",
        "type": "Warehouse",
        "createdDate": "ISO 8601 datetime",
        "lastUpdatedTime": "ISO 8601 datetime"
      }
    ]
  }
  ```
- **Response Structure** (Items Fallback):
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "type": "Warehouse",
        "workspaceId": "string (UUID)"
      }
    ]
  }
  ```
- **Notes**:
  - Primary endpoint `/warehouses` may not exist; use items API as fallback
  - Items API returns less detailed metadata than primary endpoint
  - SQLDemo workspace known to contain warehouse(s) but discovery status unclear
  - **Research Needed**: Verify primary endpoint availability and response structure

### Get Warehouse Details
- **Endpoint**: `GET /workspaces/{workspaceId}/warehouses/{warehouseId}`
- **Status**: ❓ Status TBD - Research Needed
- **Alternative Endpoint**: Items list response may contain sufficient detail
- **Description**: Returns detailed information for a specific warehouse including SQL endpoint
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
  - `warehouseId`: Warehouse ID (UUID)
- **Query Parameters**: None
- **Response Structure** (Expected):
  ```json
  {
    "id": "string (UUID)",
    "workspaceId": "string (UUID)",
    "displayName": "string",
    "description": "string (optional)",
    "type": "Warehouse",
    "createdDate": "ISO 8601 datetime",
    "lastUpdatedTime": "ISO 8601 datetime",
    "properties": {
      "connectionString": "Server=<server>.datawarehouse.fabric.microsoft.com;Database=<warehouse_name>;",
      "sqlEndpointProperties": {
        "id": "string (UUID)",
        "displayName": "string"
      }
    }
  }
  ```
- **Notes**:
  - **Status Unknown**: Structure may differ from lakehouses
  - **Research Needed**: Verify endpoint availability, response structure, and SQL endpoint location
  - Connection string location may differ from lakehouse API response

---

## Mirrored Databases

### List Mirrored Databases
- **Endpoint**: `GET /workspaces/{workspaceId}/mirroredDatabases`
- **Status**: ❓ Status TBD - Research Needed
- **Alternative Endpoint**: `GET /workspaces/{workspaceId}/items?type=MirroredDatabase`
- **Description**: Returns all mirrored databases in a workspace
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
- **Query Parameters** (items endpoint):
  - `type`: Filter by item type (e.g., `MirroredDatabase`)
- **Response Structure** (Expected):
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "type": "MirroredDatabase",
        "createdDate": "ISO 8601 datetime"
      }
    ]
  }
  ```
- **Notes**:
  - **Status Unknown**: Primary endpoint may not exist or may be in preview
  - **Research Needed**: Verify API availability and response structure
  - Items API type filter may be the only available discovery mechanism

### Get Mirrored Database Details
- **Endpoint**: `GET /workspaces/{workspaceId}/mirroredDatabases/{databaseId}`
- **Status**: ❓ Status TBD - Research Needed
- **Description**: Returns detailed information including SQL endpoint
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
  - `databaseId`: Database ID (UUID)
- **Response Structure** (Expected):
  ```json
  {
    "id": "string (UUID)",
    "displayName": "string",
    "type": "MirroredDatabase",
    "properties": {
      "sourceType": "string (e.g., 'AzureSQLDatabase')",
      "connectionString": "Server=<server>;Database=<database>;..."
    }
  }
  ```
- **Notes**:
  - **Research Needed**: Confirm endpoint exists, response structure, SQL endpoint details
  - Connection string format may differ based on source type

---

## SQL Endpoints (Generic)

### List SQL Endpoints
- **Endpoint**: `GET /workspaces/{workspaceId}/sqlEndpoints`
- **Status**: ❓ Status TBD - Research Needed
- **Description**: Returns generic SQL endpoints in workspace (fallback for unified discovery)
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
- **Response Structure** (Expected):
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "connectionString": "string"
      }
    ]
  }
  ```
- **Notes**:
  - **Research Needed**: Verify endpoint exists and functionality
  - May return aggregated view of all SQL-capable resources
  - Likely returns less detailed metadata than type-specific endpoints
  - Use as fallback only if type-specific endpoints unavailable

---

## Items API (Universal)

### List Items
- **Endpoint**: `GET /workspaces/{workspaceId}/items`
- **Status**: ✅ Verified (Partial)
- **Description**: Universal endpoint for listing workspace items with optional type filtering
- **Path Parameters**:
  - `workspaceId`: Workspace ID (UUID)
- **Query Parameters**:
  - `type` (optional): Filter by item type
    - Supported values: `Lakehouse`, `Warehouse`, `MirroredDatabase`, `Report`, `Notebook`, `Dashboard`, etc.
  - `$top` (optional): Maximum number of results (default varies)
  - `$skip` (optional): Number of results to skip (pagination)
- **Response Structure**:
  ```json
  {
    "value": [
      {
        "id": "string (UUID)",
        "displayName": "string",
        "type": "string",
        "workspaceId": "string (UUID)",
        "description": "string (optional)"
      }
    ],
    "continuationToken": "string (optional, for pagination)"
  }
  ```
- **Notes**:
  - Serves as fallback when type-specific endpoints unavailable
  - Returns limited metadata; use type-specific detail endpoints for full information
  - Pagination via `continuationToken` (not traditional offset-based)
  - Useful for exploratory discovery when API surface unknown

---

## Authentication & Scopes

### Required Scopes
- **Default Scope**: `.default` (includes all necessary scopes for Fabric APIs)
- **Additional Scopes** (if required):
  - `https://api.fabric.microsoft.com/.default`
  - `Workspace.Read.All` (delegated)
  - `Item.Read.All` (delegated)

### Token Format
- **Type**: OAuth 2.0 Bearer token
- **Acquisition**: Via MSAL (see `fabric_auth.py`)
- **Header**: `Authorization: Bearer <token>`
- **TTL**: Typically 3600 seconds (1 hour)
- **Caching**: Implemented in `InteractiveAuthProvider` (file: `~/.fabric_mcp_token_cache.json`)

---

## Error Handling

### Common HTTP Status Codes
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters or malformed request
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: Insufficient permissions for resource
- `404 Not Found`: Resource does not exist or endpoint unavailable
- `429 Too Many Requests`: Rate limit exceeded (respect `Retry-After` header)
- `500 Internal Server Error`: Server-side error

### Error Response Structure
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": [
      {
        "code": "string",
        "message": "string"
      }
    ]
  }
}
```

---

## Rate Limiting

### Known Limits
- **Default**: Rate limit headers typically included in response (`X-RateLimit-*`)
- **Retry Strategy**: Exponential backoff with `Retry-After` header
- **Implementation**: httpx client in `fabric_api_client.py` should handle transparently

### Best Practices
- Respect `Retry-After` headers
- Implement jitter in backoff calculations
- Parallel requests acceptable but monitor for rate limit responses
- Cache responses when possible to minimize API calls

---

## Data Types & Formats

### UUID Format
- Standard 8-4-4-4-12 format (e.g., `931b4b7f-31c7-4710-bbe3-ec107b00c869`)
- Used for all resource IDs

### DateTime Format
- ISO 8601 format (e.g., `2024-12-05T14:30:00Z`)
- Always UTC timezone
- May include milliseconds: `2024-12-05T14:30:00.123Z`

### Connection String Format
- SQL Server connection string
- Example: `Server=xyz.datawarehouse.fabric.microsoft.com;Database=SalesLakehouse;`
- Contains server hostname and database name
- Authentication handled separately via token

---

## API Usage Examples

See implementation in:
- `fabric_api_client.py`: Generic REST client wrapper
- `fabric_mcp_service.py`: Service layer with API calls
- `main.py`: MCP tool definitions

---

## Known Issues & Limitations

### SQLDemo Workspace
- **Issue**: Hidden warehouse(s) - warehouses exist but cannot be discovered with current tooling
- **Impact**: `list_lakehouses` shows only lakehouses; warehouses not returned
- **Status**: Being addressed by `unified-analytical-store-discovery.md` feature

### API Stability
- Fabric APIs are evolving; endpoints may change or be deprecated
- Response structures may vary between regions or preview versions
- Not all endpoints documented in official Microsoft Learn

### Response Structure Variance
- Different endpoint types return inconsistent field locations
- Lakehouse SQL endpoint in `properties.sqlEndpointProperties.connectionString`
- Warehouse SQL endpoint location TBD (may differ)
- Items API returns minimal metadata

---

## References

### External Documentation
- [Microsoft Fabric API Documentation](https://learn.microsoft.com/en-us/fabric/api/)
- [Lakehouse API Reference](https://learn.microsoft.com/en-us/rest/api/fabric/lakehouse)
- [Warehouse Documentation](https://learn.microsoft.com/en-us/fabric/data-warehouse/)
- [Mirrored Database Preview](https://learn.microsoft.com/en-us/fabric/database/mirrored-database/)
- [OAuth 2.0 Bearer Tokens](https://tools.ietf.org/html/rfc6750)

### Internal Documentation
- `docs/3-dual-authentication-system.md`: Authentication implementation details
- `features/unified-analytical-store-discovery.md`: Multi-store discovery design

---

## Contribution Notes

When adding new API information:
1. Include endpoint URL, HTTP method, and verification status
2. Document path parameters, query parameters, and request body (if applicable)
3. Provide sample response JSON with all possible fields
4. Note any known limitations or edge cases
5. Update status as `✅ Verified`, `⚠️ Partial`, or `❓ TBD`
6. Reference implementation location if API is already used in codebase

---

**Status Summary**:
- ✅ Verified & Implemented: Workspaces, Lakehouses (list & detail), Items API
- ⚠️ Partial Coverage: Warehouses (discovery method unclear), SQL Endpoints (untested)
- ❓ Research Needed: Warehouse details, Mirrored Databases, Endpoint availability

