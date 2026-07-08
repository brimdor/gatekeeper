"""Tests for module route definitions — structural checks, not exact counts.

Routes may be added or removed over time, so tests verify properties
that must always hold rather than asserting exact route IDs or counts.
"""

from gatekeeper.modules import load_module


class TestDriveModule:
    """Tests for the Drive module route definitions."""

    def setup_method(self):
        self.mod = load_module("drive")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_drive(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("drive."), (
                f"Route {route.route_id} doesn't start with 'drive.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["drive.files.list", "drive.files.get", "drive.files.export"]:
            assert required in ids, f"Missing core route: {required}"

    def test_core_write_routes_exist(self):
        """Essential write routes must be present (even if disabled)."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["drive.files.create", "drive.files.delete"]:
            assert required in ids, f"Missing write route: {required}"

    def test_write_routes_disabled_by_default(self):
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        # drive.files.update is intentionally enabled by default (basic CRUD)
        allowed_by_default = {"drive.files.update"}
        for route in self.mod.get_routes():
            if route.method in write_methods and route.route_id not in allowed_by_default:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} ({route.method}) should be disabled by default"
                )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "drive.files.list",
            "drive.files.get",
            "drive.files.export",
            "drive.about.get",
            "drive.permissions.list",
            "drive.permissions.get",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_each_route_has_input_schema(self):
        for route in self.mod.get_routes():
            assert "type" in route.input_schema, f"{route.route_id} missing input schema type"
            assert route.input_schema["type"] == "object"

    def test_each_route_has_description(self):
        for route in self.mod.get_routes():
            assert len(route.description) > 0, f"{route.route_id} missing description"

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/drive" in self.mod.required_scopes

    def test_default_policies_structure(self):
        policies = self.mod.get_default_policies()
        for route_id, policy in policies.items():
            assert isinstance(policy, dict), f"Policy for {route_id} is not a dict"


class TestGmailModule:
    """Tests for the Gmail module route definitions."""

    def setup_method(self):
        self.mod = load_module("gmail")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_gmail(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("gmail."), (
                f"Route {route.route_id} doesn't start with 'gmail.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["gmail.messages.list", "gmail.messages.get", "gmail.labels.list"]:
            assert required in ids, f"Missing core route: {required}"

    def test_label_routes_exist(self):
        """Label management routes must be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "gmail.labels.list",
            "gmail.labels.get",
            "gmail.labels.create",
            "gmail.labels.update",
            "gmail.labels.delete",
        ]:
            assert required in ids, f"Missing label route: {required}"

    def test_filter_routes_exist(self):
        """Filter management routes must be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "gmail.filters.list",
            "gmail.filters.get",
            "gmail.filters.create",
            "gmail.filters.update",
            "gmail.filters.delete",
        ]:
            assert required in ids, f"Missing filter route: {required}"

    def test_write_routes_disabled_by_default(self):
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        # drive.files.update is intentionally enabled by default (basic CRUD)
        allowed_by_default = {"drive.files.update"}
        for route in self.mod.get_routes():
            if route.method in write_methods and route.route_id not in allowed_by_default:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} ({route.method}) should be disabled by default"
                )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "gmail.messages.list",
            "gmail.messages.get",
            "gmail.drafts.list",
            "gmail.drafts.get",
            "gmail.labels.list",
            "gmail.labels.get",
            "gmail.threads.list",
            "gmail.threads.get",
            "gmail.messages.attachments.get",
            "gmail.history.list",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_messages_list_has_label_policy(self):
        list_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.messages.list")
        assert "allowed_labels" in list_route.default_policy
        assert "exclude_labels" in list_route.default_policy
        assert "SPAM" in list_route.default_policy["exclude_labels"]
        assert "TRASH" in list_route.default_policy["exclude_labels"]

    def test_messages_send_has_recipient_limit(self):
        send_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.messages.send")
        assert "max_recipients" in send_route.default_policy

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/gmail.modify" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/gmail.send" in self.mod.required_scopes

    def test_mcp_tools_naming(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool["name"].startswith("gmail__")
            assert "description" in tool
            assert "inputSchema" in tool


class TestCalendarModule:
    """Tests for the Calendar module route definitions."""

    def setup_method(self):
        self.mod = load_module("calendar")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_calendar(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("calendar."), (
                f"Route {route.route_id} doesn't start with 'calendar.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.freebusy.query",
        ]:
            assert required in ids, f"Missing core route: {required}"

    def test_write_routes_disabled_by_default(self):
        # POST/PUT/PATCH/DELETE routes are disabled by default,
        # except for read-oriented POST routes (freebusy.query, quickAdd)
        read_posts = {"calendar.freebusy.query", "calendar.events.quick_add"}
        for route in self.mod.get_routes():
            if route.method in {"POST", "PUT", "PATCH", "DELETE"}:
                if route.route_id not in read_posts:
                    assert route.enabled_by_default is False, (
                        f"{route.route_id} ({route.method}) should be disabled by default"
                    )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.calendarlist.list",
            "calendar.calendars.get",
            "calendar.freebusy.query",
            "calendar.acl.list",
            "calendar.acl.get",
            "calendar.calendarlist.get",
            "calendar.colors.get",
            "calendar.settings.list",
            "calendar.settings.get",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_events_list_has_max_results_policy(self):
        list_route = next(r for r in self.mod.get_routes() if r.route_id == "calendar.events.list")
        assert "max_results" in list_route.default_policy

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/calendar" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/calendar.events" in self.mod.required_scopes

    def test_mcp_tools_naming(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool["name"].startswith("calendar__")
            assert "description" in tool
            assert "inputSchema" in tool
