import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch

from use_cases.dhcp_manager import DHCPManager, DHCP_RETRY_BACKOFF_BASE, DHCP_RETRY_BACKOFF_MAX


class _NotFoundError(Exception):
    pass


def _make_manager():
    netmon = MagicMock()
    netmon.dhcp_ip_cache = {}
    netmon.dhcp_update_callbacks = []
    runtime = MagicMock()
    runtime.NotFoundError = _NotFoundError
    vnic_repo = MagicMock()
    return DHCPManager(netmon, runtime, vnic_repo)


class TestHandleDhcpUpdate:
    @pytest.mark.asyncio
    async def test_incomplete_data_returns_early(self):
        """Missing required fields returns without saving."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {}

        await mgr.handle_dhcp_update({"container_name": "plc1"})

        mgr.vnic_repo.load_configs.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_cache_and_vnic_config(self):
        """Updates dhcp_ip_cache and persists to vnic_repo."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "eth_vnic", "network_mode": "dhcp"}]
        }

        await mgr.handle_dhcp_update({
            "container_name": "plc1",
            "vnic_name": "eth_vnic",
            "ip": "192.168.1.50",
            "gateway": "192.168.1.1",
            "dns": ["8.8.8.8"],
        })

        assert mgr.netmon_client.dhcp_ip_cache["plc1:eth_vnic"]["ip"] == "192.168.1.50"
        mgr.vnic_repo.save_configs.assert_called_once_with(
            "plc1",
            [{"name": "eth_vnic", "network_mode": "dhcp", "dhcp_ip": "192.168.1.50", "dhcp_gateway": "192.168.1.1", "dhcp_dns": ["8.8.8.8"]}],
        )

    @pytest.mark.asyncio
    async def test_saves_proxy_arp_config(self):
        """proxy_arp_config from data is saved to vnic_config."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "wifi_vnic"}]
        }

        proxy_config = {"veth_host": "veth-plc1", "ip_address": "10.0.0.5"}
        await mgr.handle_dhcp_update({
            "container_name": "plc1",
            "vnic_name": "wifi_vnic",
            "ip": "10.0.0.5",
            "proxy_arp_config": proxy_config,
        })

        saved_configs = mgr.vnic_repo.save_configs.call_args[0][1]
        assert saved_configs[0]["_proxy_arp_config"] == proxy_config

    @pytest.mark.asyncio
    async def test_invokes_callbacks(self):
        """Registered callbacks are called with update data."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {}

        sync_cb = MagicMock()
        async_cb = AsyncMock()
        mgr.netmon_client.dhcp_update_callbacks = [sync_cb, async_cb]

        data = {"container_name": "plc1", "vnic_name": "v1", "ip": "10.0.0.1"}
        await mgr.handle_dhcp_update(data)

        sync_cb.assert_called_once_with("plc1", "v1", data)
        async_cb.assert_called_once_with("plc1", "v1", data)

    @pytest.mark.asyncio
    async def test_container_not_in_configs(self):
        """Container not in vnic_repo configs → cache updated, no save."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {}

        await mgr.handle_dhcp_update({
            "container_name": "plc1",
            "vnic_name": "v1",
            "ip": "10.0.0.1",
        })

        assert "plc1:v1" in mgr.netmon_client.dhcp_ip_cache
        mgr.vnic_repo.save_configs.assert_not_called()


class TestGetNetworkSubnet:
    def test_returns_subnet(self):
        """Returns subnet from IPAM config."""
        mgr = _make_manager()
        network = MagicMock()
        network.attrs = {"IPAM": {"Config": [{"Subnet": "192.168.1.0/24"}]}}
        mgr.container_runtime.get_network.return_value = network

        result = mgr._get_network_subnet("macvlan_eth0", mgr.container_runtime)

        assert result == "192.168.1.0/24"

    def test_returns_none_on_empty_config(self):
        """No IPAM config returns None."""
        mgr = _make_manager()
        network = MagicMock()
        network.attrs = {"IPAM": {"Config": []}}
        mgr.container_runtime.get_network.return_value = network

        result = mgr._get_network_subnet("macvlan_eth0", mgr.container_runtime)

        assert result is None

    def test_returns_none_on_exception(self):
        """Exception returns None."""
        mgr = _make_manager()
        mgr.container_runtime.get_network.side_effect = RuntimeError("boom")

        result = mgr._get_network_subnet("macvlan_eth0", mgr.container_runtime)

        assert result is None


class TestScheduleNextRetry:
    def test_increments_retry_count(self):
        """Retry count incremented by 1."""
        mgr = _make_manager()
        state = {"retry_count": 0, "next_retry_at": 0}

        mgr._schedule_next_retry("plc1:v1", state)

        assert state["retry_count"] == 1

    def test_exponential_backoff(self):
        """Delay grows exponentially."""
        mgr = _make_manager()
        state = {"retry_count": 2, "next_retry_at": 0}

        before = time.time()
        mgr._schedule_next_retry("plc1:v1", state)

        # After retry_count becomes 3: base * 2^3 = 1.0 * 8 = 8.0 (before jitter)
        # With 30% jitter: 8 * 0.7 to 8 * 1.3 = 5.6 to 10.4
        expected_min = before + DHCP_RETRY_BACKOFF_BASE
        assert state["next_retry_at"] >= expected_min

    def test_capped_at_max(self):
        """Delay doesn't exceed DHCP_RETRY_BACKOFF_MAX."""
        mgr = _make_manager()
        state = {"retry_count": 20, "next_retry_at": 0}

        mgr._schedule_next_retry("plc1:v1", state)

        max_possible = time.time() + DHCP_RETRY_BACKOFF_MAX * 1.3 + 1
        assert state["next_retry_at"] <= max_possible


