import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from use_cases.serial_device_manager import SerialDeviceManager


class _NotFoundError(Exception):
    pass


def _make_manager():
    serial_repo = MagicMock()
    runtime = MagicMock()
    runtime.NotFoundError = _NotFoundError
    return SerialDeviceManager(serial_repo, runtime)


class TestHandleDeviceDiscovery:
    @pytest.mark.asyncio
    async def test_populates_cache(self):
        """Populates device_cache with discovered devices."""
        mgr = _make_manager()
        mgr.serial_repo.get_all_configured_ports.return_value = []

        await mgr.handle_device_discovery({
            "devices": [
                {"by_id": "usb-FTDI_FT232R-if00", "path": "/dev/ttyUSB0", "major": 188, "minor": 0},
                {"by_id": "usb-Prolific-if00", "path": "/dev/ttyUSB1", "major": 188, "minor": 1},
            ]
        })

        assert len(mgr.device_cache) == 2
        assert "usb-FTDI_FT232R-if00" in mgr.device_cache
        assert "usb-Prolific-if00" in mgr.device_cache

    @pytest.mark.asyncio
    async def test_clears_old_cache(self):
        """Old cache entries are cleared before repopulating."""
        mgr = _make_manager()
        mgr.device_cache = {"old-device": {"path": "/dev/ttyUSB9"}}
        mgr.serial_repo.get_all_configured_ports.return_value = []

        await mgr.handle_device_discovery({"devices": []})

        assert len(mgr.device_cache) == 0

    @pytest.mark.asyncio
    async def test_skips_devices_without_by_id(self):
        """Devices without by_id are not cached."""
        mgr = _make_manager()
        mgr.serial_repo.get_all_configured_ports.return_value = []

        await mgr.handle_device_discovery({
            "devices": [{"path": "/dev/ttyUSB0"}]
        })

        assert len(mgr.device_cache) == 0


class TestHandleDeviceChange:
    @pytest.mark.asyncio
    async def test_add_device_creates_node(self):
        """Adding a device creates device node in matching container."""
        mgr = _make_manager()
        mgr.serial_repo.get_by_device_id.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {
                    "name": "modbus",
                    "device_id": "usb-FTDI_FT232R",
                    "container_path": "/dev/modbus0",
                },
            }
        ]
        container = MagicMock()
        container.status = "running"
        mgr.container_runtime.get_container.return_value = container

        exec_result = MagicMock()
        exec_result.exit_code = 0
        container.exec_run.return_value = exec_result

        await mgr.handle_device_change({
            "action": "add",
            "device": {
                "path": "/dev/ttyUSB0",
                "by_id": "usb-FTDI_FT232R-if00",
                "major": 188,
                "minor": 0,
            },
        })

        assert "usb-FTDI_FT232R-if00" in mgr.device_cache
        mgr.serial_repo.update_status.assert_called_once_with(
            "plc1", "modbus", "connected",
            current_host_path="/dev/ttyUSB0", major=188, minor=0,
        )

    @pytest.mark.asyncio
    async def test_remove_device_updates_status(self):
        """Removing a device updates status to disconnected."""
        mgr = _make_manager()
        mgr.device_cache = {"usb-FTDI_FT232R-if00": {"path": "/dev/ttyUSB0", "by_id": "usb-FTDI_FT232R-if00"}}
        mgr.serial_repo.get_by_device_id.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {"name": "modbus", "device_id": "usb-FTDI_FT232R"},
            }
        ]

        await mgr.handle_device_change({
            "action": "remove",
            "device": {"path": "/dev/ttyUSB0", "by_id": "usb-FTDI_FT232R-if00"},
        })

        assert "usb-FTDI_FT232R-if00" not in mgr.device_cache
        mgr.serial_repo.update_status.assert_called_once_with(
            "plc1", "modbus", "disconnected"
        )

    @pytest.mark.asyncio
    async def test_invalid_event_returns_early(self):
        """Missing action or device → early return."""
        mgr = _make_manager()

        await mgr.handle_device_change({})
        await mgr.handle_device_change({"action": "add"})

        mgr.serial_repo.get_by_device_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_without_by_id_uses_path_lookup(self):
        """Remove event without by_id falls back to path-based cache lookup."""
        mgr = _make_manager()
        mgr.device_cache = {
            "usb-FTDI-if00": {"path": "/dev/ttyUSB0", "by_id": "usb-FTDI-if00"}
        }
        mgr.serial_repo.get_by_device_id.return_value = []

        await mgr.handle_device_change({
            "action": "remove",
            "device": {"path": "/dev/ttyUSB0"},
        })

        # Cache entry should be removed via path-based fallback
        assert "usb-FTDI-if00" not in mgr.device_cache

    @pytest.mark.asyncio
    async def test_add_invokes_callbacks(self):
        """Device add notifies registered callbacks."""
        mgr = _make_manager()
        callback = AsyncMock()
        mgr.device_update_callbacks = [callback]
        mgr.serial_repo.get_by_device_id.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {"name": "modbus", "device_id": "usb-FTDI", "container_path": "/dev/modbus0"},
            }
        ]
        container = MagicMock()
        container.status = "running"
        mgr.container_runtime.get_container.return_value = container
        exec_result = MagicMock()
        exec_result.exit_code = 0
        container.exec_run.return_value = exec_result

        device = {"path": "/dev/ttyUSB0", "by_id": "usb-FTDI-if00", "major": 188, "minor": 0}
        await mgr.handle_device_change({"action": "add", "device": device})

        callback.assert_called_once_with("plc1", "modbus", "connected", device)


