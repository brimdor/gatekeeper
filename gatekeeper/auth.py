"""API key authentication middleware and admin auth dependency."""

from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.config import settings
from gatekeeper.db import async_session

api_key_header_scheme = "X-Gatekeeper-API-Key"
http_basic = HTTPBasic()


async def get_db_session() -> AsyncSession:
    """Provide an async DB session."""
    async with async_session() as session:
        yield session


async def validate_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> "ApiKey":
    """Validate the API key from the request header.
    
    Reads the X-Gatekeeper-API-Key header, finds the key by prefix match,
    verifies the bcrypt hash, and returns the ApiKey record.
    
    Raises HTTP 401 on invalid or missing keys.
    """
    from gatekeeper.models import ApiKey

    api_key = request.headers.get(api_key_header_scheme)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Gatekeeper-API-Key header",
        )

    # Find key by trying prefix match then hash verify
    result = await db.execute(select(ApiKey).where(ApiKey.is_active == True))  # noqa: E712
    keys = result.scalars().all()

    for key_record in keys:
        # Check prefix first for quick elimination
        if api_key.startswith(key_record.key_prefix):
            # Verify hash
            if bcrypt.checkpw(api_key.encode(), key_record.key_hash.encode()):
                # Update last_used_at
                from datetime import datetime, timezone

                key_record.last_used_at = datetime.now(timezone.utc)
                await db.commit()
                request.state.api_key = key_record
                return key_record

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def require_admin(
    credentials: HTTPBasicCredentials = Depends(http_basic),
) -> HTTPBasicCredentials:
    """Require HTTP Basic Auth with valid admin credentials.
    
    Raises HTTP 401 on invalid credentials.
    """
    if (
        credentials.username == settings.admin_username
        and credentials.password == settings.admin_password
    ):
        return credentials
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials",
        headers={"WWW-Authenticate": "Basic"},
    )