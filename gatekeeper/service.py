"""Manage Gatekeeper as a systemd service.

Supports both **user-level** and **system-level** service installation.

User services (``--scope user``) live in ``~/.config/systemd/user/`` and are
tied to the user's login session. They require ``loginctl enable-linger``
to survive disconnects.

System services (``--scope system``) live in ``/etc/systemd/system/`` and are
started at boot, independent of any user session. This is the recommended
mode for servers and always-on deployments. System commands require
``sudo`` privileges.
"""

from __future__ import annotations

import getpass
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
SYSTEMD_SYSTEM_DIR = Path("/etc/systemd/system")

SERVICE_USER_TEMPLATE = """\
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

SERVICE_SYSTEM_TEMPLATE = """\
[Unit]
Description=Gatekeeper Policy Gateway
After=network.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={work_dir}
ExecStart={exec_path} serve
Restart=on-failure
RestartSec=5
EnvironmentFile={env_file}

[Install]
WantedBy=multi-user.target
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _systemctl(
    *args: str, check: bool = True, scope: str = "user"
) -> subprocess.CompletedProcess:
    """Run a systemctl command for the given scope.

    Parameters
    ----------
    scope : str
        ``"user"`` for user-level systemd (``systemctl --user``),
        ``"system"`` for system-level (``sudo systemctl``).
    """
    if scope == "system":
        return _run(["sudo", "systemctl"] + list(args), check=check)
    return _run(["systemctl", "--user"] + list(args), check=check)


def _is_systemd_available(scope: str = "user") -> bool:
    """Check whether the given systemd scope is available."""
    if scope == "system":
        # System-level systemd is virtually always present on Linux servers
        try:
            result = _run(["systemctl", "is-system-running"], check=False)
            return result.returncode in (0, 1)  # running or degraded
        except OSError:
            return False
    # User scope
    try:
        result = _systemctl("status", check=False)
    except OSError:
        return False
    try:
        result = _run(["systemctl", "--user", "is-system-running"], check=False)
        return result.returncode in (0, 1)
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
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return str(Path.cwd())

    exec_path = _resolve_exec_path()
    if exec_path:
        exec_dir = Path(exec_path).resolve().parent
        if exec_dir.name == "bin" and (exec_dir.parent / ".venv").exists():
            return str(exec_dir.parent)
        for parent in exec_dir.parents:
            if (parent / ".env").exists():
                return str(parent)

    return str(Path.cwd())


def _unit_path(scope: str = "user") -> Path:
    """Return the path where the service unit file should be written."""
    if scope == "system":
        return SYSTEMD_SYSTEM_DIR / SERVICE_UNIT
    return SYSTEMD_USER_DIR / SERVICE_UNIT


