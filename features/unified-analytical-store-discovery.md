# Unified Analytical Store Discovery (Design Notes)

## Context
- Current MCP server only exposes `list_lakehouses` which returns lakehouse resources exclusively
- **Warehouses, mirrored databases, and other SQL-capable stores exist but are invisible** to current tooling
- Users must know ahead of time which type of analytical store they're looking for
- Multiple discovery APIs must be called separately, then correlation logic applied to get SQL endpoints
- Example: SQLDemo workspace contains at least one warehouse that current tools cannot discover

## Problem Statement
The current discovery workflow is fragmented and type-specific:
1. Call `list_lakehouses` → only see lakehouses
2. Call `list_warehouses` (if it existed) → only see warehouses
3. Call separate detail APIs to get SQL endpoint information
4. Manual correlation and aggregation by user/application

**This creates a circular blindspot**: We can't discover resources we don't know exist, and we can't build tools for resources we can't discover.

## Goal
Create a **unified analytical store discovery tool** that returns all SQL-capable Fabric resources in a workspace with one call, including:
- Resource type identification (lakehouse, warehouse, mirrored database, etc.)
- SQL endpoint information (server, database, connection string)
- Consistent structure regardless of source type
- Simplified discovery workflow without type-specific assumptions

## High-Level Requirements

### Input Parameters
```python
workspace_id: str  # Required - target workspace
include_types: Optional[List[str]] = None  # Optional filter: ["lakehouse", "warehouse", "mirrored_database"]
```

### Output Structure
```json
{
  "workspace_id": "931b4b7f-31c7-4710-bbe3-ec107b00c869",
  "analytical_stores": [
    {
      "id": "996dc810-5e24-4499-b493-d6d9c533b808",
      "name": "SalesLakehouse",
      "type": "lakehouse",
      "description": "Sales data lakehouse",
      "sql_endpoint": {
        "server": "xyz.datawarehouse.fabric.microsoft.com",
        "database": "SalesLakehouse",
        "connection_string": "Server=xyz.datawarehouse.fabric.microsoft.com;Database=SalesLakehouse;..."
      },
      "properties": {
        "created_date": "2024-01-15T10:30:00Z",
        "modified_date": "2024-12-01T14:22:00Z"
      }
    },
    {
      "id": "abc12345-...",
      "name": "SalesWarehouse",
      "type": "warehouse",
      "description": "Sales analytics warehouse",
      "sql_endpoint": {
        "server": "xyz.datawarehouse.fabric.microsoft.com",
        "database": "SalesWarehouse",
        "connection_string": "Server=xyz..."
      },
      "properties": {
        "created_date": "2024-02-20T09:15:00Z",
        "modified_date": "2024-11-28T16:45:00Z"
      }
    }
  ],
  "discovered_types": ["lakehouse", "warehouse"],
  "metadata": {
    "total_count": 2,
    "by_type": {
      "lakehouse": 1,
      "warehouse": 1
    }
  },
  "errors": []  // Partial failure handling - some API calls may fail
}
```

### Functional Requirements
1. **Multi-Source Aggregation**: Query multiple Fabric REST APIs and merge results
2. **Type Detection**: Identify resource type and include in output
3. **SQL Endpoint Extraction**: Parse connection strings and expose server/database clearly
4. **Deduplication**: Handle cases where same resource appears in multiple API responses
5. **Partial Failure Handling**: Continue if some APIs fail (permissions, rate limits, etc.)
6. **Optional Filtering**: Support `include_types` parameter to filter by resource type
7. **Consistent Format**: Normalize heterogeneous API responses to unified structure
8. **Auth Support**: Work with both interactive and service principal authentication
9. **Performance**: Parallel API calls where possible to minimize latency

## Proposed Architecture

### Tool Definition (main.py)
```python
@mcp.tool()
async def list_analytical_stores(
    workspace_id: str,
    include_types: Optional[str] = None  # Comma-separated: "lakehouse,warehouse"
) -> dict[str, Any]:
    """Discover all analytical stores with SQL endpoints in a workspace.
    
    Returns unified list of lakehouses, warehouses, mirrored databases, and other
    SQL-capable Fabric resources. Simplifies discovery by eliminating need for
    type-specific API calls.
    
    Use this when:
    - Discovering what analytical stores exist in a workspace
    - Need SQL endpoints without knowing resource types ahead of time
    - Building connection lists for analytics tools
    - Exploring workspace capabilities
    
    Args:
        workspace_id: Workspace ID (from list_workspaces)
        include_types: Optional filter (e.g., "lakehouse,warehouse")
    
    Returns:
        dict with "analytical_stores" array containing all discovered resources
    """
    return await service.list_analytical_stores(workspace_id, include_types)
```

