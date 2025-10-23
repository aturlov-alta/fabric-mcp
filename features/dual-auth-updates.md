# Dual Authentication Support (Design Notes)

## Context
- The repository now includes `fabric_auth.py` with two providers:
  - `ServicePrincipalAuthProvider` (client-credential flow)
  - `InteractiveAuthProvider` (device code flow)
- `fabric_api_client.py` currently requests the scope `https://analysis.windows.net/powerbi/api/.default` for every call.
- `main.py` still uses an inline `FabricAPIClient` implementation that supports service principals only.
- Several MCP tools rely on Fabric REST APIs (workspaces, lakehouses, SQL metadata) and should work with either authentication mode.

## Goal
Complete the authentication refactor so that every MCP tool seamlessly uses either service principal or interactive user authentication, requesting the correct scopes for whichever provider is active.

## Current Gaps
1. **Legacy client usage in `main.py`**
   - `main.py` instantiates the old inline `FabricAPIClient` that requires `FABRIC_CLIENT_SECRET`.
   - Needs to switch to `create_auth_provider_from_env()` + the new `FabricAPIClient` class.
2. **Scope selection**
   - Service principal tokens work with `.default` scope (app-level permissions).
   - Device-code tokens require explicit delegated scopes. Current REST tools need `Workspace.Read.All`.
   - Future features (SQL endpoint discovery) will also require `SqlEndpoint.Read.All` or `Item.Read.All`.
3. **Documentation**
   - README and `.env.example` still describe service-principal-only setup.
   - Need instructions for signing in via device code and consenting to delegated scopes.

## Proposed Updates
1. **main.py**
   - Replace the inline client with:
     ```python
     from fabric_auth import create_auth_provider_from_env
     from fabric_api_client import FabricAPIClient
     
     auth_provider = create_auth_provider_from_env()
     fabric_api = FabricAPIClient(auth_provider)
     ```
   - Ensure all REST tools reference this shared `fabric_api` instance.

2. **fabric_api_client.py**
   - Allow per-provider scope selection:
     - Service principal → `SCOPES_SP = ["https://analysis.windows.net/powerbi/api/.default"]`
     - Interactive/user → `SCOPES_USER = [
         "https://analysis.windows.net/powerbi/api/Workspace.Read.All"
       ]`
   - Implementation options:
     - Add a `preferred_scopes` property to `BaseAuthProvider` subclasses.
     - Or pass a scope list into `FabricAPIClient` at construction time based on provider type.

3. **README + `.env.example`**
   - Document both authentication workflows.
   - Mention the delegated scopes needed for interactive sign-in.
   - Highlight that service principals still require the usual tenant/app configuration.

4. **Testing/Validation**
   - Verify service principal flow still works (existing functionality).
   - Sign in via device code and confirm the MCP tools (workspaces/lakehouses/SQL) function with user tokens.

## Future Coding Prompt
> Update the authentication wiring so `main.py` uses the new `FabricAPIClient` together with `create_auth_provider_from_env`, and modify `fabric_api_client.py` to request the correct scopes for service principals vs interactive users. Refresh documentation to cover both flows.

---
Use this document as the reference when picking up the authentication refactor later.
