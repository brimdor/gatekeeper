"""Tests for the module system — loading, routes, policies, MCP tools."""

import pytest


class TestModuleLoading:
    """Tests for loading modules from the registry."""

    def test_load_drive_module(self):
        from gatekeeper.modules import load_module

        mod = load_module("drive")
        assert mod is not None
        assert mod.name == "drive"
        assert mod.display_name == "Google Drive"
        assert mod.icon == "📁"

    def test_load_gmail_module(self):
        from gatekeeper.modules import load_module

        mod = load_module("gmail")
        assert mod is not None
        assert mod.name == "gmail"
        assert mod.display_name == "Google Gmail"
        assert mod.icon == "📧"

    def test_load_calendar_module(self):
        from gatekeeper.modules import load_module

        mod = load_module("calendar")
        assert mod is not None
        assert mod.name == "calendar"
        assert mod.display_name == "Google Calendar"
        assert mod.icon == "📅"

    def test_load_unknown_module_returns_none(self):
        from gatekeeper.modules import load_module

        mod = load_module("nonexistent")
        assert mod is None

    def test_load_enabled_modules_selective(self):
        from gatekeeper.modules import load_enabled_modules, _loaded_modules

        # Clear cache for fresh load
        _loaded_modules.clear()
        mods = load_enabled_modules(["drive", "calendar"])
        assert len(mods) == 2
        names = {m.name for m in mods}
        assert "drive" in names
        assert "gmail" not in names
        assert "calendar" in names


class TestDriveModule:
    """Tests for the Drive module route definitions."""

    def setup_method(self):
        from gatekeeper.modules import load_module

        self.mod = load_module("drive")

    def test_routes_count(self):
        assert len(self.mod.get_routes()) == 5

    def test_route_ids_start_with_drive(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("drive."), f"Route {route.route_id} doesn't start with 'drive.'"

    def test_specific_route_ids(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        assert "drive.files.list" in ids
        assert "drive.files.get" in ids
        assert "drive.files.export" in ids
        assert "drive.files.list_shared" in ids
        assert "drive.files.copy" in ids

    def test_copy_route_disabled_by_default(self):
        copy_route = next(r for r in self.mod.get_routes() if r.route_id == "drive.files.copy")
        assert copy_route.enabled_by_default is False

    def test_read_routes_enabled_by_default(self):
        for route in self.mod.get_routes():
            if route.route_id != "drive.files.copy":
                assert route.enabled_by_default is True, f"{route.route_id} should be enabled by default"

    def test_each_route_has_input_schema(self):
        for route in self.mod.get_routes():
            assert "type" in route.input_schema, f"{route.route_id} missing input schema type"
            assert route.input_schema["type"] == "object"

    def test_each_route_has_description(self):
        for route in self.mod.get_routes():
            assert len(route.description) > 0, f"{route.route_id} missing description"

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/drive.readonly" in self.mod.required_scopes

    def test_default_policies_structure(self):
        policies = self.mod.get_default_policies()
        assert len(policies) == 5
        for route_id, policy in policies.items():
            assert "enabled" in policy
            assert "config" in policy

    def test_mcp_tools_structure(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) == 5
        for tool in tools:
            assert tool["name"].startswith("drive__")
            assert "description" in tool
            assert "inputSchema" in tool


class TestGmailModule:
    """Tests for the Gmail module route definitions."""

    def setup_method(self):
        from gatekeeper.modules import load_module

        self.mod = load_module("gmail")

    def test_routes_count(self):
        assert len(self.mod.get_routes()) == 6

    def test_route_ids_start_with_gmail(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("gmail."), f"Route {route.route_id} doesn't start with 'gmail.'"

    def test_specific_route_ids(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        assert "gmail.messages.list" in ids
        assert "gmail.messages.get" in ids
        assert "gmail.messages.send" in ids
        assert "gmail.drafts.list" in ids
        assert "gmail.drafts.create" in ids
        assert "gmail.labels.list" in ids

    def test_write_routes_disabled_by_default(self):
        send_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.messages.send")
        draft_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.drafts.create")
        assert send_route.enabled_by_default is False
        assert draft_route.enabled_by_default is False

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
        assert "https://www.googleapis.com/auth/gmail.readonly" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/gmail.send" in self.mod.required_scopes


class TestCalendarModule:
    """Tests for the Calendar module route definitions."""

    def setup_method(self):
        from gatekeeper.modules import load_module

        self.mod = load_module("calendar")

    def test_routes_count(self):
        assert len(self.mod.get_routes()) == 8

    def test_route_ids_start_with_calendar(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("calendar."), f"Route {route.route_id} doesn't start with 'calendar.'"

    def test_write_routes_disabled_by_default(self):
        write_routes = [
            "calendar.events.create",
            "calendar.events.update",
            "calendar.events.delete",
        ]
        for route in self.mod.get_routes():
            if route.route_id in write_routes:
                assert route.enabled_by_default is False, f"{route.route_id} should be disabled by default"

    def test_read_routes_enabled_by_default(self):
        read_routes = [
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.calendarlist.list",
            "calendar.freebusy.query",
        ]
        for route in self.mod.get_routes():
            if route.route_id in read_routes:
                assert route.enabled_by_default is True, f"{route.route_id} should be enabled by default"

    def test_events_list_has_max_results_policy(self):
        list_route = next(r for r in self.mod.get_routes() if r.route_id == "calendar.events.list")
        assert "max_results" in list_route.default_policy

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/calendar.readonly" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/calendar.events" in self.mod.required_scopes

    def test_mcp_tools_naming(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) == 8
        for tool in tools:
            assert tool["name"].startswith("calendar__")
            assert "description" in tool
            assert "inputSchema" in tool