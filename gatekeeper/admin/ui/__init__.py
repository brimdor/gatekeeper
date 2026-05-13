"""Admin UI — Jinja2 templates and static files."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

import gatekeeper

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Use plain Jinja2 Environment to avoid Starlette TemplateResponse compatibility issues
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def mount_ui(app: FastAPI) -> None:
    """Mount the admin UI templates and static files."""

    # Static files
    app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin-static")

    version = gatekeeper.__version__

    @app.get("/admin/", response_class=HTMLResponse)
    async def admin_dashboard(request: Request):
        template = jinja_env.get_template("dashboard.html")
        html = template.render(version=version, page="dashboard")
        return HTMLResponse(content=html)

    @app.get("/admin/modules", response_class=HTMLResponse)
    async def admin_modules(request: Request):
        template = jinja_env.get_template("modules.html")
        html = template.render(version=version, page="modules")
        return HTMLResponse(content=html)

    @app.get("/admin/keys", response_class=HTMLResponse)
    async def admin_keys(request: Request):
        template = jinja_env.get_template("api_keys.html")
        html = template.render(version=version, page="keys")
        return HTMLResponse(content=html)

    @app.get("/admin/audit", response_class=HTMLResponse)
    async def admin_audit(request: Request):
        template = jinja_env.get_template("audit_log.html")
        html = template.render(version=version, page="audit")
        return HTMLResponse(content=html)

    @app.get("/admin/auth", response_class=HTMLResponse)
    async def admin_auth(request: Request):
        template = jinja_env.get_template("auth_status.html")
        html = template.render(version=version, page="auth")
        return HTMLResponse(content=html)