### Service Layer (fabric_mcp_service.py)
```python
async def list_analytical_stores(
    self,
    workspace_id: str,
    include_types: Optional[str] = None
) -> dict[str, Any]:
    """Discover all analytical stores with SQL endpoints in workspace.
    
    Aggregates from multiple Fabric APIs:
    - /workspaces/{id}/lakehouses
    - /workspaces/{id}/warehouses  
    - /workspaces/{id}/items?type=Warehouse
    - /workspaces/{id}/sqlAnalyticsEndpoints (if applicable)
    
    Returns unified, normalized structure with SQL endpoint details.
    """
    # Parse optional filter
    type_filter = set(include_types.split(',')) if include_types else None
    
    # Parallel API calls to discover resources
    stores = []
    errors = []
    
    # Discover lakehouses (if not filtered out)
    if not type_filter or 'lakehouse' in type_filter:
        try:
            lakehouse_stores = await self._discover_lakehouses(workspace_id)
            stores.extend(lakehouse_stores)
        except Exception as e:
            errors.append({"type": "lakehouse", "error": str(e)})
    
    # Discover warehouses (if not filtered out)
    if not type_filter or 'warehouse' in type_filter:
        try:
            warehouse_stores = await self._discover_warehouses(workspace_id)
            stores.extend(warehouse_stores)
        except Exception as e:
            errors.append({"type": "warehouse", "error": str(e)})
    
    # Future: Add mirrored databases, SQL endpoints, etc.
    
    # Build metadata
    type_counts = {}
    for store in stores:
        store_type = store['type']
        type_counts[store_type] = type_counts.get(store_type, 0) + 1
    
    return {
        "workspace_id": workspace_id,
        "analytical_stores": stores,
        "discovered_types": list(type_counts.keys()),
        "metadata": {
            "total_count": len(stores),
            "by_type": type_counts
        },
        "errors": errors
    }
```

### API Helper Methods (fabric_mcp_service.py)
```python
async def _discover_lakehouses(self, workspace_id: str) -> List[dict]:
    """Discover lakehouse analytical stores with SQL endpoints."""
    data = await self.fabric_api.get(f'/workspaces/{workspace_id}/lakehouses')
    stores = []
    
    for lh in data.get('value', []):
        lakehouse_id = lh['id']
        # Get detailed info including SQL endpoint
        details = await self.fabric_api.get(
            f'/workspaces/{workspace_id}/lakehouses/{lakehouse_id}'
        )
        
        sql_props = details.get('properties', {}).get('sqlEndpointProperties', {})
        if sql_props.get('connectionString'):
            stores.append({
                "id": lakehouse_id,
                "name": details.get('displayName', lakehouse_id),
                "type": "lakehouse",
                "description": details.get('description', ''),
                "sql_endpoint": self._parse_sql_endpoint(
                    sql_props.get('connectionString'),
                    details.get('displayName')
                ),
                "properties": {
                    "created_date": details.get('createdDate'),
                    "modified_date": details.get('lastUpdatedTime')
                }
            })
    
    return stores

async def _discover_warehouses(self, workspace_id: str) -> List[dict]:
    """Discover warehouse analytical stores with SQL endpoints."""
    # Try primary warehouses API
    try:
        data = await self.fabric_api.get(f'/workspaces/{workspace_id}/warehouses')
    except Exception:
        # Fallback to items API with type filter
        data = await self.fabric_api.get(
            f'/workspaces/{workspace_id}/items',
            params={'type': 'Warehouse'}
        )
    
    stores = []
    for wh in data.get('value', []):
        warehouse_id = wh['id']
        # Get detailed info including SQL endpoint
        try:
            details = await self.fabric_api.get(
                f'/workspaces/{workspace_id}/warehouses/{warehouse_id}'
            )
        except Exception:
            # Use item details as fallback
            details = wh
        
        # Extract SQL endpoint (API response structure may vary)
        connection_string = (
            details.get('properties', {}).get('connectionString') or
            details.get('properties', {}).get('sqlEndpointProperties', {}).get('connectionString')
        )
        
        if connection_string:
            stores.append({
                "id": warehouse_id,
                "name": details.get('displayName', warehouse_id),
                "type": "warehouse",
                "description": details.get('description', ''),
                "sql_endpoint": self._parse_sql_endpoint(
                    connection_string,
                    details.get('displayName')
                ),
                "properties": {
                    "created_date": details.get('createdDate'),
                    "modified_date": details.get('lastUpdatedTime')
                }
            })
    
    return stores

def _parse_sql_endpoint(
    self,
    connection_string: str,
    database_name: str
) -> dict:
    """Parse SQL endpoint from connection string."""
    server = connection_string
    
    # Extract server address if in connection string format
    if "Server=" in connection_string:
        parts = connection_string.split(";")
        for part in parts:
            if part.startswith("Server="):
                server = part.replace("Server=", "")
                break
    
    return {
        "server": server,
        "database": database_name,
        "connection_string": connection_string
    }
```

