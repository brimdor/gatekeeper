"""Google API proxy — policy-enforced request forwarding."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.google_client import credential_manager
from gatekeeper.logging import log_request
from gatekeeper.models import ApiKey
from gatekeeper.modules import get_loaded_modules, load_module
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
    ) -> JSONResponse:
        """Proxy a request to Google API through the policy engine.

        1. Check policy (allow/deny)
        2. Apply request transforms
        3. Get Google credentials
        4. Call Google API
        5. Apply response filters
        6. Log to audit
        7. Return filtered response with correct HTTP status code

        Returns a JSONResponse with the appropriate HTTP status code.
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
            return JSONResponse(
                status_code=403,
                content={"error": True, "status": 403, "message": decision.reason},
            )

        # Find the module and route
        modules = get_loaded_modules()
        module = modules.get(module_name)
        if not module:
            module = load_module(module_name)
            if not module:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": True,
                        "status": 404,
                        "message": f"Module {module_name} not found",
                    },
                )

        route = None
        for r in module.get_routes():
            if r.route_id == route_id:
                route = r
                break

        if not route:
            return JSONResponse(
                status_code=404,
                content={"error": True, "status": 404, "message": f"Route {route_id} not found"},
            )

        # Apply request transforms
        transformed_params = self.policy_engine.apply_request_transforms(
            params, decision.policy_config
        )

        # Get Google credentials
        creds = credential_manager.get_credentials()
        if not creds or not creds.token:
            return JSONResponse(
                status_code=401,
                content={
                    "error": True,
                    "status": 401,
                    "message": ("Google credentials not configured. Run 'gatekeeper auth'."),
                },
            )

        # Build Google API URL
        # Normalize param keys: snake_case → camelCase to match google_path placeholders
        # e.g., "file_id" → "fileId", "calendar_id" → "calendarId"
        normalized_params = {}
        for key, value in transformed_params.items():
            parts = key.split("_")
            camel_key = parts[0] + "".join(p.capitalize() for p in parts[1:])
            normalized_params[camel_key] = value

        # Replace path parameters (e.g., {calendarId} -> actual value) in google_path
        google_path = route.google_path
        for key, value in list(normalized_params.items()):
            placeholder = "{" + key + "}"
            if placeholder in google_path:
                google_path = google_path.replace(placeholder, str(value))
                del normalized_params[key]

        # Construct the final URL
        if route.google_path.startswith("/"):
            # google_path already includes full API path (e.g., /calendar/v3/...)
            url = f"{GOOGLE_API_BASE}{google_path}"
        else:
            # Relative path — prepend the module API prefix
            api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
            url = f"{GOOGLE_API_BASE}{api_prefix}/{google_path}"

        # Remove path params from normalized_params — remaining ones are query/body params
        # (path params were already extracted and substituted above)

        # Make the request
        headers = {"Authorization": f"Bearer {creds.token}"}

        try:
            async with httpx.AsyncClient() as client:
                if route.method == "GET":
                    response = await client.get(url, params=normalized_params, headers=headers)
                elif route.method == "POST":
                    response = await client.post(url, json=normalized_params, headers=headers)
                elif route.method == "PATCH":
                    response = await client.patch(url, json=normalized_params, headers=headers)
                elif route.method == "DELETE":
                    response = await client.delete(url, headers=headers)
                elif route.method == "PUT":
                    response = await client.put(url, json=normalized_params, headers=headers)
                else:
                    response = await client.request(
                        route.method,
                        url,
                        json=normalized_params,
                        headers=headers,
                    )

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

            # Return with the Google API's status code
            return JSONResponse(status_code=response.status_code, content=response_data)

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
            return JSONResponse(
                status_code=502,
                content={
                    "error": True,
                    "status": 502,
                    "message": f"Google API request failed: {e}",
                },
            )

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
            return JSONResponse(
                status_code=500,
                content={"error": True, "status": 500, "message": f"Internal error: {e}"},
            )