class TestResyncDhcpForExistingContainers:
    @pytest.mark.asyncio
    async def test_no_vnic_configs(self):
        """Empty configs → early return, no DHCP started."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {}

        await mgr.resync_dhcp_for_existing_containers()

        mgr.netmon_client.start_dhcp.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_static_vnics(self):
        """Static network_mode vNICs skipped."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "v1", "network_mode": "static", "parent_interface": "eth0"}]
        }

        await mgr.resync_dhcp_for_existing_containers()

        mgr.container_runtime.get_container.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_running_containers(self):
        """Non-running containers skipped."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "v1", "network_mode": "dhcp", "parent_interface": "eth0"}]
        }
        container = MagicMock()
        container.status = "exited"
        mgr.container_runtime.get_container.return_value = container

        await mgr.resync_dhcp_for_existing_containers()

        mgr.netmon_client.start_dhcp.assert_not_called()

    @pytest.mark.asyncio
    async def test_starts_dhcp_for_macvlan(self):
        """Running container with MACVLAN gets DHCP started via netmon."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "v1", "network_mode": "dhcp", "parent_interface": "eth0"}]
        }
        container = MagicMock()
        container.status = "running"
        container.attrs = {
            "State": {"Pid": 1234},
            "NetworkSettings": {
                "Networks": {
                    "macvlan_eth0_192_168_1_0_24": {"MacAddress": "02:00:00:00:00:01"}
                }
            },
        }
        mgr.container_runtime.get_container.return_value = container
        mgr.netmon_client.start_dhcp = AsyncMock(return_value={"success": True})

        await mgr.resync_dhcp_for_existing_containers()

        mgr.netmon_client.start_dhcp.assert_called_once_with(
            "plc1", "v1", "02:00:00:00:00:01", 1234
        )

    @pytest.mark.asyncio
    async def test_container_not_found_skipped(self):
        """NotFoundError for container is handled gracefully."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "v1", "network_mode": "dhcp", "parent_interface": "eth0"}]
        }
        mgr.container_runtime.get_container.side_effect = _NotFoundError

        # Should not raise
        await mgr.resync_dhcp_for_existing_containers()

    @pytest.mark.asyncio
    async def test_proxy_arp_vnic_uses_wifi_dhcp(self):
        """WiFi/Proxy ARP vNIC uses request_wifi_dhcp instead of start_dhcp."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{
                "name": "wifi_v1",
                "network_mode": "dhcp",
                "parent_interface": "wlan0",
                "_proxy_arp_config": {"veth_host": "veth-plc1"},
            }]
        }
        container = MagicMock()
        container.status = "running"
        container.attrs = {"State": {"Pid": 5678}}
        mgr.container_runtime.get_container.return_value = container
        mgr.netmon_client.request_wifi_dhcp = AsyncMock(return_value={"success": True})

        await mgr.resync_dhcp_for_existing_containers()

        mgr.netmon_client.request_wifi_dhcp.assert_called_once_with(
            "plc1", "wifi_v1", "wlan0", 5678
        )

    @pytest.mark.asyncio
    async def test_failed_dhcp_added_to_pending(self):
        """Failed DHCP resync adds entry to pending_dhcp_resyncs."""
        mgr = _make_manager()
        mgr.vnic_repo.load_configs.return_value = {
            "plc1": [{"name": "v1", "network_mode": "dhcp", "parent_interface": "eth0"}]
        }
        container = MagicMock()
        container.status = "running"
        container.attrs = {
            "State": {"Pid": 1234},
            "NetworkSettings": {
                "Networks": {
                    "macvlan_eth0_net": {"MacAddress": "02:00:00:00:00:01"}
                }
            },
        }
        mgr.container_runtime.get_container.return_value = container
        mgr.netmon_client.start_dhcp = AsyncMock(return_value={"success": False, "error": "timeout"})

        await mgr.resync_dhcp_for_existing_containers()

        assert "plc1:v1" in mgr.pending_dhcp_resyncs
        assert mgr.pending_dhcp_resyncs["plc1:v1"]["retry_count"] == 0


class TestStop:
    @pytest.mark.asyncio
    async def test_cancels_retry_task(self):
        """Sets running=False and cancels dhcp_retry_task."""
        import asyncio

        mgr = _make_manager()
        mgr.running = True

        # Create a real asyncio task that sleeps forever (simulates the retry loop)
        async def _forever():
            await asyncio.sleep(9999)

        mgr.dhcp_retry_task = asyncio.create_task(_forever())

        await mgr.stop()

        assert mgr.running is False
        assert mgr.dhcp_retry_task.cancelled()
