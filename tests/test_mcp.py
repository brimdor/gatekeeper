"""Tests for the MCP server — tool listing, naming, and authentication."""

from gatekeeper.modules import load_module


class TestMCPToolNaming:
    """Tests for MCP tool name format: {module}__{route_suffix_with_underscores}.

    The route_id includes the module prefix (e.g., 'drive.files.list'), so the
    suffix is stripped: 'drive.files.list' → 'messages_list' → tool 'drive__files_list'.
    """

    def test_drive_files_list_naming(self):
        """drive.files.list → drive__files_list."""
        mod = load_module("drive")
        tools = mod.get_mcp_tools()
        tool_names = {t["name"] for t in tools}
        assert "drive__files_list" in tool_names

    def test_drive_files_list_shared_naming(self):
        """drive.files.list_shared → drive__files_list_shared."""
        mod = load_module("drive")
        tools = mod.get_mcp_tools()
        tool_names = {t["name"] for t in tools}
        assert "drive__files_list_shared" in tool_names

    def test_gmail_messages_send_naming(self):
        """gmail.messages.send → gmail__messages_send."""
        mod = load_module("gmail")
        tools = mod.get_mcp_tools()
        tool_names = {t["name"] for t in tools}
        assert "gmail__messages_send" in tool_names

    def test_calendar_events_quick_add_naming(self):
        """calendar.events.quick_add → calendar__events_quick_add."""
        mod = load_module("calendar")
        tools = mod.get_mcp_tools()
        tool_names = {t["name"] for t in tools}
        assert "calendar__events_quick_add" in tool_names

    def test_roundtrip_all_tools(self):
        """Every module route should produce an MCP tool with correct naming."""
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            tools = mod.get_mcp_tools()
            assert len(tools) == len(mod.get_routes())

            for route in mod.get_routes():
                # Tool name format: {module}__{route_suffix_with_underscores}
                # route_id = "drive.files.list" → suffix = "files.list" → tool = "drive__files_list"
                route_suffix = (
                    route.route_id.split(".", 1)[1] if "." in route.route_id else route.route_id
                )
                expected_name = f"{module_name}__{route_suffix.replace('.', '_')}"
                tool_names = {t["name"] for t in tools}
                assert expected_name in tool_names, f"Missing tool {expected_name}"

    def test_all_modules_have_tools(self):
        """Each module should produce the same number of tools as routes."""
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            routes = mod.get_routes()
            tools = mod.get_mcp_tools()
            assert len(tools) == len(routes), (
                f"{module_name}: {len(tools)} tools vs {len(routes)} routes"
            )


class TestMCPToolNameParsing:
    """Tests for parsing MCP tool names back to module + route.

    Format: {module}__{route_suffix_with_underscores}
    e.g. gmail__messages_list → module=gmail, route_suffix=messages_list
    """

    def test_parse_simple_name(self):
        """gmail__messages_list → module=gmail, route_suffix=messages_list"""
        name = "gmail__messages_list"
        parts = name.split("__", 1)
        assert len(parts) == 2
        module = parts[0]
        route_suffix = parts[1]
        assert module == "gmail"
        assert route_suffix == "messages_list"

    def test_parse_drive_route(self):
        """drive__files_list → module=drive, route_suffix=files_list"""
        name = "drive__files_list"
        parts = name.split("__", 1)
        module = parts[0]
        route_suffix = parts[1]
        assert module == "drive"
        assert route_suffix == "files_list"

    def test_parse_calendarlist_route(self):
        """calendar__calendarlist_list → module=calendar, route_suffix=calendarlist_list"""
        name = "calendar__calendarlist_list"
        parts = name.split("__", 1)
        module = parts[0]
        route_suffix = parts[1]
        assert module == "calendar"
        assert route_suffix == "calendarlist_list"

    def test_roundtrip_via_module_lookup(self):
        """Tool name suffix should match a route in the module when converted back."""
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            for route in mod.get_routes():
                route_suffix = (
                    route.route_id.split(".", 1)[1] if "." in route.route_id else route.route_id
                )
                tool_suffix = route_suffix.replace(".", "_")
                # Verify the suffix can be found in the module's routes
                found = False
                for r in mod.get_routes():
                    r_suffix = r.route_id.split(".", 1)[1] if "." in r.route_id else r.route_id
                    if r_suffix.replace(".", "_") == tool_suffix:
                        found = True
                        break
                assert found, f"Tool suffix {tool_suffix} not found in {module_name} routes"


class TestMCPServerCreation:
    """Tests for creating the MCP server instance."""

    def test_create_mcp_server_returns_instance(self):
        """create_mcp_server() should return a FastMCP instance."""
        from gatekeeper.mcp_server import create_mcp_server

        mcp = create_mcp_server()
        assert mcp is not None
        assert mcp.name == "gatekeeper"

    def test_mcp_server_has_instructions(self):
        """MCP server should have instructions set."""
        from gatekeeper.mcp_server import create_mcp_server

        mcp = create_mcp_server()
        assert mcp.instructions is not None
        assert len(mcp.instructions) > 0
        assert "policy" in mcp.instructions.lower() or "gatekeeper" in mcp.instructions.lower()


class TestMCPToolSchema:
    """Tests for MCP tool input schema structure."""

    def test_each_tool_has_required_fields(self):
        """Every MCP tool must have name, description, and inputSchema."""
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            tools = mod.get_mcp_tools()
            for tool in tools:
                assert "name" in tool
                assert "description" in tool
                assert "inputSchema" in tool
                assert tool["inputSchema"]["type"] == "object"

    def test_tool_descriptions_are_nonempty(self):
        """Every MCP tool should have a nonempty description."""
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            tools = mod.get_mcp_tools()
            for tool in tools:
                assert len(tool["description"]) > 0, f"Tool {tool['name']} has empty description"

    def test_write_tools_have_input_schemas(self):
        """Write tools should have detailed input schemas."""
        mod = load_module("gmail")
        tools = mod.get_mcp_tools()
        send_tool = next(t for t in tools if t["name"] == "gmail__messages_send")
        props = send_tool["inputSchema"].get("properties", {})
        assert "to" in props
        assert "subject" in props
