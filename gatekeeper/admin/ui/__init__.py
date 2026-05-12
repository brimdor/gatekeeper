"""Admin UI — Jinja2 templates and static files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from gatekeeper.auth import require_admin

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def mount_ui(app: FastAPI) -> None:
    """Mount the admin UI templates and static files."""

    # Static files
    app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin-static")

    # UI pages
    @app.get("/admin/", response_class=HTMLResponse)
    async def admin_dashboard(request: Request):
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "dashboard",
        })

    @app.get("/admin/modules", response_class=HTMLResponse)
    async def admin_modules(request: Request):
        return templates.TemplateResponse("modules.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "modules",
        })

    @app.get("/admin/routes", response_class=HTMLResponse)
    async def admin_routes(request: Request):
        return templates.TemplateResponse("routes.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "routes",
        })

    @app.get("/admin/keys", response_class=HTMLResponse)
    async def admin_keys(request: Request):
        return templates.TemplateResponse("api_keys.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "keys",
        })

    @app.get("/admin/audit", response_class=HTMLResponse)
    async def admin_audit(request: Request):
        return templates.TemplateResponse("audit_log.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "audit",
        })

    @app.get("/admin/auth", response_class=HTMLResponse)
    async def admin_auth(request: Request):
        return templates.TemplateResponse("auth_status.html", {
            "request": request,
            "version": __import__("gatekeeper").__version__,
            "page": "auth",
        })