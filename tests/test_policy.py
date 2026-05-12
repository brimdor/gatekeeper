"""Tests for the policy engine."""

import json
import pytest
import pytest_asyncio
from sqlalchemy import select

from gatekeeper.models import RoutePolicy


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_allowed_decision(self):
        from gatekeeper.policy import PolicyDecision

        d = PolicyDecision(allowed=True, policy_config={"max_results": 50})
        assert d.allowed is True
        assert d.policy_config == {"max_results": 50}

    def test_denied_decision(self):
        from gatekeeper.policy import PolicyDecision

        d = PolicyDecision(allowed=False, reason="Route is disabled")
        assert d.allowed is False
        assert "disabled" in d.reason


class TestRequestTransforms:
    """Tests for PolicyEngine.apply_request_transforms."""

    def setup_method(self):
        from gatekeeper.policy import PolicyEngine

        self.engine = PolicyEngine(session=None)  # Session not needed for transforms

    def test_cap_max_results(self):
        """maxResults exceeding policy limit should be capped."""
        params = {"maxResults": 200}
        policy = {"max_results": 50}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["maxResults"] == 50

    def test_max_results_below_limit_unchanged(self):
        """maxResults below policy limit should not be changed."""
        params = {"maxResults": 30}
        policy = {"max_results": 50}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["maxResults"] == 30

    def test_cap_page_size(self):
        """pageSize should also be capped by max_results policy."""
        params = {"pageSize": 100}
        policy = {"max_results": 25}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["pageSize"] == 25

    def test_filter_allowed_labels(self):
        """labelIds should be filtered to only allowed_labels."""
        params = {"labelIds": ["INBOX", "SPAM", "TRASH", "UNREAD"]}
        policy = {"allowed_labels": ["INBOX", "UNREAD", "SENT"]}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["labelIds"] == ["INBOX", "UNREAD"]

    def test_exclude_labels(self):
        """labelIds should have excluded labels removed."""
        params = {"labelIds": ["INBOX", "SPAM", "TRASH", "UNREAD"]}
        policy = {"exclude_labels": ["SPAM", "TRASH"]}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["labelIds"] == ["INBOX", "UNREAD"]

    def test_query_filter_added(self):
        """query_filter should be added to the query parameter."""
        params = {}
        policy = {"query_filter": "sharedWithMe=true"}
        result = self.engine.apply_request_transforms(params, policy)
        assert result["q"] == "sharedWithMe=true"

    def test_query_filter_combined_with_existing(self):
        """query_filter should combine with existing query."""
        params = {"q": "from:alice"}
        policy = {"query_filter": "sharedWithMe=true"}
        result = self.engine.apply_request_transforms(params, policy)
        assert "sharedWithMe=true" in result["q"]
        assert "from:alice" in result["q"]

    def test_empty_policy_no_changes(self):
        """Empty policy config should not modify params."""
        params = {"maxResults": 200, "q": "test"}
        result = self.engine.apply_request_transforms(params, {})
        assert result == params


class TestResponseFilter:
    """Tests for PolicyEngine.apply_response_filter."""

    def setup_method(self):
        from gatekeeper.policy import PolicyEngine

        self.engine = PolicyEngine(session=None)

    def test_strip_blocked_fields(self):
        """blocked_fields should be removed from response."""
        response = {"id": "123", "internalDate": "456", "snippet": "hello"}
        policy = {"blocked_fields": ["internalDate"]}
        result = self.engine.apply_response_filter(response, policy)
        assert "id" in result
        assert "snippet" in result
        assert "internalDate" not in result

    def test_cap_array_length(self):
        """max_items should cap array lengths."""
        response = {"messages": [{"id": i} for i in range(100)]}
        policy = {"max_items": {"messages": 10}}
        result = self.engine.apply_response_filter(response, policy)
        assert len(result["messages"]) == 10

    def test_empty_policy_no_changes(self):
        """Empty policy should not modify response."""
        response = {"id": "123", "data": [1, 2, 3]}
        result = self.engine.apply_response_filter(response, {})
        assert result == response


@pytest.mark.asyncio
class TestPolicyCheckRoute:
    """Tests for PolicyEngine.check_route with DB."""

    async def test_route_allowed_when_enabled(self, db_session):
        """Route with enabled policy should be allowed."""
        from gatekeeper.policy import PolicyEngine

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
        """Route with disabled policy should be denied."""
        from gatekeeper.policy import PolicyEngine

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
        assert "disabled" in decision.reason

    async def test_route_denied_when_no_policy(self, db_session):
        """Route with no policy defined should be denied (default deny)."""
        from gatekeeper.policy import PolicyEngine

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("drive", "drive.files.list")
        assert decision.allowed is False
        assert "No policy defined" in decision.reason

    async def test_key_lacks_module_permission(self, db_session):
        """Key with 'drive' permission should be denied access to 'gmail' module."""
        from gatekeeper.policy import PolicyEngine

        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.list", api_key_permissions="drive")
        assert decision.allowed is False
        assert "not authorized" in decision.reason

    async def test_key_with_wildcard_permission(self, db_session):
        """Key with '*' permission should access any module with enabled policy."""
        from gatekeeper.policy import PolicyEngine

        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        engine = PolicyEngine(db_session)
        decision = await engine.check_route("gmail", "gmail.messages.list", api_key_permissions="*")
        assert decision.allowed is True