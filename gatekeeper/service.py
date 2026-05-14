"""Manage Gatekeeper as a systemd user service.

Provides install, enable, disable, restart, status, logs, and uninstall
operations for the ``gatekeeper.service`` user unit. All operations
use ``systemctl --user`` so no root privileges are required.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

logger = __import__("logging").getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVICE_NAME = "gatekeeper"
SERVICE_UNIT = f"{SERVICE_NAME}.service"
SYSTEMD_USER_DIR = Path(os.path.expanduser("~/.config/systemd/user"))

SERVICE_TEMPLATE = """\
[Unit]
Description=Gatekeeper Policy Gateway
After=network.target

[Service]
Type=simple
WorkingDirectory={work_dir}
ExecStart={exec_path} serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a ``systemctl --user`` command."""
    return _run(["systemctl", "--user"] + list(args), check=check)


def _is_systemd_available() -> bool:
    """Check whether systemd user sessions are available."""
    try:
        result = _systemctl("status", check=False)
    except OSError:
        # systemctl not installed or not executable — no systemd at all
        return False
    # systemctl --user exits 0 or 1 when running; 1 could mean "no units" but
    # systemd is active. Only non-zero codes like 4 (not found) mean unavailable.
    # A more reliable check: can we reach the user session manager?
    try:
        result = _run(["systemctl", "--user", "is-system-running"], check=False)
        return result.returncode in (0, 1)  # 0=running, 1=degraded both OK
    except OSError:
        return False


def _resolve_exec_path() -> str | None:
    """Find the ``gatekeeper`` binary on PATH."""
    return shutil.which("gatekeeper")


def _resolve_work_dir() -> str:
    """Best-effort working directory for the service.

    Tries, in order:
    1. The directory containing the .env file (walk up from the binary).
    2. The repo root if running from a checkout.
    3. The current working directory.
    """
    # Check if .env exists in the current directory
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return str(Path.cwd())

    # Check if the gatekeeper binary is in a venv and look for .env
    # in the project root (parent of .venv)
    exec_path = _resolve_exec_path()
    if exec_path:
        exec_dir = Path(exec_path).resolve().parent
        # If running from .venv/bin, the project root is two levels up
        if exec_dir.name == "bin" and (exec_dir.parent / ".venv").exists():
            return str(exec_dir.parent)
        # Check for .env in parent directories
        for parent in exec_dir.parents:
            if (parent / ".env").exists():
                return str(parent)

    return str(Path.cwd())


def _unit_path() -> Path:
    """Return the path where the service unit file should be written."""
    return SYSTEMD_USER_DIR / SERVICE_UNIT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_service(skip_prompt: bool = False) -> bool:
    """Install the systemd user unit file and enable + start the service.

    Parameters
    ----------
    skip_prompt : bool
        If True, skip the confirmation prompt (for CI / install script use).

    Returns
    -------
    bool
        True if the service was installed successfully.
    """
    if not _is_systemd_available():
        print("❌ systemd user sessions are not available on this system.")
        print("   Gatekeeper can still be run manually with: gatekeeper serve")
        return False

    exec_path = _resolve_exec_path()
    if not exec_path:
        print("❌ Cannot find 'gatekeeper' on PATH.")
        print("   Make sure Gatekeeper is installed and accessible.")
        return False

    work_dir = _resolve_work_dir()
    unit_content = SERVICE_TEMPLATE.format(
        work_dir=work_dir,
        exec_path=exec_path,
    )

    # Write unit file
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    unit_path = _unit_path()
    unit_path.write_text(unit_content)
    print(f"📝 Service unit written to {unit_path}")

    # Reload systemd
    _systemctl("daemon-reload")

    # Enable and start
    _systemctl("enable", SERVICE_NAME)
    _systemctl("start", SERVICE_NAME)
    print("✅ Gatekeeper service installed and started.")
    print(f"   Working directory: {work_dir}")
    print(f"   ExecStart: {exec_path} serve")
    print()
    print("   Useful commands:")
    print("     systemctl --user status gatekeeper")
    print("     journalctl --user -u gatekeeper -f")
    print("     gatekeeper service status")
    return True


def uninstall_service() -> bool:
    """Stop, disable, and remove the systemd user unit."""
    if not _unit_path().exists():
        print("ℹ️  Gatekeeper service is not installed.")
        return True

    print("Stopping and disabling service...")
    _systemctl("stop", SERVICE_NAME, check=False)
    _systemctl("disable", SERVICE_NAME, check=False)

    unit_path = _unit_path()
    unit_path.unlink(missing_ok=True)
    print(f"🗑️  Removed {unit_path}")

    _systemctl("daemon-reload")
    print("✅ Gatekeeper service uninstalled.")
    return True


def enable_service() -> bool:
    """Enable and start the service (without reinstalling the unit file)."""
    if not _unit_path().exists():
        print("❌ Service unit not found. Run 'gatekeeper service install' first.")
        return False

    _systemctl("enable", SERVICE_NAME)
    _systemctl("start", SERVICE_NAME)
    print("✅ Gatekeeper service enabled and started.")
    return True


def disable_service() -> bool:
    """Stop and disable the service (unit file is preserved)."""
    _systemctl("stop", SERVICE_NAME, check=False)
    _systemctl("disable", SERVICE_NAME)
    print("✅ Gatekeeper service disabled and stopped.")
    return True


def restart_service() -> bool:
    """Restart the service (stop + start, preserving enable state)."""
    if not _unit_path().exists():
        print("❌ Service unit not found. Run 'gatekeeper service install' first.")
        return False

    _systemctl("restart", SERVICE_NAME)
    print("✅ Gatekeeper service restarted.")
    return True


def service_status() -> None:
    """Print the current status of the Gatekeeper service."""
    if not _unit_path().exists():
        print("ℹ️  Gatekeeper service is not installed.")
        print("   Run 'gatekeeper service install' to set it up.")
        return

    result = _systemctl("status", SERVICE_NAME, check=False)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


def service_logs(follow: bool = False) -> None:
    """Show Gatekeeper service logs.

    Parameters
    ----------
    follow : bool
        If True, follow the log output (like ``tail -f``).
    """
    cmd = ["journalctl", "--user", "-u", SERVICE_NAME]
    if follow:
        # Can't capture output in follow mode — let it stream
        os.execvp("journalctl", cmd + ["-f"])
    else:
        result = _run(cmd, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
