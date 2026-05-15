"""Google API proxy — policy-enforced request forwarding."""

from __future__ import annotations

import json
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

        # Inject schema defaults for params the caller didn't provide.
        # This must happen BEFORE policy transforms so that defaults can be
        # capped/overridden by policy (e.g., maxResults capping pageSize).
        schema_props = route.input_schema.get("properties", {})
        for schema_key, schema_val in schema_props.items():
            if "default" in schema_val and schema_key not in params:
                params[schema_key] = schema_val["default"]

        # Apply request transforms (policy caps, overrides, etc.)
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

        # Coerce array-type parameters that arrive as strings back to lists.
        # MCP clients may stringify JSON arrays in tool arguments, and the
        # direct REST API can also receive strings for array fields.
        # Uses the route's input_schema to identify which params should be arrays.
        schema_props = route.input_schema.get("properties", {})
        # Map snake_case schema keys to their camelCase counterparts
        schema_key_map = {}
        for schema_key, schema_val in schema_props.items():
            parts = schema_key.split("_")
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
            schema_key_map[camel] = schema_val

        for key in list(normalized_params.keys()):
            value = normalized_params[key]
            # Check if this param is defined as array type in the schema
            prop_schema = schema_key_map.get(key, {})
            if prop_schema.get("type") == "array" and isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        normalized_params[key] = parsed
                    # If parsed isn't a list, leave as-is (let Google API reject it)
                except (json.JSONDecodeError, TypeError):
                    # Not valid JSON — leave as string and let the API reject it
                    pass

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

        # Gmail filter routes need special body transformation:
        # The Gmail API expects nested {criteria: {...}, action: {...}} but
        # the proxy receives flat parameters. Restructure before sending.
        if route_id in ("gmail.filters.create", "gmail.filters.update"):
            normalized_params = self._restructure_filter_body(normalized_params)

        # Drive shortcut creation: when mimeType is shortcut and shortcutTargetId
        # is provided, construct the shortcutDetails object that the Drive API
        # requires. Without this, creating a shortcut returns 400 Bad Request.
        if route_id == "drive.files.create" and "shortcutTargetId" in normalized_params:
            shortcut_details = {"targetId": normalized_params.pop("shortcutTargetId")}
            if "shortcutTargetMimeType" in normalized_params:
                shortcut_details["targetMimeType"] = normalized_params.pop("shortcutTargetMimeType")
            normalized_params["shortcutDetails"] = shortcut_details

        # Some routes (e.g. drive.files.update) require certain params to be
        # sent as URL query parameters rather than in the JSON body.
        # Google's API silently ignores addParents/removeParents if they're
        # in the PATCH body — they MUST be query params.
        query_params = {}
        body_params = {}
        for key, value in normalized_params.items():
            if key in route.query_params:
                query_params[key] = value
            else:
                body_params[key] = value

        # Make the request
        headers = {"Authorization": f"Bearer {creds.token}"}

        try:
            async with httpx.AsyncClient() as client:
                if route.method == "GET":
                    # For GET requests, all params go as query params (no body)
                    all_query = {**query_params, **body_params}
                    response = await client.get(
                        url, params=all_query, headers=headers
                    )
                elif route.method == "POST":
                    response = await client.post(
                        url, json=body_params, headers=headers
                    )
                elif route.method == "PATCH":
                    response = await client.patch(
                        url,
                        params=query_params or None,
                        json=body_params or None,
                        headers=headers,
                    )
                elif route.method == "DELETE":
                    response = await client.delete(
                        url, params=query_params or None, headers=headers
                    )
                elif route.method == "PUT":
                    response = await client.put(
                        url, json=body_params, headers=headers
                    )
                else:
                    response = await client.request(
                        route.method,
                        url,
                        params=query_params or None,
                        json=body_params or None,
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

    @staticmethod
    def _restructure_filter_body(params: dict[str, Any]) -> dict[str, Any]:
        """Restructure flat filter params into Gmail's nested format.

        The Gmail filters.create and filters.update APIs expect a body like:
        {
            "criteria": {"query": "...", "from": "...", ...},
            "action": {"addLabelIds": [...], "forward": "...", ...}
        }

        But the proxy receives flat parameters from MCP/REST callers:
        {"query": "...", "label_ids": [...], "forward": "...", ...}

        This method splits flat params into the nested structure.
        """
        # Filter criteria fields (as accepted by the Gmail API)
        criteria_fields = {
            "query",
            "from",
            "to",
            "subject",
            "negatedQuery",
            "hasAttachment",
            "excludeChats",
            "size",
            "sizeComparison",
        }
        # Action fields
        action_fields = {
            "addLabelIds",
            "removeLabelIds",
            "forward",
            "archive",
            "delete",
            "markAsImportant",
            "markAsRead",
            "star",
        }

        # Map our snake_case names to Gmail's camelCase action names
        snake_to_camel_action = {
            "label_ids": "addLabelIds",
            "mark_as_read": "markAsRead",
            "mark_as_important": "markAsImportant",
            "archive": "archive",
            "delete": "delete",
            "forward": "forward",
            "star": "star",
        }

        body: dict[str, Any] = {}

        # Also preserve any already-nested structures passed through
        if "criteria" in params or "action" in params:
            return params

        criteria: dict[str, Any] = {}
        action: dict[str, Any] = {}

        for key, value in params.items():
            # Skip path params that were already used
            if key in ("filterId", "userId"):
                continue

            # Direct camelCase criteria match
            if key in criteria_fields:
                criteria[key] = value
            # Direct camelCase action match
            elif key in action_fields:
                action[key] = value
            # Map snake_case action names
            elif key in snake_to_camel_action:
                action[snake_to_camel_action[key]] = value
            # labelIds → addLabelIds (common snake_case variant)
            elif key == "labelIds":
                action["addLabelIds"] = value

        if criteria:
            body["criteria"] = criteria
        if action:
            body["action"] = action

        # If neither criteria nor action was populated, just return params as-is
        # (let Google API reject with a clear error)
        if not body:
            return params

        return body
