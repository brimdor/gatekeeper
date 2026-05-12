"""Dynamic FastAPI router mounting module sub-routers."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request

from gatekeeper.auth import validate_api_key
from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.config import settings
from gatekeeper.db import async_session
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import get_loaded_modules, load_enabled_modules
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def create_api_router() -> APIRouter:
    """Create the main API router, mounting module sub-routers for all enabled modules."""
    router = APIRouter(prefix="/api/v1")

    # Load enabled modules
    enabled = []
    if settings.drive_enabled:
        enabled.append("drive")
    if settings.gmail_enabled:
        enabled.append("gmail")
    if settings.calendar_enabled:
        enabled.append("calendar")

    # If no modules explicitly enabled, don't mount any routes
    if not enabled:
        logger.info("No modules enabled — API router will have no routes")
        return router

    modules = load_enabled_modules(enabled)

    for module in modules:
        sub_router = APIRouter(prefix=f"/{module.name}", tags=[module.display_name])

        for route in module.get_routes():
            # Convert route_id to URL path (e.g., "gmail.messages.list" -> "/messages/list")
            parts = route.route_id.split(".", 1)
            if len(parts) > 1:
                path = f"/{parts[1].replace('.', '/')}"
            else:
                path = f"/{parts[0]}"

            # Create the endpoint function dynamically
            _make_endpoint(sub_router, module.name, route.route_id, path, route.method, route.description)

        router.include_router(sub_router)
        logger.info(f"Mounted API routes for module: {module.name}")

    return router


def _make_endpoint(
    router: APIRouter,
    module_name: str,
    route_id: str,
    path: str,
    method: str,
    description: str,
):
    """Create a dynamic endpoint for a route."""
    if method == "GET":
        @router.get(path, summary=description)
        async def endpoint(
            request: Request,
            key: ApiKey = Depends(validate_api_key),
        ):
            from gatekeeper.db import get_session
            from gatekeeper.auth import get_db_session

            async for session in get_db_session():
                proxy = GoogleProxy(session)
                # Collect query params
                params = dict(request.query_params)
                return await proxy.call_google(
                    module_name=module_name,
                    route_id=route_id,
                    params=params,
                    api_key_record=key,
                    request_path=str(request.url.path),
                    request_method=request.method,
                )

    elif method == "POST":
        @router.post(path, summary=description)
        async def endpoint(
            request: Request,
            key: ApiKey = Depends(validate_api_key),
        ):
            from gatekeeper.db import get_db_session

            async for session in get_db_session():
                proxy = GoogleProxy(session)
                try:
                    params = await request.json()
                except Exception:
                    params = dict(request.query_params)
                return await proxy.call_google(
                    module_name=module_name,
                    route_id=route_id,
                    params=params,
                    api_key_record=key,
                    request_path=str(request.url.path),
                    request_method=request.method,
                )

    elif method == "PATCH":
        @router.patch(path, summary=description)
        async def endpoint(
            request: Request,
            key: ApiKey = Depends(validate_api_key),
        ):
            from gatekeeper.db import get_db_session

            async for session in get_db_session():
                proxy = GoogleProxy(session)
                try:
                    params = await request.json()
                except Exception:
                    params = {}
                return await proxy.call_google(
                    module_name=module_name,
                    route_id=route_id,
                    params=params,
                    api_key_record=key,
                    request_path=str(request.url.path),
                    request_method=request.method,
                )

    elif method == "DELETE":
        @router.delete(path, summary=description)
        async def endpoint(
            request: Request,
            key: ApiKey = Depends(validate_api_key),
        ):
            from gatekeeper.db import get_db_session

            async for session in get_db_session():
                proxy = GoogleProxy(session)
                params = dict(request.query_params)
                return await proxy.call_google(
                    module_name=module_name,
                    route_id=route_id,
                    params=params,
                    api_key_record=key,
                    request_path=str(request.url.path),
                    request_method=request.method,
                )