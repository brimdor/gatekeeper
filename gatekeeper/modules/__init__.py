"""Module registry — dynamic route and policy registration."""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatekeeper.modules.base import GoogleModule

logger = logging.getLogger(__name__)

# Available modules: name -> import path
AVAILABLE_MODULES: dict[str, str] = {
    "drive": "gatekeeper.modules.drive",
    "gmail": "gatekeeper.modules.gmail",
    "calendar": "gatekeeper.modules.calendar",
}

_loaded_modules: dict[str, GoogleModule] = {}


def load_module(name: str) -> GoogleModule | None:
    """Load a module by name. Returns None if not found."""
    if name in _loaded_modules:
        return _loaded_modules[name]

    if name not in AVAILABLE_MODULES:
        logger.error(f"Unknown module: {name}")
        return None

    try:
        mod = importlib.import_module(AVAILABLE_MODULES[name])
        module_cls = getattr(mod, "Module", None)
        if module_cls is None:
            logger.error(f"Module {name} has no Module class")
            return None
        instance = module_cls()
        _loaded_modules[name] = instance
        logger.info(f"Loaded module: {name}")
        return instance
    except Exception as e:
        logger.error(f"Failed to load module {name}: {e}")
        return None


def load_enabled_modules(enabled: list[str]) -> list[GoogleModule]:
    """Load all enabled modules. Returns list of loaded module instances."""
    modules = []
    for name in enabled:
        mod = load_module(name)
        if mod:
            modules.append(mod)
    return modules


def get_loaded_modules() -> dict[str, GoogleModule]:
    """Return all currently loaded modules."""
    return dict(_loaded_modules)
