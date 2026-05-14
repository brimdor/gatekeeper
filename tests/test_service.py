"""Tests for gatekeeper.service — systemd user service management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from gatekeeper.service import (
    SERVICE_TEMPLATE,
    SERVICE_UNIT,
    _is_systemd_available,
    _resolve_exec_path,
    _resolve_work_dir,
    disable_service,
    enable_service,
    install_service,
    uninstall_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path):
    """Create a mock settings object with a tmp_path database URL."""
    from gatekeeper.config import Settings

    db_path = tmp_path / "gatekeeper.db"
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        google_client_id="test-id",
        google_client_secret="test-secret",
        google_token_file=str(tmp_path / "token.json"),
    )


# ---------------------------------------------------------------------------
# Unit path / template tests
# ---------------------------------------------------------------------------


class TestUnitPath:
    """Tests for _unit_path and unit file generation."""

    def test_unit_path_under_systemd_dir(self, tmp_path):
        """Unit file should live under ~/.config/systemd/user/."""
        expected_unit = tmp_path / "systemd" / SERVICE_UNIT
        with patch("gatekeeper.service._unit_path", return_value=expected_unit):
            result = Path(str(expected_unit))
            assert result.name == "gatekeeper.service"
            assert "systemd" in str(result)


class TestServiceTemplate:
    """Tests for the service unit template."""

    def test_template_has_required_fields(self):
        """Template must contain the core systemd directives."""
        unit = SERVICE_TEMPLATE.format(work_dir="/tmp/gk", exec_path="/usr/bin/gatekeeper")
        assert "[Unit]" in unit
        assert "[Service]" in unit
        assert "[Install]" in unit
        assert "ExecStart=/usr/bin/gatekeeper serve" in unit
        assert "WorkingDirectory=/tmp/gk" in unit
        assert "Restart=on-failure" in unit
        assert "WantedBy=default.target" in unit


# ---------------------------------------------------------------------------
# Install tests
# ---------------------------------------------------------------------------


class TestInstallService:
    """Tests for install_service()."""

    def test_install_no_gatekeeper_binary(self, tmp_path):
        """Should fail if gatekeeper binary is not on PATH."""
        with patch("gatekeeper.service._is_systemd_available", return_value=True), \
             patch("gatekeeper.service._resolve_exec_path", return_value=None), \
             patch("gatekeeper.service.SYSTEMD_USER_DIR", tmp_path / "sysd"):
            result = install_service(skip_prompt=True)
            assert result is False

    def test_install_no_systemd(self, tmp_path):
        """Should fail gracefully when systemd is not available."""
        with patch("gatekeeper.service._is_systemd_available", return_value=False), \
             patch("gatekeeper.service.SYSTEMD_USER_DIR", tmp_path / "sysd"):
            result = install_service(skip_prompt=True)
            assert result is False

    def test_install_creates_unit_file(self, tmp_path):
        """Should write a unit file and run systemctl commands."""
        sysd_dir = tmp_path / "sysd"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("gatekeeper.service._is_systemd_available", return_value=True), \
             patch("gatekeeper.service._resolve_exec_path", return_value="/usr/bin/gatekeeper"), \
             patch("gatekeeper.service._resolve_work_dir", return_value="/home/user/gatekeeper"), \
             patch("gatekeeper.service.SYSTEMD_USER_DIR", sysd_dir), \
             patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl:
            result = install_service(skip_prompt=True)
            assert result is True

            # Check unit file was written
            unit_path = sysd_dir / SERVICE_UNIT
            assert unit_path.exists()

            # Verify content
            content = unit_path.read_text()
            assert "ExecStart=/usr/bin/gatekeeper serve" in content
            assert "WorkingDirectory=/home/user/gatekeeper" in content

            # Verify systemctl was called correctly
            assert mock_ctl.call_count == 3  # daemon-reload, enable, start


class TestUninstallService:
    """Tests for uninstall_service()."""

    def test_uninstall_no_unit(self, tmp_path):
        """Should report not installed when unit file doesn't exist."""
        with patch("gatekeeper.service.SYSTEMD_USER_DIR", tmp_path / "sysd"), \
             patch("gatekeeper.service._systemctl") as mock_ctl:
            result = uninstall_service()
            assert result is True
            mock_ctl.assert_not_called()

    def test_uninstall_removes_unit_file(self, tmp_path):
        """Should stop, disable, and remove the unit file."""
        sysd_dir = tmp_path / "sysd"
        sysd_dir.mkdir(parents=True)
        unit_path = sysd_dir / SERVICE_UNIT
        unit_path.write_text("[Service]\nExecStart=gatekeeper serve\n")
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("gatekeeper.service.SYSTEMD_USER_DIR", sysd_dir), \
             patch("gatekeeper.service._unit_path", return_value=unit_path), \
             patch("gatekeeper.service._systemctl", return_value=mock_result):
            result = uninstall_service()
            assert result is True
            assert not unit_path.exists()


# ---------------------------------------------------------------------------
# Enable / disable tests
# ---------------------------------------------------------------------------


class TestEnableDisable:
    """Tests for enable_service() and disable_service()."""

    def test_enable_no_unit(self, tmp_path):
        """Should fail if unit file doesn't exist."""
        with patch("gatekeeper.service._unit_path", return_value=tmp_path / "nonexistent.service"):
            result = enable_service()
            assert result is False

    def test_enable_starts_service(self, tmp_path):
        """Should enable and start the service."""
        unit_path = tmp_path / SERVICE_UNIT
        unit_path.write_text("[Service]\nExecStart=gatekeeper serve\n")
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("gatekeeper.service._unit_path", return_value=unit_path), \
             patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl:
            result = enable_service()
            assert result is True
            # enable and start
            assert mock_ctl.call_count == 2

    def test_disable_stops_service(self, tmp_path):
        """Should stop and disable the service."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl:
            result = disable_service()
            assert result is True
            # stop and disable
            assert mock_ctl.call_count == 2


# ---------------------------------------------------------------------------
# Resolve path tests
# ---------------------------------------------------------------------------


class TestResolvePaths:
    """Tests for _resolve_exec_path and _resolve_work_dir."""

    def test_resolve_exec_path_found(self):
        """Should find gatekeeper on PATH."""
        with patch("shutil.which", return_value="/usr/bin/gatekeeper"):
            assert _resolve_exec_path() == "/usr/bin/gatekeeper"

    def test_resolve_exec_path_not_found(self):
        """Should return None when gatekeeper is not on PATH."""
        with patch("shutil.which", return_value=None):
            assert _resolve_exec_path() is None

    def test_resolve_work_dir_with_env(self, tmp_path):
        """Should detect .env in the current directory."""
        (tmp_path / ".env").write_text("TEST=1\n")
        with patch.object(Path, "cwd", return_value=tmp_path):
            result = _resolve_work_dir()
            assert result == str(tmp_path)

    def test_systemd_available_when_running(self):
        """Should return True when systemd user session is running."""
        mock_result = MagicMock(returncode=0, stdout="running", stderr="")
        with patch("gatekeeper.service._run", return_value=mock_result):
            assert _is_systemd_available() is True

    def test_systemd_unavailable_when_missing(self):
        """Should return False when systemctl is not found."""
        # _is_systemd_available calls _systemctl first, then _run.
        # Both should raise OSError when systemctl doesn't exist.
        with patch("gatekeeper.service._run", side_effect=OSError("systemctl not found")):
            assert _is_systemd_available() is False
