"""SSE transport configuration for MCP server.

The transport is handled directly in __init__.py via FastMCP.sse_app(),
which creates a Starlette application with SSE and message endpoints.

This file is kept for future transport-level configuration overrides
(e.g. custom security settings, rate limiting middleware, etc.).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Future: custom TransportSecuritySettings can be constructed here
# and passed to FastMCP when creating the server instance.  For now
# the defaults (DNS rebinding protection on localhost) are sufficient.