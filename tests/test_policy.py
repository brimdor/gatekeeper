"""Comprehensive tests for the policy engine.

Tests PolicyDecision dataclass, PolicyEngine.check_route (async with DB),
request transforms, and response filters.
"""

import json
import pytest
import pytest_asyncio
from sqlalchemy import select

from gatekeeper.models import RoutePolicy
from gatekeeper.policy import PolicyDecision, PolicyEngine


# ---------------------------------------------------------------------------
# PolicyDecision dataclass
# ---------------------------------------------------------------------------

class TestPolicyDecision:
    """Tests for PolicyDecision dataclass — allowed/denied states, defaults."""

    def test_allowed_with_config(self):
        """Allowed decision carries policy config."""
        d = PolicyDecision(allowed=True, policy_config={"max_results": 50})
        assert d.allowed is True
        assert d.policy_config == {"max_results": 50}
        assert d.reason == ""

    def test_denied_with_reason(self):
        """Denied decision carries reason string."""
        d = PolicyDecision(allowed=False, reason="Route is disabled")
        assert d.allowed is False
        assert d.reason == "Route is disabled"
        assert d.policy_config == {}  # default

    def test_default_reason_is_empty(self):
        """Default reason should be empty string."""
        d = PolicyDecision(allowed=True)
        assert d.reason == ""

    def test_default_policy_config_is_empty_dict(self):
        """Default policy_config should be empty dict."""
        d = PolicyDecision(allowed=False)
        assert d.policy_config == {}

    def test_allowed_no_config(self):
        """Allowed decision with default config is empty dict."""
        d = PolicyDecision(allowed=True)
        assert d.allowed is True
        assert d.policy_config == {}

    def test_denied_with_config_still_populated(self):
        """Even denied decisions can carry policy_config (for informational purposes)."""
        d = PolicyDecision(allowed=False, reason="forbidden", policy_config={"max_results": 10})
        assert d.allowed is False
        assert d.policy_config == {"max_results": 10}

    def test_equality(self):
        """Two identical decisions should compare equal."""
        d1 = PolicyDecision(allowed=True, reason="", policy_config={"a": 1})
        d2 = PolicyDecision(allowed=True, reason="", policy_config={"a": 1})
        assert d1 == d2

    def test_inequality(self):
        """Different decisions should not compare equal."""
        d1 = PolicyDecision(allowed=True)
        d2 = PolicyDecision(allowed=False, reason="no")
        assert d1 != d2


# ---------------------------------------------------------------------------
# Request transforms (sync, no DB needed)
# ---------------------------------------------------------------------------