## Fabric REST API Investigation

### APIs to Research (May Change)
1. **Lakehouses**:
   - List: `GET /v1/workspaces/{workspaceId}/lakehouses`
   - Details: `GET /v1/workspaces/{workspaceId}/lakehouses/{lakehouseId}`
   - Known to return `sqlEndpointProperties.connectionString`

2. **Warehouses**:
   - Primary: `GET /v1/workspaces/{workspaceId}/warehouses` (may not exist yet)
   - Fallback: `GET /v1/workspaces/{workspaceId}/items?type=Warehouse`
   - Details: `GET /v1/workspaces/{workspaceId}/warehouses/{warehouseId}`
   - **Status**: Need to verify API availability and response structure

3. **Mirrored Databases**:
   - List: `GET /v1/workspaces/{workspaceId}/mirroredDatabases` (TBD)
   - Fallback: `GET /v1/workspaces/{workspaceId}/items?type=MirroredDatabase`
   - **Status**: API may be in preview or not yet available

4. **SQL Analytics Endpoints** (Generic):
   - `GET /v1/workspaces/{workspaceId}/sqlEndpoints`
   - **Status**: Known to return limited metadata, use as fallback only

5. **Items API** (Universal Fallback):
   - `GET /v1/workspaces/{workspaceId}/items`
   - Query param: `?type=Lakehouse` or `?type=Warehouse` or `?type=MirroredDatabase`
   - Returns all item types but may lack SQL endpoint details

### API Discovery Strategy
1. Attempt specific resource API (e.g., `/warehouses`)
2. If 404, fallback to items API with type filter
3. For detailed info, attempt detail endpoint (e.g., `/warehouses/{id}`)
4. If detail endpoint unavailable, use item list response
5. Gracefully handle missing SQL endpoint properties

### Authentication Considerations
- Current `.default` scope should work for all APIs
- May need additional delegated permissions for interactive auth:
  - `Workspace.Read.All`
  - `Item.Read.All`
  - `SqlEndpoint.Read.All` (if it exists)
- Service principal needs appropriate API permissions configured in Azure AD

## Implementation Phases

### Phase 1: Lakehouse + Warehouse Discovery (Immediate Priority)
**Goal**: Discover the hidden warehouse in SQLDemo workspace

**Implementation**:
1. Add `_discover_lakehouses()` helper (reuse existing logic)
2. Add `_discover_warehouses()` helper (new implementation)
3. Add `list_analytical_stores()` service method
4. Add `list_analytical_stores` MCP tool
5. Test against SQLDemo to verify warehouse discovery

**Validation**:
- Verify SQLDemo returns both lakehouses AND warehouse(s)
- Confirm SQL endpoint information is correct for both types
- Test with interactive and service principal auth

**Estimated Effort**: 2-3 hours

### Phase 2: Mirrored Databases + SQL Endpoints (Future)
**Goal**: Complete coverage of all Fabric analytical stores

**Implementation**:
1. Research mirrored database API availability
2. Add `_discover_mirrored_databases()` helper
3. Add generic SQL endpoint fallback logic
4. Implement deduplication across sources
5. Add comprehensive error handling

**Validation**:
- Test against workspace with mirrored databases
- Verify deduplication logic works correctly
- Confirm partial failure handling

**Estimated Effort**: 3-4 hours