def _detect_scope() -> str:
    """Auto-detect which scope to use.

    Returns ``"system"`` if no user session is active but systemd is available
    at system level, otherwise ``"user"``.
    """
    if _is_systemd_available("system") and not _is_systemd_available("user"):
        return "system"
    return "user"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_service(skip_prompt: bool = False, scope: str = "user") -> bool:
    """Install the systemd unit file and enable + start the service.

    Parameters
    ----------
    skip_prompt : bool
        If True, skip the confirmation prompt (for CI / install script use).
    scope : str
        ``"user"`` to install as a user service (``~/.config/systemd/user/``),
        ``"system"`` to install as a system service (``/etc/systemd/system/``).

    Returns
    -------
    bool
        True if the service was installed successfully.
    """
    if scope not in ("user", "system"):
        print(f"❌ Invalid scope '{scope}'. Use 'user' or 'system'.")
        return False

    if not _is_systemd_available(scope):
        if scope == "system":
            print("❌ systemd is not available at the system level.")
            print("   This is unexpected on Linux. Is systemd running?")
        else:
            print("❌ systemd user sessions are not available on this system.")
        print("   Gatekeeper can still be run manually with: gatekeeper serve")
        return False

    exec_path = _resolve_exec_path()
    if not exec_path:
        print("❌ Cannot find 'gatekeeper' on PATH.")
        print("   Make sure Gatekeeper is installed and accessible.")
        return False

    work_dir = _resolve_work_dir()

    if scope == "system":
        # System service template: needs User/Group/EnvironmentFile
        username = getpass.getuser()
        import grp

        groupname = grp.getgrgid(os.getgid()).gr_name
        env_file = os.path.join(work_dir, ".env")

        unit_content = SERVICE_SYSTEM_TEMPLATE.format(
            user=username,
            group=groupname,
            work_dir=work_dir,
            exec_path=exec_path,
            env_file=env_file,
        )
    else:
        unit_content = SERVICE_USER_TEMPLATE.format(
            work_dir=work_dir,
            exec_path=exec_path,
        )

    # Write unit file
    if scope == "system":
        unit_path = _unit_path("system")
        # Need sudo to write to /etc/systemd/system
        result = subprocess.run(
            ["sudo", "tee", str(unit_path)],
            input=unit_content,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"❌ Failed to write system unit file: {result.stderr}")
            return False
        print(f"📝 System service unit written to {unit_path}")
    else:
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        unit_path = _unit_path("user")
        unit_path.write_text(unit_content)
        print(f"📝 User service unit written to {unit_path}")

    # Reload systemd
    _systemctl("daemon-reload", scope=scope)

    # If migrating from user to system, stop and disable the old user service
    if scope == "system" and _unit_path("user").exists():
        print("⚠️  Existing user service detected — stopping and disabling it...")
        _systemctl("stop", SERVICE_NAME, check=False, scope="user")
        _systemctl("disable", SERVICE_NAME, check=False, scope="user")
        # Remove the user unit file
        old_path = _unit_path("user")
        old_path.unlink(missing_ok=True)
        print(f"🗑️  Removed user service unit at {old_path}")
        _systemctl("daemon-reload", scope="user")

    # Enable and start
    _systemctl("enable", SERVICE_NAME, scope=scope)
    _systemctl("start", SERVICE_NAME, scope=scope)

    scope_label = "system" if scope == "system" else "user"
    systemctl_prefix = "sudo systemctl" if scope == "system" else "systemctl --user"
    journalctl_prefix = "journalctl" if scope == "system" else "journalctl --user"

    print(f"✅ Gatekeeper {scope_label} service installed and started.")
    print(f"   Working directory: {work_dir}")
    print(f"   ExecStart: {exec_path} serve")
    print()
    print("   Useful commands:")
    print(f"     {systemctl_prefix} status gatekeeper")
    print(f"     {journalctl_prefix} -u gatekeeper -f")
    print("     gatekeeper service status")
    print("     gatekeeper service restart")

    if scope == "system":
        print()
        print("   💡 System service starts at boot — no user session required.")
        print("   💡 No need for 'loginctl enable-linger'.")
    else:
        print()
        print("   ⚠️  User services require a persistent login session.")
        print("   ⚠️  Run 'loginctl enable-linger' to survive disconnects,")
        print("   ⚠️  or re-install with --scope system for boot-time startup.")

    return True


def uninstall_service(scope: str = "user") -> bool:
    """Stop, disable, and remove the systemd unit.

    Parameters
    ----------
    scope : str
        ``"user"`` or ``"system"``.
    """
    unit = _unit_path(scope)
    if scope == "system":
        # Check system path even without sudo
        result = _run(["test", "-f", str(unit)], check=False)
        if result.returncode != 0:
            print("ℹ️  Gatekeeper system service is not installed.")
            return True
    elif not unit.exists():
        print("ℹ️  Gatekeeper user service is not installed.")
        return True

    scope_label = "system" if scope == "system" else "user"
    print(f"Stopping and disabling {scope_label} service...")
    _systemctl("stop", SERVICE_NAME, check=False, scope=scope)
    _systemctl("disable", SERVICE_NAME, check=False, scope=scope)

    if scope == "system":
        _run(["sudo", "rm", "-f", str(unit)], check=True)
    else:
        unit.unlink(missing_ok=True)

    print(f"🗑️  Removed {unit}")
    _systemctl("daemon-reload", scope=scope)
    print(f"✅ Gatekeeper {scope_label} service uninstalled.")
    return True


