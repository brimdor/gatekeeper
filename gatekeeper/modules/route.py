"""Route definition — describes a single proxied Google API route."""

from __future__ import annotations

from typing import Any

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
    # Parameters that must be sent as URL query params (not JSON body).
    # Required for Google APIs where certain params (e.g. addParents/removeParents
    # on drive.files.update) are only accepted as query parameters.
    query_params: list[str] = []
    # Whether this route returns a binary response that requires special handling
    # (e.g. file downloads from Google Drive). When True, the proxy streams the
    # response instead of parsing it as JSON and optionally base64-encodes it
    # if it is below the max_inline_size_mb policy threshold.
    binary_response: bool = False
    # Whether this route requires multipart/related body construction for file
    # uploads. When True, the proxy builds a multipart body from metadata JSON
    # plus raw file bytes instead of sending a JSON body.
    multipart_upload: bool = False
    # Default policy config
    default_policy: dict[str, Any] = {}
    # Whether this route is enabled by default
    enabled_by_default: bool = True
    # Optional per-route base URL. When set, the proxy uses it instead of the
    # global GOOGLE_API_BASE for URL construction. Required for Google APIs
    # that don't live on www.googleapis.com (Sheets, Docs, Slides).
    # Examples: "https://sheets.googleapis.com", "https://docs.googleapis.com",
    # "https://slides.googleapis.com". Defaults to None (use GOOGLE_API_BASE).
    base_url: str | None = None
