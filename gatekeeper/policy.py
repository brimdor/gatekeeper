"""Policy engine — route-level allow/deny and request/response transformation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.models import RoutePolicy

logger = logging.getLogger(__name__)


@dataclass
class PolicyDecision:
    """Result of a policy check for a route."""

    allowed: bool
    reason: str = ""
    policy_config: dict[str, Any] = field(default_factory=dict)


class PolicyEngine:
    """Evaluate route policies for incoming requests."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_route(
        self,
        module: str,
        route: str,
        api_key_permissions: str = "*",
    ) -> PolicyDecision:
        """Check if a route is allowed for a given API key.

        Args:
            module: Module name (e.g., "gmail")
            route: Route ID (e.g., "gmail.messages.list")
            api_key_permissions: Comma-separated module list or "*" for all

        Returns:
            PolicyDecision with allowed/denied status and policy config.
        """
        # Check module permission
        if api_key_permissions != "*":
            allowed_modules = [m.strip() for m in api_key_permissions.split(",")]
            if module not in allowed_modules:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Key not authorized for module: {module}",
                )

        # Look up route policy
        result = await self.session.execute(
            select(RoutePolicy).where(
                RoutePolicy.module == module,
                RoutePolicy.route == route,
            )
        )
        policy = result.scalar_one_or_none()

        if policy is None:
            # No explicit policy = default deny
            return PolicyDecision(
                allowed=False,
                reason=f"No policy defined for {route}",
            )

        if not policy.enabled:
            return PolicyDecision(
                allowed=False,
                reason=f"Route {route} is disabled",
            )

        # Parse policy config
        try:
            config = json.loads(policy.policy_config) if policy.policy_config else {}
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in policy config for {route}")
            config = {}

        return PolicyDecision(allowed=True, policy_config=config)

    def apply_request_transforms(
        self, params: dict[str, Any], policy_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply policy-based limits to request parameters.

        Transforms:
        - Cap maxResults/pageSize/max_results to policy limit
        - Filter labelIds to allowed_labels set
        - Add forced query parameters from query_filter
        """
        transformed = dict(params)

        # Cap result limits
        if "max_results" in policy_config:
            limit = policy_config["max_results"]
            for key in ("maxResults", "max_results", "pageSize", "page_size"):
                if key in transformed and isinstance(transformed[key], int):
                    if transformed[key] > limit:
                        transformed[key] = limit

        # Filter allowed labels
        if "allowed_labels" in policy_config:
            if "labelIds" in transformed and isinstance(transformed["labelIds"], list):
                allowed = set(policy_config["allowed_labels"])
                transformed["labelIds"] = [
                    label for label in transformed["labelIds"] if label in allowed
                ]

        # Apply excluded labels
        if "exclude_labels" in policy_config:
            if "labelIds" in transformed and isinstance(transformed["labelIds"], list):
                excluded = set(policy_config["exclude_labels"])
                transformed["labelIds"] = [
                    label for label in transformed["labelIds"] if label not in excluded
                ]

        # Add forced query filter
        if "query_filter" in policy_config:
            existing_q = transformed.get("q", "")
            forced_q = policy_config["query_filter"]
            if existing_q:
                transformed["q"] = f"{forced_q} AND {existing_q}"
            else:
                transformed["q"] = forced_q

        return transformed

    def apply_response_filter(
        self, response_data: dict[str, Any], policy_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Strip or redact fields from Google API responses per policy.

        Transforms:
        - Remove blocked_fields
        - Cap array lengths per max_items
        """
        if not policy_config:
            return response_data

        result = dict(response_data)

        # Strip blocked fields
        if "blocked_fields" in policy_config:
            for field_name in policy_config["blocked_fields"]:
                result.pop(field_name, None)

        # Cap array lengths
        if "max_items" in policy_config:
            for key, limit in policy_config["max_items"].items():
                if key in result and isinstance(result[key], list):
                    result[key] = result[key][:limit]

        return result