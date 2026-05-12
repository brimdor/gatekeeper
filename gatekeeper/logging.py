"""Audit logging — write request audit trail to SQLite."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.db import async_session
from gatekeeper.models import AuditLog

logger = logging.getLogger(__name__)


async def log_request(
    api_key_prefix: str,
    module: str,
    route: str,
    method: str,
    path: str,
    status_code: int,
    response_summary: Optional[str] = None,
) -> None:
    """Log a gateway request to the audit trail.

    Creates an AuditLog row in the database. Truncates response_summary
    to 200 chars. Catches and logs DB errors without failing the request.
    """
    try:
        async with async_session() as session:
            entry = AuditLog(
                api_key_prefix=api_key_prefix,
                module=module,
                route=route,
                method=method,
                path=path,
                status_code=status_code,
                response_summary=(response_summary[:200] if response_summary else None),
            )
            session.add(entry)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to log audit entry: {e}")