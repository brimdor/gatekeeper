"""MCP server setup — dynamic tool registration from enabled routes."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI

from gatekeeper.config import settings
from gatekeeper.db import async_session
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.policy import PolicyEngine

logger = logging.getLogger(__name__)


def create_mcp_server(app: FastAPI) -> "MCPServer":
    """Create an MCP server instance that exposes enabled routes as tools.
    
    The server dynamically discovers enabled routes from the database,
    so admin toggles are reflected immediately without restart.
    """
    try:
        from mcp.server import MCPServer
        from mcp.server.sse import SseTransport
    except ImportError:
        logger.error("MCP package not installed. Install with: pip install mcp")
        return None

    mcp = MCPServer("gatekeeper")

    @mcp.list_tools()
    async def list_tools() -> list[dict[str, Any]]:
        """List all enabled routes as MCP tools."""
        from gatekeeper.modules import load_module, AVAILABLE_MODULES

        tools = []
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
                        tools.append({
                            "name": f"{module_name}__{route.route_id.replace('.', '_')}",
                            "description": route.description,
                            "inputSchema": route.input_schema,
                        })

        return tools

    @mcp.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any], api_key: str = None) -> Any:
        """Call a tool by name, routing through the policy engine."""
        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.modules import load_module

        # Parse module and route from tool name
        # Format: "gmail__messages_list" -> module="gmail", route="gmail.messages.list"
        parts = name.split("__", 1)
        if len(parts) != 2:
            return {"error": True, "message": f"Invalid tool name: {name}"}

        module_name = parts[0]
        route_part = parts[1]
        # Convert underscores back to dots for route_id
        route_id = f"{module_name}.{route_part.replace('_', '.')}"

        # Validate API key
        if not api_key:
            return {"error": True, "message": "API key required (pass as api_key in metadata)"}

        async with async_session() as session:
            # Find the API key
            from sqlalchemy import select
            from gatekeeper.auth import validate_api_key_header

            result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))  # noqa: E712
            keys = result.scalars().all()

            import bcrypt
            key_record = None
            for k in keys:
                if api_key.startswith(k.key_prefix):
                    if bcrypt.checkpw(api_key.encode(), k.key_hash.encode()):
                        key_record = k
                        break

            if not key_record:
                return {"error": True, "message": "Invalid API key"}

            proxy = GoogleProxy(session)
            return await proxy.call_google(
                module_name=module_name,
                route_id=route_id,
                params=arguments,
                api_key_record=key_record,
                request_path=f"/mcp/{name}",
                request_method="POST",
            )

    return mcp


def mount_mcp_server(app: FastAPI) -> None:
    """Mount the MCP SSE server onto the FastAPI app."""
    mcp = create_mcp_server(app)
    if mcp is None:
        logger.warning("MCP server not created — mcp package may not be installed")
        return

    try:
        from mcp.server.sse import SseTransport

        sse = SseTransport("/mcp")

        @app.get("/mcp")
        async def mcp_sse(request):
            return await sse.handle_request(request)

        @app.post("/mcp")
        async def mcp_post(request):
            return await sse.handle_request(request)

        logger.info("MCP SSE server mounted at /mcp")
    except Exception as e:
        logger.error(f"Failed to mount MCP server: {e}")