class TestRequestTransforms:
    """Tests for PolicyEngine.apply_request_transforms."""

    def setup_method(self):
        self.engine = PolicyEngine(session=None)  # Session not needed for transforms

    # ---- max_results capping ----

    def test_cap_maxResults(self):
        """maxResults exceeding policy limit should be capped."""
        result = self.engine.apply_request_transforms(
            {"maxResults": 200}, {"max_results": 50}
        )
        assert result["maxResults"] == 50

    def test_maxResults_below_limit_unchanged(self):
        """maxResults below limit should not change."""
        result = self.engine.apply_request_transforms(
            {"maxResults": 30}, {"max_results": 50}
        )
        assert result["maxResults"] == 30

    def test_cap_pageSize(self):
        """pageSize should be capped by max_results policy."""
        result = self.engine.apply_request_transforms(
            {"pageSize": 100}, {"max_results": 25}
        )
        assert result["pageSize"] == 25

    def test_cap_max_results_snake(self):
        """max_results (snake_case form) should also be capped."""
        result = self.engine.apply_request_transforms(
            {"max_results": 100}, {"max_results": 10}
        )
        assert result["max_results"] == 10

    def test_cap_page_size_snake(self):
        """page_size (snake_case form) should also be capped."""
        result = self.engine.apply_request_transforms(
            {"page_size": 200}, {"max_results": 50}
        )
        assert result["page_size"] == 50

    def test_multiple_result_keys_capped_together(self):
        """All four result-limit keys should be capped if present together."""
        result = self.engine.apply_request_transforms(
            {"maxResults": 200, "pageSize": 200, "max_results": 200, "page_size": 200},
            {"max_results": 25},
        )
        assert result["maxResults"] == 25
        assert result["pageSize"] == 25
        assert result["max_results"] == 25
        assert result["page_size"] == 25

    def test_max_results_does_not_affect_non_int_values(self):
        """String values in result-limit keys should not be modified."""
        result = self.engine.apply_request_transforms(
            {"maxResults": "all"}, {"max_results": 50}
        )
        assert result["maxResults"] == "all"

    # ---- allowed_labels ----

    def test_filter_allowed_labels(self):
        """labelIds should be filtered to only allowed_labels."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["INBOX", "SPAM", "TRASH", "UNREAD"]},
            {"allowed_labels": ["INBOX", "UNREAD", "SENT"]},
        )
        assert result["labelIds"] == ["INBOX", "UNREAD"]

    def test_allowed_labels_all_pass(self):
        """If all labels are in allowed_labels, nothing is removed."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["INBOX", "SENT"]},
            {"allowed_labels": ["INBOX", "SENT", "DRAFT"]},
        )
        assert result["labelIds"] == ["INBOX", "SENT"]

    def test_allowed_labels_empty_result(self):
        """If no labels match, result should be empty list."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["SPAM", "TRASH"]},
            {"allowed_labels": ["INBOX", "SENT"]},
        )
        assert result["labelIds"] == []

    # ---- exclude_labels ----

    def test_exclude_labels(self):
        """labelIds should have excluded labels removed."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["INBOX", "SPAM", "TRASH", "UNREAD"]},
            {"exclude_labels": ["SPAM", "TRASH"]},
        )
        assert result["labelIds"] == ["INBOX", "UNREAD"]

    def test_exclude_labels_no_match(self):
        """If no labels match exclusion, everything stays."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["INBOX", "SENT"]},
            {"exclude_labels": ["SPAM", "TRASH"]},
        )
        assert result["labelIds"] == ["INBOX", "SENT"]

    # ---- allowed + exclude together ----

    def test_allowed_and_exclude_labels_combined(self):
        """Both allowed_labels and exclude_labels should apply together."""
        result = self.engine.apply_request_transforms(
            {"labelIds": ["INBOX", "IMPORTANT", "SPAM", "TRASH", "UNREAD"]},
            {"allowed_labels": ["INBOX", "IMPORTANT", "UNREAD", "SPAM"], "exclude_labels": ["SPAM"]},
        )
        # allowed_labels filters to [INBOX, IMPORTANT, SPAM, UNREAD]
        # exclude_labels then removes SPAM
        assert result["labelIds"] == ["INBOX", "IMPORTANT", "UNREAD"]

    # ---- query_filter ----

    def test_query_filter_added_fresh(self):
        """query_filter should be set as q when no existing q."""
        result = self.engine.apply_request_transforms(
            {}, {"query_filter": "sharedWithMe=true"}
        )
        assert result["q"] == "sharedWithMe=true"

    def test_query_filter_combined_with_existing(self):
        """query_filter should combine with existing q using AND."""
        result = self.engine.apply_request_transforms(
            {"q": "from:alice"}, {"query_filter": "sharedWithMe=true"}
        )
        assert "sharedWithMe=true" in result["q"]
        assert "from:alice" in result["q"]
        assert " AND " in result["q"]

    def test_query_filter_order_forced_then_existing(self):
        """Forced query should come before existing query with AND."""
        result = self.engine.apply_request_transforms(
            {"q": "from:alice"}, {"query_filter": "sharedWithMe=true"}
        )
        assert result["q"] == "sharedWithMe=true AND from:alice"

    # ---- empty / no-op transforms ----

    def test_empty_policy_no_changes(self):
        """Empty policy config should not modify params."""
        params = {"maxResults": 200, "q": "test", "labelIds": ["INBOX"]}
        result = self.engine.apply_request_transforms(params, {})
        assert result == params

    def test_no_max_results_key_in_policy(self):
        """Policy without max_results should not cap any limit keys."""
        result = self.engine.apply_request_transforms(
            {"maxResults": 200}, {"allowed_labels": ["INBOX"]}
        )
        assert result["maxResults"] == 200

    def test_no_labelIds_key_in_params(self):
        """allowed_labels policy with no labelIds in params should not add labelIds."""
        result = self.engine.apply_request_transforms(
            {"q": "test"}, {"allowed_labels": ["INBOX"]}
        )
        assert "labelIds" not in result

    # ---- multiple transforms together ----

    def test_multiple_transforms_applied(self):
        """Multiple policy transforms should all apply in one call."""
        params = {
            "maxResults": 200,
            "labelIds": ["INBOX", "SPAM", "TRASH"],
            "q": "from:boss",
        }
        policy = {
            "max_results": 25,
            "exclude_labels": ["SPAM"],
            "query_filter": "has:attachment",
        }
        result = self.engine.apply_request_transforms(params, policy)
        assert result["maxResults"] == 25
        assert result["labelIds"] == ["INBOX", "TRASH"]
        assert result["q"] == "has:attachment AND from:boss"


# ---------------------------------------------------------------------------
# Response filters (sync, no DB needed)
# ---------------------------------------------------------------------------

class TestResponseFilter:
    """Tests for PolicyEngine.apply_response_filter."""

    def setup_method(self):
        self.engine = PolicyEngine(session=None)

    def test_strip_blocked_fields(self):
        """blocked_fields should be removed from response."""
        response = {"id": "123", "internalDate": "456", "snippet": "hello"}
        result = self.engine.apply_response_filter(response, {"blocked_fields": ["internalDate"]})
        assert "id" in result
        assert "snippet" in result
        assert "internalDate" not in result

    def test_strip_multiple_blocked_fields(self):
        """Multiple blocked fields should all be removed."""
        response = {"id": "1", "internalDate": "2", "raw": "3", "snippet": "4"}
        result = self.engine.apply_response_filter(
            response, {"blocked_fields": ["internalDate", "raw"]}
        )
        assert "id" in result
        assert "snippet" in result
        assert "internalDate" not in result
        assert "raw" not in result

    def test_blocked_fields_missing_in_response_no_error(self):
        """Missing fields in blocked_fields should not cause errors."""
        response = {"id": "123", "label": "INBOX"}
        result = self.engine.apply_response_filter(
            response, {"blocked_fields": ["internalDate", "nonexistent"]}
        )
        assert result == {"id": "123", "label": "INBOX"}

    def test_cap_array_length(self):
        """max_items should cap array lengths."""
        response = {"messages": [{"id": i} for i in range(100)]}
        result = self.engine.apply_response_filter(response, {"max_items": {"messages": 10}})
        assert len(result["messages"]) == 10

    def test_cap_array_length_preserves_content(self):
        """Capped arrays should preserve first N elements."""
        response = {"items": ["a", "b", "c", "d", "e"]}
        result = self.engine.apply_response_filter(response, {"max_items": {"items": 3}})
        assert result["items"] == ["a", "b", "c"]

    def test_cap_multiple_arrays(self):
        """max_items can cap multiple arrays."""
        response = {
            "messages": [{"id": i} for i in range(20)],
            "labels": [{"id": i} for i in range(30)],
        }
        result = self.engine.apply_response_filter(
            response, {"max_items": {"messages": 5, "labels": 3}}
        )
        assert len(result["messages"]) == 5
        assert len(result["labels"]) == 3

    def test_max_items_does_not_affect_non_arrays(self):
        """max_items should only affect list values, not strings or dicts."""
        response = {"name": "test", "data": "a string", "items": [1, 2, 3, 4, 5]}
        result = self.engine.apply_response_filter(
            response, {"max_items": {"name": 1, "data": 1, "items": 2}}
        )
        assert result["name"] == "test"
        assert result["data"] == "a string"
        assert result["items"] == [1, 2]

    def test_empty_policy_no_changes(self):
        """Empty policy should not modify response at all."""
        response = {"id": "123", "data": [1, 2, 3]}
        result = self.engine.apply_response_filter(response, {})
        assert result == response

    def test_blocked_fields_and_max_items_together(self):
        """Both blocked_fields and max_items should apply together."""
        response = {
            "id": "123",
            "internalDate": "456",
            "messages": [{"id": i} for i in range(50)],
        }
        result = self.engine.apply_response_filter(
            response, {"blocked_fields": ["internalDate"], "max_items": {"messages": 10}}
        )
        assert "internalDate" not in result
        assert len(result["messages"]) == 10


# ---------------------------------------------------------------------------
# PolicyEngine.check_route (async, needs DB session)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPolicyCheckRoute:
    """Tests for PolicyEngine.check_route with real DB session."""

    async def test_route_allowed_when_enabled(self, db_session):
        """Enabled route with policy config should be allowed."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config='{"max_results": 50}',
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.list")
        assert decision.allowed is True
        assert decision.policy_config == {"max_results": 50}

    async def test_route_denied_when_disabled(self, db_session):
        """Disabled route should be denied with reason."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.send",
            enabled=False,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.send")
        assert decision.allowed is False
        assert "disabled" in decision.reason.lower()

    async def test_route_denied_when_no_policy(self, db_session):
        """Route with no policy defined should be default-deny."""
        engine = PolicyEngine(db_session)
        decision = await engine.check_route("drive", "drive.files.list")
        assert decision.allowed is False
        assert "no policy defined" in decision.reason.lower()

    async def test_wildcard_permission_allowed(self, db_session):
        """Key with '*' permission should access any enabled module."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route(
            "calendar", "calendar.events.list", api_key_permissions="*"
        )
        assert decision.allowed is True

    async def test_specific_module_permission_allowed(self, db_session):
        """Key with matching module permission should be allowed."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route(
            "gmail", "gmail.messages.list", api_key_permissions="gmail,drive"
        )
        assert decision.allowed is True

    async def test_wrong_module_permission_denied(self, db_session):
        """Key with wrong module permission should be denied."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route(
            "gmail", "gmail.messages.list", api_key_permissions="drive,calendar"
        )
        assert decision.allowed is False
        assert "not authorized" in decision.reason.lower()

    async def test_module_permission_checked_before_policy_lookup(self, db_session):
        """Module permission check should happen before DB lookup — denied even if policy exists."""
        # This route has an enabled policy, but the key has no gmail permission
        policy = RoutePolicy(
            module="gmail",
            route="gmail.drafts.list",
            enabled=True,
            policy_config='{"max_results": 10}',
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route(
            "gmail", "gmail.drafts.list", api_key_permissions="drive"
        )
        assert decision.allowed is False
        assert "not authorized" in decision.reason.lower()

    async def test_multiple_modules_in_permissions(self, db_session):
        """Key with comma-separated modules should work for all listed modules."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route(
            "drive", "drive.files.get", api_key_permissions="gmail,drive,calendar"
        )
        assert decision.allowed is True

    async def test_policy_config_parsed_as_json(self, db_session):
        """Policy config should be correctly parsed from JSON string."""
        config = {"max_results": 20, "allowed_labels": ["INBOX", "SENT"]}
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config=json.dumps(config),
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.list")
        assert decision.allowed is True
        assert decision.policy_config == config

    async def test_invalid_policy_config_treated_as_empty(self, db_session):
        """Invalid JSON in policy_config should result in empty dict config."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config="NOT VALID JSON{{{",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.get")
        # Should still be allowed but with empty config
        assert decision.allowed is True
        assert decision.policy_config == {}