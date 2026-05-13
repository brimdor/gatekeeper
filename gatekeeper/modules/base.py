"""Base module class — all Google Workspace modules inherit from this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gatekeeper.modules.route import RouteDef


class GoogleModule(ABC):
    """Base class for Google Workspace modules."""

    # Module metadata
    name: str = ""
    display_name: str = ""
    description: str = ""
    icon: str = ""  # Emoji or icon class

    # Google OAuth scopes this module requires
    required_scopes: list[str] = []

    @abstractmethod
    def get_routes(self) -> list[RouteDef]:
        """Return all routes this module provides."""
        ...

    def get_default_policies(self) -> dict[str, dict[str, Any]]:
        """Return default policy configs for each route.

        Returns:
            Dict mapping route_id to {enabled, config}.
        """
        routes = self.get_routes()
        return {
            route.route_id: {
                "enabled": route.enabled_by_default,
                "config": route.default_policy,
            }
            for route in routes
        }

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions derived from this module's routes.

        Each tool's name follows the pattern: {module}__{route_suffix_with_underscores}
        where route_suffix strips the leading module prefix from route_id.
        e.g., "drive.files.list" → "drive__files_list"
        """
        tools = []
        for route in self.get_routes():
            # Strip module prefix from route_id to avoid redundancy
            # e.g., "drive.files.list" → suffix "files.list" → "drive__files_list"
            route_suffix = route.route_id.split(".", 1)[1] if "." in route.route_id else route.route_id
            tools.append(
                {
                    "name": f"{self.name}__{route_suffix.replace('.', '_')}",
                    "description": route.description or f"{route.method} {route.route_id}",
                    "inputSchema": route.input_schema,
                }
            )
        return tools