"""Tests for the module system — loading, routes, policies, MCP tools."""


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
        from gatekeeper.modules import _loaded_modules, load_enabled_modules

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
        # Drive has 13 routes as of current codebase
        assert len(self.mod.get_routes()) == 13

    def test_route_ids_start_with_drive(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("drive."), (
                f"Route {route.route_id} doesn't start with 'drive.'"
            )

    def test_specific_route_ids(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        expected = {
            "drive.files.list",
            "drive.files.get",
            "drive.files.export",
            "drive.files.list_shared",
            "drive.files.copy",
            "drive.files.create",
            "drive.files.update",
            "drive.files.delete",
            "drive.files.trash",
            "drive.permissions.list",
            "drive.permissions.get",
            "drive.permissions.create",
            "drive.permissions.delete",
        }
        assert ids == expected

    def test_write_routes_disabled_by_default(self):
        write_routes = [
            "drive.files.copy",
            "drive.files.create",
            "drive.files.update",
            "drive.files.delete",
            "drive.files.trash",
            "drive.permissions.create",
            "drive.permissions.delete",
        ]
        for route in self.mod.get_routes():
            if route.route_id in write_routes:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} should be disabled by default"
                )

    def test_read_routes_enabled_by_default(self):
        write_routes = {
            "drive.files.copy",
            "drive.files.create",
            "drive.files.update",
            "drive.files.delete",
            "drive.files.trash",
            "drive.permissions.create",
            "drive.permissions.delete",
        }
        for route in self.mod.get_routes():
            if route.route_id not in write_routes:
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
        assert len(policies) == 13
        for route_id, policy in policies.items():
            assert "enabled" in policy
            assert "config" in policy

    def test_mcp_tools_structure(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) == 13
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
        # Gmail has 14 routes
        assert len(self.mod.get_routes()) == 14

    def test_route_ids_start_with_gmail(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("gmail."), (
                f"Route {route.route_id} doesn't start with 'gmail.'"
            )

    def test_specific_route_ids(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        expected = {
            "gmail.messages.list",
            "gmail.messages.get",
            "gmail.messages.send",
            "gmail.messages.modify",
            "gmail.messages.trash",
            "gmail.messages.delete",
            "gmail.drafts.list",
            "gmail.drafts.get",
            "gmail.drafts.create",
            "gmail.drafts.update",
            "gmail.drafts.send",
            "gmail.drafts.delete",
            "gmail.labels.list",
            "gmail.labels.get",
        }
        assert ids == expected

    def test_write_routes_disabled_by_default(self):
        write_routes = {
            "gmail.messages.send",
            "gmail.messages.modify",
            "gmail.messages.trash",
            "gmail.messages.delete",
            "gmail.drafts.create",
            "gmail.drafts.update",
            "gmail.drafts.send",
            "gmail.drafts.delete",
        }
        for route in self.mod.get_routes():
            if route.route_id in write_routes:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} should be disabled by default"
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
        assert len(tools) == 14
        for tool in tools:
            assert tool["name"].startswith("gmail__")
            assert "description" in tool
            assert "inputSchema" in tool


class TestCalendarModule:
    """Tests for the Calendar module route definitions."""

    def setup_method(self):
        from gatekeeper.modules import load_module

        self.mod = load_module("calendar")

    def test_routes_count(self):
        # Calendar has 12 routes
        assert len(self.mod.get_routes()) == 12

    def test_route_ids_start_with_calendar(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("calendar."), (
                f"Route {route.route_id} doesn't start with 'calendar.'"
            )

    def test_specific_route_ids(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        expected = {
            "calendar.events.list",
            "calendar.events.get",
            "calendar.events.create",
            "calendar.events.update",
            "calendar.events.delete",
            "calendar.events.quick_add",
            "calendar.calendars.list",
            "calendar.calendarlist.list",
            "calendar.calendars.get",
            "calendar.calendars.create",
            "calendar.calendars.delete",
            "calendar.freebusy.query",
        }
        assert ids == expected

    def test_write_routes_disabled_by_default(self):
        write_routes = {
            "calendar.events.create",
            "calendar.events.update",
            "calendar.events.delete",
            "calendar.events.quick_add",
            "calendar.calendars.create",
            "calendar.calendars.delete",
        }
        for route in self.mod.get_routes():
            if route.route_id in write_routes:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} should be disabled by default"
                )

    def test_read_routes_enabled_by_default(self):
        read_routes = {
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.calendarlist.list",
            "calendar.calendars.get",
            "calendar.freebusy.query",
        }
        for route in self.mod.get_routes():
            if route.route_id in read_routes:
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
        assert len(tools) == 12
        for tool in tools:
            assert tool["name"].startswith("calendar__")
            assert "description" in tool
            assert "inputSchema" in tool
