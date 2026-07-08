# Gatekeeper Module Development Guide

**Audience:** Developers extending Gatekeeper with new Google API modules.  
**Prerequisites:** Read [ARCHITECTURE.md](ARCHITECTURE.md) §4 (Module System) first.  
**See also:** [API_REFERENCE.md](API_REFERENCE.md), [ROUTES.md](ROUTES.md), [POLICY_REFERENCE.md](POLICY_REFERENCE.md).

---

## 1. Prerequisites

Confirm the baseline tests pass before adding a module:

```bash
uv run pytest tests/test_modules.py -v
```

You need Python 3.11+ and the project dependencies installed (`uv pip install -e ".[dev]"`).

## 2. Anatomy of a Module

A module is a Python file under `gatekeeper/modules/{name}/__init__.py` that defines a `Module` subclass of `GoogleModule`.

Minimal example from `gatekeeper/modules/drive/__init__.py`:

```python
from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef

class Module(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = "View, create, and manage Drive files"
    icon = "📁"
    required_scopes = ["https://www.googleapis.com/auth/drive"]

    def get_routes(self) -> list[RouteDef]:
        return [
            RouteDef(
                route_id="drive.files.list",
                method="GET",
                google_path="/drive/v3/files",
                description="List and search for files in Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "description": "Drive query string"},
                        "page_size": {"type": "integer", "default": 20},
                    },
                },
                default_policy={"max_results": 50},
                enabled_by_default=True,
            ),
        ]
```

Base class fields (`gatekeeper/modules/base.py`):

- `name` — short module identifier (used in URLs and tool names).
- `display_name` — human-readable label.
- `description` — shown in the admin UI and module list.
- `icon` — emoji or icon class.
- `required_scopes` — Google OAuth scopes requested during `gatekeeper auth`.
- `get_routes()` — abstract method returning `list[RouteDef]`.

## 3. Step 1: Scaffold the Module File

Create the directory and file:

```bash
mkdir -p gatekeeper/modules/tasks
```

`gatekeeper/modules/tasks/__init__.py`:

```python
"""Tasks module — example Google API module scaffold."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class Module(GoogleModule):
    name = "tasks"
    display_name = "Google Tasks"
    description = "Manage Google Tasks lists and tasks"
    icon = "✅"
    required_scopes = ["https://www.googleapis.com/auth/tasks"]

    def get_routes(self) -> list[RouteDef]:
        return []
```

Verify the stub parses:

```bash
python -c "import ast; ast.parse(open('gatekeeper/modules/tasks/__init__.py').read())"
```

## 4. Step 2: Define `RouteDef`s

### Minimal GET route

```python
RouteDef(
    route_id="tasks.tasklists.list",
    method="GET",
    google_path="/tasks/v1/users/@me/lists",
    description="List all task lists",
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "default": 20},
        },
    },
    default_policy={"max_results": 50},
    enabled_by_default=True,
)
```

### Route with every optional field

```python
RouteDef(
    route_id="tasks.tasks.insert",
    method="POST",
    google_path="/tasks/v1/lists/{tasklist}/tasks",
    description="Insert a new task",
    input_schema={
        "type": "object",
        "properties": {
            "tasklist": {"type": "string", "description": "Task list identifier"},
            "title": {"type": "string", "description": "Task title"},
            "notes": {"type": "string", "description": "Task notes"},
        },
        "required": ["tasklist", "title"],
    },
    query_params=[],
    binary_response=False,
    multipart_upload=False,
    default_policy={"max_results": 50},
    enabled_by_default=False,  # write operation
    base_url=None,
)
```

`input_schema` follows JSON Schema conventions. See the [JSON Schema reference](https://json-schema.org/) for advanced patterns.

## 5. Step 3: Register the Module

Add one line to `gatekeeper/modules/__init__.py:AVAILABLE_MODULES`:

```python
AVAILABLE_MODULES: dict[str, str] = {
    "drive": "gatekeeper.modules.drive",
    "gmail": "gatekeeper.modules.gmail",
    "calendar": "gatekeeper.modules.calendar",
    "tasks": "gatekeeper.modules.tasks",  # <-- added
}
```

This is the only registration edit needed. `create_api_router()` and `create_mcp_server()` both auto-discover the module.

## 6. Step 4: Add Tests

Create `tests/test_tasks_module.py`:

```python
import pytest

from gatekeeper.modules import load_module


@pytest.mark.asyncio
async def test_tasks_routes_load():
    mod = load_module("tasks")
    assert mod is not None
    routes = mod.get_routes()
    assert len(routes) >= 1
    route_ids = [r.route_id for r in routes]
    assert "tasks.tasklists.list" in route_ids


def test_tasks_module_metadata():
    mod = load_module("tasks")
    assert mod.name == "tasks"
    assert "https://www.googleapis.com/auth/tasks" in mod.required_scopes


def test_tasks_tool_name():
    mod = load_module("tasks")
    tools = mod.get_mcp_tools()
    names = [t["name"] for t in tools]
    assert "tasks__tasklists_list" in names
```

Run the module tests:

```bash
uv run pytest tests/test_modules.py tests/test_tasks_module.py -v
```

## 7. Step 5: Run Smoke Tests

`smoke_test.py` exercises every route end-to-end against a live Google account. Before running it:

1. Authenticate Gatekeeper to a secondary/test account:

   ```bash
   gatekeeper auth
   ```

2. Run the smoke test and confirm the account when prompted:

   ```bash
   uv run python smoke_test.py
   ```

The first 50 lines of `smoke_test.py` document the prerequisites and strategy. See `smoke_test.py:1-50`.

## 8. Step 6: Update Documentation

1. Regenerate the route reference:

   ```bash
   uv run python scripts/generate_routes_doc.py
   ```

2. Add the new module to `docs/API_REFERENCE.md` §4 with one example curl.
3. Update OAuth scope tables in `docs/SETUP.md` and `docs/MCP_SETUP_HUMAN.md` if you added new scopes.

## 9. Common Pitfalls

- **`base_url` required for non-`googleapis.com` hosts.** Sheets, Docs, and Slides routes set `base_url` to their respective API hosts. If your module calls an API on a different hostname, set `base_url` explicitly.
- **`input_schema.required` must include every required param.** The MCP server marks `api_key` as required automatically; include only the route-specific required fields.
- **The policy engine defaults to deny.** A route with no `RoutePolicy` row returns 403. Run `gatekeeper init` to seed default policies after adding routes.
- **Write operations should be disabled by default.** Set `enabled_by_default=False` on POST/PUT/PATCH/DELETE routes, matching the existing Gmail/Calendar/Drive write routes.
- **`description` is reused.** It becomes the MCP tool description and the FastAPI route `summary`.
- **Route prefix is auto-stripped.** Use `route_id="tasks.tasks.list"`, not `"tasks.tasks.tasks.list"`. The API router strips the first segment; the MCP server strips it for the tool name.
- **Snake_case schema keys become camelCase** before the Google call. Use `tasklist_id` in `input_schema`; the proxy sends `tasklistId` upstream.
- **Path parameters are substituted into `google_path`.** Any schema key whose camelCase form matches a `{placeholder}` in `google_path` is removed from the body/query.
- **Array params sent as strings are parsed.** If a client sends `["INBOX"]` as a string, the proxy parses it back to a list when the schema declares an array type.
- **Add `query_params` for Google query-only fields.** For example, Drive `addParents`/`removeParents` must be URL query parameters, not in the PATCH body.
