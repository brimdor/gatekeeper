"""Route definition — describes a single proxied Google API route."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class RouteDef(BaseModel):
    """Definition of a gateway route that proxies to a Google API."""

    # Unique route identifier (e.g. "gmail.messages.list")
    route_id: str
    # HTTP method for the proxied call
    method: str = "GET"
    # Google API path this proxies (e.g. "/gmail/v1/users/me/messages")
    google_path: str
    # Human-readable description
    description: str = ""
    # Pydantic-style input schema for MCP tool definition
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    # Default policy config
    default_policy: dict[str, Any] = {}
    # Whether this route is enabled by default
    enabled_by_default: bool = True