import pytest
from unittest.mock import MagicMock, patch

from use_cases.docker_manager.create_runtime_container import (
    _generate_mac_address,
    _validate_vnic_configs,
    _validate_mac_addresses,
    _create_runtime_container_sync,
    start_creation,
)


class TestGenerateMacAddress:
    def test_format(self):
        """MAC has 6 colon-separated hex octets."""
        mac = _generate_mac_address()
        parts = mac.split(":")
        assert len(parts) == 6
        for part in parts:
            assert len(part) == 2
            int(part, 16)  # should not raise

    def test_locally_administered(self):
        """First octet bit 1 set (locally administered)."""
        mac = _generate_mac_address()
        first_octet = int(mac.split(":")[0], 16)
        assert first_octet & 0x02 != 0

    def test_unicast(self):
        """First octet bit 0 clear (unicast)."""
        mac = _generate_mac_address()
        first_octet = int(mac.split(":")[0], 16)
        assert first_octet & 0x01 == 0

    def test_uniqueness(self):
        """100 generated MACs are all unique."""
        macs = {_generate_mac_address() for _ in range(100)}
        assert len(macs) == 100


class TestValidateVnicConfigs:
    def test_single_vnic_valid(self):
        """One ethernet vNIC is valid."""
        cache = MagicMock()
        cache.get_interface_type.return_value = "ethernet"

        with patch(
            "use_cases.docker_manager.create_runtime_container.get_macvlan_network_key"
        ) as mock_key:
            mock_key.return_value = "macvlan_eth0_192_168_1_0_24"
            valid, error = _validate_vnic_configs(
                [{"name": "vnic1", "parent_interface": "eth0", "subnet": "255.255.255.0", "gateway": "192.168.1.1"}],
                interface_cache=cache,
            )

        assert valid is True
        assert error == ""

    def test_duplicate_macvlan_network(self):
        """Two vNICs resolving to the same MACVLAN network → invalid."""
        cache = MagicMock()
        cache.get_interface_type.return_value = "ethernet"

        with patch(
            "use_cases.docker_manager.create_runtime_container.get_macvlan_network_key"
        ) as mock_key:
            mock_key.return_value = "macvlan_eth0_192_168_1_0_24"
            valid, error = _validate_vnic_configs(
                [
                    {"name": "vnic1", "parent_interface": "eth0", "subnet": "255.255.255.0", "gateway": "192.168.1.1"},
                    {"name": "vnic2", "parent_interface": "eth0", "subnet": "255.255.255.0", "gateway": "192.168.1.1"},
                ],
                interface_cache=cache,
            )

        assert valid is False
        assert "same MACVLAN network" in error

    def test_wifi_same_interface_warns_but_passes(self):
        """Two WiFi vNICs on same interface → valid (just warns)."""
        cache = MagicMock()
        cache.get_interface_type.return_value = "wifi"

        valid, error = _validate_vnic_configs(
            [
                {"name": "wifi1", "parent_interface": "wlan0"},
                {"name": "wifi2", "parent_interface": "wlan0"},
            ],
            interface_cache=cache,
        )

        assert valid is True
        assert error == ""

    def test_mixed_wifi_ethernet(self):
        """Mixed interface types → valid when no duplicates."""
        cache = MagicMock()
        cache.get_interface_type.side_effect = ["wifi", "ethernet"]

        with patch(
            "use_cases.docker_manager.create_runtime_container.get_macvlan_network_key"
        ) as mock_key:
            mock_key.return_value = "macvlan_eth0_192_168_1_0_24"
            valid, error = _validate_vnic_configs(
                [
                    {"name": "wifi1", "parent_interface": "wlan0"},
                    {"name": "eth1", "parent_interface": "eth0", "subnet": "255.255.255.0", "gateway": "192.168.1.1"},
                ],
                interface_cache=cache,
            )

        assert valid is True
        assert error == ""


