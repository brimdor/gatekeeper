"""Dynamic FastAPI router mounting module sub-routers.

All module routes are always registered at startup. Route enable/disable is
controlled dynamically through the policy engine (RoutePolicy table in the DB),
not by which modules are "mounted". This means toggling a route in the admin UI
takes effect immediately without a server restart.

The settings.DRIVE_ENABLED / settings.GMAIL_ENABLED / settings.CALENDAR_ENABLED
flags control which Google OAuth scopes are requested during authentication —
they do NOT control which REST API routes exist.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.auth import validate_api_key
from gatekeeper.models import ApiKey
from gatekeeper.modules import AVAILABLE_MODULES, load_module

logger = logging.getLogger(__name__)


def create_api_router() -> APIRouter:
    """Create the main API router, mounting module sub-routers for ALL modules.

    All routes are always registered. Enable/disable is handled dynamically
    by the policy engine checking the RoutePolicy table in the DB on each
    request — so admin toggles take effect immediately without a restart.
    """
    router = APIRouter(prefix="/api/v1")

    for module_name in AVAILABLE_MODULES:
        mod = load_module(module_name)
        if mod is None:
            continue

        sub_router = APIRouter(prefix=f"/{mod.name}", tags=[mod.display_name])

        for route in mod.get_routes():
            # Convert route_id to URL path (e.g., "gmail.messages.list" -> "/messages/list")
            parts = route.route_id.split(".", 1)
            if len(parts) > 1:
                path = f"/{parts[1].replace('.', '/')}"
            else:
                path = f"/{parts[0]}"

            # Create the endpoint function dynamically
            _make_endpoint(
                sub_router,
                mod.name,
                route.route_id,
                path,
                route.method,
                route.description,
            )

        router.include_router(sub_router)
        logger.info(f"Mounted API routes for module: {mod.name}")

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
            from gatekeeper.auth import get_db_session

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

    elif method == "PUT":

        @router.put(path, summary=description)
        async def endpoint(
            request: Request,
            key: ApiKey = Depends(validate_api_key),
        ):
            from gatekeeper.auth import get_db_session

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
            from gatekeeper.auth import get_db_session

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
            from gatekeeper.auth import get_db_session

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
