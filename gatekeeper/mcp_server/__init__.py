"""MCP server setup — dynamic tool registration from enabled routes.

Uses the MCP Python SDK v1.x (FastMCP) to expose enabled Gatekeeper
routes as MCP tools discoverable by AI agents over SSE transport.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI

from gatekeeper.config import settings
from gatekeeper.db import async_session
from gatekeeper.models import ApiKey
from gatekeeper.policy import PolicyEngine

logger = logging.getLogger(__name__)

# Lazy-initialised singleton
_mcp_instance: Any | None = None


def _build_transport_security() -> Any:
    """Build transport security settings that allow the configured hosts.

    The MCP SDK enables DNS rebinding protection by default, which rejects
    all requests unless ``allowed_hosts`` is configured.  We allow:
      - The host/port Gatekeeper binds to (from settings)
      - localhost variants (for local development)
      - Common Tailscale IPs (100.x.x.x)
      - Any host on the bind port (for proxies like Tailscale Serve)
    """
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = set()

    # The configured bind host/port
    hosts.add(f"{settings.host}:{settings.port}")
    # Common local addresses
    hosts.add(f"localhost:{settings.port}")
    hosts.add(f"127.0.0.1:{settings.port}")
    # Allow any hostname on the bind port (covers Tailscale, reverse proxies)
    hosts.add(f"*:{settings.port}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(hosts),
        allowed_origins=list(hosts),
    )


async def _resolve_api_key(raw_key: str) -> ApiKey | None:
    """Look up an API key by prefix+bcrypt verification.

    Returns the ApiKey record if found and active, else None.
    """
    import bcrypt
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))  # noqa: E712
        keys = result.scalars().all()
        for k in keys:
            if raw_key.startswith(k.key_prefix):
                if bcrypt.checkpw(raw_key.encode(), k.key_hash.encode()):
                    # Touch last_used_at
                    k.last_used_at = __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    )
                    await session.commit()
                    return k
    return None


def create_mcp_server() -> Any:
    """Create a FastMCP instance that exposes enabled routes as tools.

    Tools are discovered dynamically on each list_tools call so that
    admin toggles (enabling/disabling routes) take effect immediately
    without a server restart.

    Tool names follow the pattern:  {module}__{route_suffix_with_underscores}
    where route_suffix strips the leading module prefix from route_id.
    For example:  gmail.messages.list → gmail__messages_list
    drive.files.list_shared → drive__files_list_shared

    Each tool accepts all the route's input_schema parameters plus a
    required ``api_key`` string parameter for authentication.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="gatekeeper",
        instructions=(
            "Gatekeeper MCP server — a policy gateway for Google Workspace APIs. "
            "Each tool proxies a single Google API route through the policy engine. "
            "You MUST supply an ``api_key`` argument to every tool call for "
            "authentication.  Available tools depend on which routes are enabled by "
            "the administrator."
        ),
        host=settings.host,
        transport_security=_build_transport_security(),
    )

    # ------------------------------------------------------------------ #
    #  list_tools — dynamically build the tool list from the DB           #
    # ------------------------------------------------------------------ #
    @mcp._mcp_server.list_tools()
    async def list_tools(request):
        """Return MCP tools for all enabled routes."""
        from mcp.types import Tool as MCPTool

        from gatekeeper.modules import AVAILABLE_MODULES, load_module

        tools: list[MCPTool] = []

        async with async_session() as session:
            policy_engine = PolicyEngine(session)

            for module_name in AVAILABLE_MODULES:
                mod = load_module(module_name)
                if mod is None:
                    continue

                for route in mod.get_routes():
                    # Check if route is enabled via policy
                    decision = await policy_engine.check_route(module_name, route.route_id)
                    if decision.allowed:
                        # Merge the route's input_schema with api_key param
                        schema = dict(route.input_schema)
                        props = dict(schema.get("properties", {}))
                        props["api_key"] = {
                            "type": "string",
                            "description": "Gatekeeper API key for authentication",
                        }
                        required = list(schema.get("required", []))
                        required.append("api_key")

                        # Strip module prefix from route_id to avoid redundancy
                        # e.g., "gmail.messages.list" → suffix "messages.list"
                        #     → tool name "gmail__messages_list"
                        route_suffix = (
                            route.route_id.split(".", 1)[1]
                            if "." in route.route_id
                            else route.route_id
                        )
                        tool_name = f"{module_name}__{route_suffix.replace('.', '_')}"
                        tools.append(
                            MCPTool(
                                name=tool_name,
                                description=route.description or f"{route.method} {route.route_id}",
                                inputSchema={
                                    **schema,
                                    "properties": props,
                                    "required": required,
                                },
                            )
                        )

        return tools

    # ------------------------------------------------------------------ #
    #  call_tool — authenticate & proxy through the policy engine         #
    # ------------------------------------------------------------------ #
    @mcp._mcp_server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> list:
        """Call a tool by name, routing through the policy engine."""
        import mcp.types as types

        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.modules import load_module

        # Extract and validate the API key
        api_key = arguments.pop("api_key", None)
        if not api_key:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": True, "message": "API key required (pass as api_key argument)"}
                    ),
                )
            ]

        key_record = await _resolve_api_key(api_key)
        if not key_record:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "message": "Invalid API key"}),
                )
            ]

        # Parse module and route from tool name using module registry
        # Tool name format: "{module}__{route_suffix_with_underscores}"
        # e.g., "gmail__messages_list" → module="gmail",
        #     look up route starting with "gmail.messages"
        parts = name.split("__", 1)
        if len(parts) != 2:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "message": f"Invalid tool name: {name}"}),
                )
            ]

        module_name = parts[0]
        route_suffix = parts[1]

        # Look up the route by finding a matching route in the module
        # route_suffix uses underscores where the original had dots
        # e.g., "files_list_shared" matches "drive.files.list_shared"
        mod = load_module(module_name)
        if mod is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "message": f"Module {module_name} not found"}),
                )
            ]

        # Find the route by converting each route's suffix to underscore form
        # and comparing with the tool name suffix
        route_id = None
        for route in mod.get_routes():
            route_suffix_part = (
                route.route_id.split(".", 1)[1] if "." in route.route_id else route.route_id
            )
            if route_suffix_part.replace(".", "_") == route_suffix:
                route_id = route.route_id
                break

        if route_id is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": True, "message": f"Route not found for tool: {name}"}
                    ),
                )
            ]

        async with async_session() as session:
            proxy = GoogleProxy(session)
            result = await proxy.call_google(
                module_name=module_name,
                route_id=route_id,
                params=arguments,
                api_key_record=key_record,
                request_path=f"/mcp/{name}",
                request_method="POST",
            )

        # Return as MCP content
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result) if isinstance(result, dict) else str(result),
            )
        ]

    return mcp


def mount_mcp_server(app: FastAPI) -> None:
    """Mount the MCP SSE server onto the FastAPI app at /mcp.

    This creates a Starlette sub-app via FastMCP.sse_app() and mounts
    it under FastAPI so that:

      GET  /mcp/sse        → SSE endpoint (client connects here)
      POST /mcp/messages/  → message endpoint (client sends JSON-RPC here)

    The SSE transport lets remote AI agents discover and call Gatekeeper
    tools over HTTP.
    """
    global _mcp_instance

    try:
        mcp = create_mcp_server()
        _mcp_instance = mcp

        # Get the Starlette SSE app from FastMCP
        # mount_path="/mcp" makes the SSE and message paths relative to /mcp
        starlette_app = mcp.sse_app(mount_path="/mcp")

        # Mount the Starlette app as a sub-app under FastAPI
        app.mount("/mcp", starlette_app)

        logger.info("MCP SSE server mounted at /mcp")

    except ImportError as exc:
        logger.warning("MCP package not installed. Install with: pip install mcp — %s", exc)
    except Exception as exc:
        logger.error("Failed to mount MCP server: %s", exc, exc_info=True)