class TestValidateMacAddresses:
    def test_no_mac_specified(self):
        """No user MACs → valid."""
        runtime = MagicMock()

        valid, error = _validate_mac_addresses(
            [{"name": "vnic1", "parent_interface": "eth0"}],
            container_runtime=runtime,
        )

        assert valid is True
        assert error == ""
        runtime.get_existing_mac_addresses_on_interface.assert_not_called()

    def test_mac_not_in_use(self):
        """User MAC available → valid."""
        runtime = MagicMock()
        runtime.get_existing_mac_addresses_on_interface.return_value = {}

        valid, error = _validate_mac_addresses(
            [{"name": "vnic1", "parent_interface": "eth0", "mac": "02:00:00:00:00:01"}],
            container_runtime=runtime,
        )

        assert valid is True
        assert error == ""

    def test_mac_already_in_use(self):
        """User MAC conflicts → invalid."""
        runtime = MagicMock()
        runtime.get_existing_mac_addresses_on_interface.return_value = {
            "02:00:00:00:00:01": "plc2"
        }

        valid, error = _validate_mac_addresses(
            [{"name": "vnic1", "parent_interface": "eth0", "mac": "02:00:00:00:00:01"}],
            container_runtime=runtime,
        )

        assert valid is False
        assert "already in use" in error


class TestCreateRuntimeContainerSync:
    def _make_deps(self):
        runtime = MagicMock()
        runtime.NotFoundError = type("NotFoundError", (Exception,), {})
        runtime.ImageNotFound = type("ImageNotFound", (Exception,), {})
        runtime.APIError = type("APIError", (Exception,), {})
        vnic_repo = MagicMock()
        serial_repo = MagicMock()
        registry = MagicMock()
        cache = MagicMock()
        ops = MagicMock()
        buffer = MagicMock()
        return runtime, vnic_repo, serial_repo, registry, cache, ops, buffer

    @patch("use_cases.docker_manager.create_runtime_container._validate_mac_addresses")
    @patch("use_cases.docker_manager.create_runtime_container._validate_vnic_configs")
    def test_name_already_registered(self, mock_vnic_val, mock_mac_val):
        """client_registry.contains=True → None, sets error."""
        runtime, vnic_repo, serial_repo, registry, cache, ops, buffer = self._make_deps()
        registry.contains.return_value = True

        result = _create_runtime_container_sync(
            "plc1", [],
            container_runtime=runtime,
            vnic_repo=vnic_repo,
            serial_repo=serial_repo,
            client_registry=registry,
            interface_cache=cache,
            operations_state=ops,
            devices_usage_buffer=buffer,
        )

        assert result is None
        ops.set_error.assert_called_once()
        mock_vnic_val.assert_not_called()

    @patch("use_cases.docker_manager.create_runtime_container._validate_mac_addresses")
    @patch("use_cases.docker_manager.create_runtime_container._validate_vnic_configs")
    def test_vnic_validation_fails(self, mock_vnic_val, mock_mac_val):
        """Invalid vNICs → None, sets error."""
        runtime, vnic_repo, serial_repo, registry, cache, ops, buffer = self._make_deps()
        registry.contains.return_value = False
        mock_vnic_val.return_value = (False, "duplicate network")

        result = _create_runtime_container_sync(
            "plc1", [{"name": "v1", "parent_interface": "eth0"}],
            container_runtime=runtime,
            vnic_repo=vnic_repo,
            serial_repo=serial_repo,
            client_registry=registry,
            interface_cache=cache,
            operations_state=ops,
            devices_usage_buffer=buffer,
        )

        assert result is None
        ops.set_error.assert_called_once()


class TestStartCreation:
    @pytest.mark.asyncio
    @patch("tools.operations_state.begin_operation")
    @patch("use_cases.docker_manager.create_runtime_container.create_runtime_container")
    @patch("use_cases.docker_manager.create_runtime_container.asyncio")
    async def test_start_creation_success(self, mock_asyncio, mock_create, mock_begin):
        """Returns (status_dict, True) on success."""
        mock_begin.return_value = (None, True)
        ctx = MagicMock()

        result, started = await start_creation("plc1", [], ctx=ctx)

        assert started is True
        assert result["status"] == "creating"
        assert result["container_id"] == "plc1"

    @pytest.mark.asyncio
    @patch("tools.operations_state.begin_operation")
    async def test_start_creation_already_in_progress(self, mock_begin):
        """Returns (error, False) when operation already in progress."""
        error = {"status": "error", "error": "already in progress"}
        mock_begin.return_value = (error, False)
        ctx = MagicMock()

        result, started = await start_creation("plc1", [], ctx=ctx)

        assert started is False
        assert result["status"] == "error"