class TestMatchDeviceToConfigs:
    def test_matches_by_device_id(self):
        """Matches using serial_repo.get_by_device_id."""
        mgr = _make_manager()
        mgr.serial_repo.get_by_device_id.return_value = [
            {"container_name": "plc1", "serial_config": {"name": "modbus"}}
        ]

        result = mgr._match_device_to_configs({"by_id": "usb-FTDI-if00"})

        assert len(result) == 1
        assert result[0]["container_name"] == "plc1"

    def test_no_by_id_falls_back_to_path(self):
        """No by_id falls back to path-based matching."""
        mgr = _make_manager()
        mgr.serial_repo.load_configs.return_value = {
            "plc1": {
                "serial_ports": [
                    {"name": "modbus", "device_id": "ttyUSB0"}
                ]
            }
        }

        result = mgr._match_device_to_configs({"path": "/dev/ttyUSB0"})

        assert len(result) == 1
        assert result[0]["container_name"] == "plc1"

    def test_no_path_no_by_id_returns_empty(self):
        """No path and no by_id returns empty."""
        mgr = _make_manager()

        result = mgr._match_device_to_configs({})

        assert result == []


class TestGetAvailableDevices:
    def test_returns_cache_values(self):
        """Returns list of all cached devices."""
        mgr = _make_manager()
        mgr.device_cache = {
            "usb-FTDI": {"path": "/dev/ttyUSB0", "by_id": "usb-FTDI"},
            "usb-Prolific": {"path": "/dev/ttyUSB1", "by_id": "usb-Prolific"},
        }

        result = mgr.get_available_devices()

        assert len(result) == 2

    def test_empty_cache(self):
        """Empty cache returns empty list."""
        mgr = _make_manager()

        assert mgr.get_available_devices() == []


class TestGetDeviceById:
    def test_finds_matching_device(self):
        """Finds device matching the device_id."""
        mgr = _make_manager()
        mgr.device_cache = {
            "usb-FTDI_FT232R_ABC-if00-port0": {
                "path": "/dev/ttyUSB0",
                "by_id": "usb-FTDI_FT232R_ABC-if00-port0",
            }
        }

        result = mgr.get_device_by_id("usb-FTDI_FT232R_ABC")

        assert result is not None
        assert result["path"] == "/dev/ttyUSB0"

    def test_no_match_returns_none(self):
        """No matching device returns None."""
        mgr = _make_manager()
        mgr.device_cache = {}

        assert mgr.get_device_by_id("nonexistent") is None


class TestRegisterDeviceCallback:
    def test_registers_callback(self):
        """Callback added to list."""
        mgr = _make_manager()
        cb = MagicMock()

        mgr.register_device_callback(cb)

        assert cb in mgr.device_update_callbacks


class TestResyncSerialDevices:
    @pytest.mark.asyncio
    async def test_no_configured_ports(self):
        """No configured ports → early return."""
        mgr = _make_manager()
        mgr.serial_repo.get_all_configured_ports.return_value = []

        await mgr.resync_serial_devices()

        mgr.container_runtime.get_container.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_device_node_for_connected_device(self):
        """Connected device gets device node created."""
        mgr = _make_manager()
        mgr.device_cache = {
            "usb-FTDI_FT232R-if00": {
                "path": "/dev/ttyUSB0",
                "by_id": "usb-FTDI_FT232R-if00",
                "major": 188,
                "minor": 0,
            }
        }
        mgr.serial_repo.get_all_configured_ports.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {
                    "name": "modbus",
                    "device_id": "usb-FTDI_FT232R-if00",
                    "container_path": "/dev/modbus0",
                },
            }
        ]
        container = MagicMock()
        container.status = "running"
        mgr.container_runtime.get_container.return_value = container
        exec_result = MagicMock()
        exec_result.exit_code = 0
        container.exec_run.return_value = exec_result

        await mgr.resync_serial_devices()

        mgr.serial_repo.update_status.assert_called_once_with(
            "plc1", "modbus", "connected",
            current_host_path="/dev/ttyUSB0", major=188, minor=0,
        )

    @pytest.mark.asyncio
    async def test_disconnected_device_marked(self):
        """Device not in cache marked as disconnected."""
        mgr = _make_manager()
        mgr.device_cache = {}
        mgr.serial_repo.get_all_configured_ports.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {
                    "name": "modbus",
                    "device_id": "usb-FTDI_FT232R",
                    "container_path": "/dev/modbus0",
                },
            }
        ]
        container = MagicMock()
        container.status = "running"
        mgr.container_runtime.get_container.return_value = container

        await mgr.resync_serial_devices()

        mgr.serial_repo.update_status.assert_called_once_with(
            "plc1", "modbus", "disconnected"
        )

    @pytest.mark.asyncio
    async def test_stale_container_cleaned_up(self):
        """Container not found → serial configs deleted."""
        mgr = _make_manager()
        mgr.serial_repo.get_all_configured_ports.return_value = [
            {
                "container_name": "deleted_plc",
                "serial_config": {
                    "name": "modbus",
                    "device_id": "usb-FTDI",
                    "container_path": "/dev/modbus0",
                },
            }
        ]
        mgr.container_runtime.get_container.side_effect = _NotFoundError

        await mgr.resync_serial_devices()

        mgr.serial_repo.delete_configs.assert_called_once_with("deleted_plc")

    @pytest.mark.asyncio
    async def test_skips_non_running_container(self):
        """Non-running container skipped during resync."""
        mgr = _make_manager()
        mgr.serial_repo.get_all_configured_ports.return_value = [
            {
                "container_name": "plc1",
                "serial_config": {
                    "name": "modbus",
                    "device_id": "usb-FTDI",
                    "container_path": "/dev/modbus0",
                },
            }
        ]
        container = MagicMock()
        container.status = "exited"
        mgr.container_runtime.get_container.return_value = container

        await mgr.resync_serial_devices()

        mgr.serial_repo.update_status.assert_not_called()