def enable_service(scope: str = "user") -> bool:
    """Enable and start the service (without reinstalling the unit file).

    Parameters
    ----------
    scope : str
        ``"user"`` or ``"system"``.
    """
    unit = _unit_path(scope)
    # For system scope, the file check needs sudo to detect
    exists = (
        _run(["test", "-f", str(unit)], check=False).returncode == 0
        if scope == "system"
        else unit.exists()
    )
    if not exists:
        scope_label = "system" if scope == "system" else "user"
        print(
            f"❌ {scope_label.capitalize()} service unit not found."
            f" Run 'gatekeeper service install --scope {scope}' first."
        )
        return False

    _systemctl("enable", SERVICE_NAME, scope=scope)
    _systemctl("start", SERVICE_NAME, scope=scope)
    scope_label = "system" if scope == "system" else "user"
    print(f"✅ Gatekeeper {scope_label} service enabled and started.")
    return True


def disable_service(scope: str = "user") -> bool:
    """Stop and disable the service (unit file is preserved).

    Parameters
    ----------
    scope : str
        ``"user"`` or ``"system"``.
    """
    _systemctl("stop", SERVICE_NAME, check=False, scope=scope)
    _systemctl("disable", SERVICE_NAME, scope=scope)
    scope_label = "system" if scope == "system" else "user"
    print(f"✅ Gatekeeper {scope_label} service disabled and stopped.")
    return True


def restart_service(scope: str = "user") -> bool:
    """Restart the service (stop + start, preserving enable state).

    Parameters
    ----------
    scope : str
        ``"user"`` or ``"system"``.
    """
    unit = _unit_path(scope)
    exists = (
        _run(["test", "-f", str(unit)], check=False).returncode == 0
        if scope == "system"
        else unit.exists()
    )
    if not exists:
        scope_label = "system" if scope == "system" else "user"
        print(
            f"❌ {scope_label.capitalize()} service unit not found."
            f" Run 'gatekeeper service install --scope {scope}' first."
        )
        return False

    _systemctl("restart", SERVICE_NAME, scope=scope)
    scope_label = "system" if scope == "system" else "user"
    print(f"✅ Gatekeeper {scope_label} service restarted.")
    return True


def service_status(scope: str = "user") -> None:
    """Print the current status of the Gatekeeper service.

    Parameters
    ----------
    scope : str
        ``"user"`` or ``"system"``.
    """
    unit = _unit_path(scope)
    exists = (
        _run(["test", "-f", str(unit)], check=False).returncode == 0
        if scope == "system"
        else unit.exists()
    )
    if not exists:
        scope_label = "system" if scope == "system" else "user"
        print(f"ℹ️  Gatekeeper {scope_label} service is not installed.")
        print(f"   Run 'gatekeeper service install --scope {scope}' to set it up.")
        return

    result = _systemctl("status", SERVICE_NAME, check=False, scope=scope)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


def service_logs(follow: bool = False, scope: str = "user") -> None:
    """Show Gatekeeper service logs.

    Parameters
    ----------
    follow : bool
        If True, follow the log output (like ``tail -f``).
    scope : str
        ``"user"`` or ``"system"``.
    """
    cmd = ["journalctl"]
    if scope == "system":
        pass  # system journal, no --user flag
    else:
        cmd.append("--user")
    cmd.extend(["-u", SERVICE_NAME])

    if follow:
        os.execvp("journalctl", cmd + ["-f"])
    else:
        result = _run(cmd, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)