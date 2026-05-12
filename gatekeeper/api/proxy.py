"""Google API proxy — policy-enforced request forwarding."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.auth import validate_api_key
from gatekeeper.google_client import credential_manager
from gatekeeper.logging import log_request
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules import load_module, get_loaded_modules
from gatekeeper.policy import PolicyEngine

logger = logging.getLogger(__name__)

# Google API base URL
GOOGLE_API_BASE = "https://www.googleapis.com"

# Module name to API service path prefix mapping
MODULE_API_MAP = {
    "drive": "/drive/v3",
    "gmail": "/gmail/v1",
    "calendar": "/calendar/v3",
}


class GoogleProxy:
    """Proxies requests to Google APIs through the policy engine."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.policy_engine = PolicyEngine(session)

    async def call_google(
        self,
        module_name: str,
        route_id: str,
        params: dict[str, Any],
        api_key_record: ApiKey,
        request_path: str = "",
        request_method: str = "GET",
    ) -> dict[str, Any]:
        """Proxy a request to Google API through the policy engine.

        1. Check policy (allow/deny)
        2. Apply request transforms
        3. Get Google credentials
        4. Call Google API
        5. Apply response filters
        6. Log to audit
        7. Return filtered response
        """
        # Check policy
        decision = await self.policy_engine.check_route(
            module_name, route_id, api_key_record.permissions
        )

        if not decision.allowed:
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=403,
                response_summary=decision.reason,
            )
            return {"error": True, "status": 403, "message": decision.reason}

        # Find the module and route
        modules = get_loaded_modules()
        module = modules.get(module_name)
        if not module:
            module = load_module(module_name)
            if not module:
                return {"error": True, "status": 404, "message": f"Module {module_name} not found"}

        route = None
        for r in module.get_routes():
            if r.route_id == route_id:
                route = r
                break

        if not route:
            return {"error": True, "status": 404, "message": f"Route {route_id} not found"}

        # Apply request transforms
        transformed_params = self.policy_engine.apply_request_transforms(
            params, decision.policy_config
        )

        # Get Google credentials
        creds = credential_manager.get_credentials()
        if not creds or not creds.token:
            return {"error": True, "status": 401, "message": "Google credentials not configured. Run 'gatekeeper auth'."}

        # Build Google API URL
        api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
        # Replace path parameters (e.g., {fileId} -> actual value)
        google_path = route.google_path
        for key, value in list(transformed_params.items()):
            placeholder = "{" + key + "}"
            if placeholder in google_path:
                google_path = google_path.replace(placeholder, str(value))
                del transformed_params[key]

        url = f"{GOOGLE_API_BASE}{api_prefix}{google_path.replace(MODULE_API_MAP.get(module_name, ''), '')}"
        # For modules that already include the full path in google_path
        if route.google_path.startswith("/"):
            url = f"{GOOGLE_API_BASE}{route.google_path}"
            # Replace path params in the full URL too
            for key, value in list(transformed_params.items()):
                placeholder = "{" + key + "}"
                if placeholder in url:
                    url = url.replace(placeholder, str(value))
                    del transformed_params[key]

        # Make the request
        headers = {"Authorization": f"Bearer {creds.token}"}

        try:
            async with httpx.AsyncClient() as client:
                if route.method == "GET":
                    response = await client.get(url, params=transformed_params, headers=headers)
                elif route.method == "POST":
                    response = await client.post(url, json=transformed_params, headers=headers)
                elif route.method == "PATCH":
                    response = await client.patch(url, json=transformed_params, headers=headers)
                elif route.method == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    response = await client.request(route.method, url, json=transformed_params, headers=headers)

            # Parse response
            try:
                response_data = response.json()
            except Exception:
                response_data = {"raw_response": response.text}

            # Apply response filters
            if isinstance(response_data, dict):
                response_data = self.policy_engine.apply_response_filter(
                    response_data, decision.policy_config
                )

            # Log successful request
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=response.status_code,
                response_summary=str(response_data)[:200] if response_data else None,
            )

            return response_data

        except httpx.HTTPError as e:
            logger.error(f"Google API request failed: {e}")
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=502,
                response_summary=f"HTTP error: {str(e)[:150]}",
            )
            return {"error": True, "status": 502, "message": f"Google API request failed: {e}"}

        except Exception as e:
            logger.error(f"Unexpected error in proxy: {e}")
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=500,
                response_summary=f"Internal error: {str(e)[:150]}",
            )
            return {"error": True, "status": 500, "message": f"Internal error: {e}"}