### Phase 3: Enhanced Features (Optional)
- Pagination support for large workspaces
- Caching/refresh strategies
- Health status indicators per endpoint
- Connection validation (test connectivity)
- Performance metrics (query response time estimates)

## Key Benefits

### For Users
✅ **Single Discovery Call**: One tool reveals all SQL-capable resources  
✅ **No Type Assumptions**: Don't need to know what exists beforehand  
✅ **Simplified Workflow**: Eliminate multi-step discovery process  
✅ **Complete Visibility**: See warehouses, lakehouses, and more in one view  
✅ **Consistent Format**: All stores returned in same structure  

### For Development
✅ **Future-Proof**: Easy to add new analytical store types  
✅ **Graceful Degradation**: Partial failures don't block entire discovery  
✅ **Testable**: Clear separation of concerns in helper methods  
✅ **Maintainable**: Single tool to maintain vs. multiple type-specific tools  

### For SQLDemo Workspace Specifically
**Before**: 
- Visible: 2 lakehouses (SalesLakehouse, SalesOntology_lh_...)
- Hidden: 1+ warehouse(s)

**After**:
- Visible: All analytical stores with SQL endpoints
- Unified view: Type, name, SQL endpoint in one response

## Testing Strategy

### Phase 1 Testing (Lakehouse + Warehouse)
1. **SQLDemo Workspace Test**:
   - Call `list_analytical_stores(SQLDemo_workspace_id)`
   - Verify lakehouses appear with correct SQL endpoints
   - **Verify hidden warehouse(s) now visible**
   - Confirm metadata counts match actual resources

2. **Filtering Test**:
   - Call with `include_types="lakehouse"` → only lakehouses
   - Call with `include_types="warehouse"` → only warehouses
   - Call with `include_types="lakehouse,warehouse"` → both

3. **Authentication Test**:
   - Test with interactive authentication
   - Test with service principal
   - Verify both modes work identically

4. **Error Handling Test**:
   - Test against workspace with no analytical stores
   - Test with invalid workspace_id
   - Test when API returns unexpected structure

### Phase 2 Testing (Full Coverage)
1. Workspace with mirrored databases
2. Workspace with mixed types (lakehouse + warehouse + mirrored DB)
3. Large workspace with pagination
4. Workspace where some APIs fail (partial failure scenario)

## Success Criteria
- [ ] Tool discovers lakehouses with SQL endpoints
- [ ] Tool discovers warehouses with SQL endpoints  
- [ ] Tool reveals the hidden warehouse in SQLDemo workspace
- [ ] Output structure matches specification
- [ ] Works with both authentication modes
- [ ] Partial failures handled gracefully
- [ ] Response time < 5 seconds for typical workspace (5-10 resources)
- [ ] Documentation updated (README, integration guide)
- [ ] Copilot-optimized tool description

## Future Enhancements
- Connection health checks (validate SQL endpoint accessibility)
- Capacity/performance metrics per store
- Resource tagging and filtering
- Cross-workspace discovery aggregation
- SQL endpoint connection pooling recommendations
- Automatic failover/backup endpoint detection

## Related Features
- **Dual Authentication System** (docs/3-dual-authentication-system.md) - Auth must work for all APIs
- **SQL Endpoint Discovery** (features/sql-endpoint-discovery.md) - Original design, superseded by this unified approach

## References
- [Microsoft Fabric REST API Documentation](https://learn.microsoft.com/en-us/fabric/api/)
- [Lakehouse REST API](https://learn.microsoft.com/en-us/rest/api/fabric/lakehouse)
- [Warehouse Documentation](https://learn.microsoft.com/en-us/fabric/data-warehouse/)
- [Mirrored Database Preview](https://learn.microsoft.com/en-us/fabric/database/mirrored-database/)

---

## Implementation Prompt (For Future Work)

> Implement the `list_analytical_stores` MCP tool as described in `features/unified-analytical-store-discovery.md`. Start with Phase 1 (lakehouse + warehouse discovery) to verify we can discover the hidden warehouse in SQLDemo workspace. The tool should aggregate results from multiple Fabric APIs and return a unified structure with SQL endpoint information. Ensure the implementation handles partial failures gracefully and works with both authentication modes.

---

**Last Updated**: December 5, 2025  
**Status**: Design Complete - Ready for Phase 1 Implementation  
**Priority**: High (resolves discovery blindspot and reveals hidden resources)
