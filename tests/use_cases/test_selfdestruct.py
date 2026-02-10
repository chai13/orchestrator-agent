import pytest
from unittest.mock import MagicMock, patch, call

from use_cases.docker_manager.selfdestruct import (
    start_self_destruct,
    _cleanup_orchestrator_networks,
    _delete_netmon_container,
    _delete_shared_volume,
    _delete_orchestrator_container,
    self_destruct,
    ORCHESTRATOR_STATUS_ID,
    NETMON_CONTAINER_NAME,
    SHARED_VOLUME_NAME,
)


class _NotFoundError(Exception):
    pass


def _make_runtime():
    mock_runtime = MagicMock()
    mock_runtime.NotFoundError = _NotFoundError
    return mock_runtime


class TestStartSelfDestruct:
    def test_success(self):
        """Returns True, sets deleting state."""
        ops = MagicMock()
        ops.set_deleting.return_value = True

        result = start_self_destruct(operations_state=ops)

        assert result is True
        ops.set_deleting.assert_called_once_with(ORCHESTRATOR_STATUS_ID)
        ops.set_step.assert_called_once_with(ORCHESTRATOR_STATUS_ID, "starting")

    def test_already_in_progress(self):
        """Returns False when self-destruct already in progress."""
        ops = MagicMock()
        ops.set_deleting.return_value = False

        result = start_self_destruct(operations_state=ops)

        assert result is False


class TestCleanupOrchestratorNetworks:
    def test_removes_matching_networks(self):
        """Regex matching removes internal and macvlan networks."""
        runtime = _make_runtime()
        internal_net = MagicMock()
        internal_net.name = "abcdef01-2345-6789-abcd-ef0123456789_internal"
        internal_net.attrs = {"Containers": {}}

        macvlan_net = MagicMock()
        macvlan_net.name = "macvlan_eth0_192.168.1.0_24"
        macvlan_net.attrs = {"Containers": {}}

        other_net = MagicMock()
        other_net.name = "bridge"

        runtime.list_networks.return_value = [internal_net, macvlan_net, other_net]

        _cleanup_orchestrator_networks(runtime)

        internal_net.remove.assert_called_once()
        macvlan_net.remove.assert_called_once()
        other_net.remove.assert_not_called()

    def test_skips_connected_networks(self):
        """Networks with containers are skipped."""
        runtime = _make_runtime()
        net = MagicMock()
        net.name = "abcdef01-2345-6789-abcd-ef0123456789_internal"
        net.attrs = {"Containers": {"container1": {}}}
        runtime.list_networks.return_value = [net]

        _cleanup_orchestrator_networks(runtime)

        net.remove.assert_not_called()


class TestDeleteNetmonContainer:
    def test_stops_and_removes(self):
        """Stops and removes autonomy_netmon."""
        runtime = _make_runtime()
        container = MagicMock()
        runtime.get_container.return_value = container

        _delete_netmon_container(runtime)

        runtime.get_container.assert_called_once_with(NETMON_CONTAINER_NAME)
        container.stop.assert_called_once_with(timeout=10)
        container.remove.assert_called_once_with(force=True)

    def test_not_found(self):
        """NotFoundError handled gracefully."""
        runtime = _make_runtime()
        runtime.get_container.side_effect = _NotFoundError

        # Should not raise
        _delete_netmon_container(runtime)


class TestDeleteSharedVolume:
    def test_removes_volume(self):
        """Removes volume."""
        runtime = _make_runtime()
        volume = MagicMock()
        runtime.get_volume.return_value = volume

        _delete_shared_volume(runtime)

        runtime.get_volume.assert_called_once_with(SHARED_VOLUME_NAME)
        volume.remove.assert_called_once_with(force=True)


class TestDeleteOrchestratorContainer:
    @patch("use_cases.docker_manager.selfdestruct.get_self_container")
    def test_removes_self(self, mock_get_self):
        """get_self_container → remove."""
        runtime = _make_runtime()
        self_container = MagicMock()
        self_container.name = "orchestrator_agent"
        mock_get_self.return_value = self_container

        _delete_orchestrator_container(runtime)

        self_container.remove.assert_called_once_with(force=True)

    @patch("use_cases.docker_manager.selfdestruct.get_self_container")
    def test_not_found_raises(self, mock_get_self):
        """get_self_container=None → raises RuntimeError."""
        runtime = _make_runtime()
        mock_get_self.return_value = None

        with pytest.raises(RuntimeError, match="Could not detect"):
            _delete_orchestrator_container(runtime)


class TestSelfDestruct:
    @patch("use_cases.docker_manager.selfdestruct._delete_orchestrator_container")
    @patch("use_cases.docker_manager.selfdestruct._delete_shared_volume")
    @patch("use_cases.docker_manager.selfdestruct._delete_netmon_container")
    @patch("use_cases.docker_manager.selfdestruct._cleanup_proxy_arp_veths")
    @patch("use_cases.docker_manager.selfdestruct._cleanup_orchestrator_networks")
    @patch("use_cases.docker_manager.selfdestruct._delete_all_runtime_containers")
    def test_full_sequence(
        self,
        mock_delete_all,
        mock_cleanup_nets,
        mock_cleanup_veths,
        mock_delete_netmon,
        mock_delete_vol,
        mock_delete_orch,
    ):
        """All steps called in order with state tracking."""
        runtime = _make_runtime()
        registry = MagicMock()
        vnic_repo = MagicMock()
        ops = MagicMock()
        buffer = MagicMock()

        self_destruct(
            container_runtime=runtime,
            client_registry=registry,
            vnic_repo=vnic_repo,
            operations_state=ops,
            devices_usage_buffer=buffer,
        )

        mock_delete_all.assert_called_once_with(runtime, registry, vnic_repo, buffer)
        mock_cleanup_nets.assert_called_once_with(runtime)
        mock_cleanup_veths.assert_called_once()
        mock_delete_netmon.assert_called_once_with(runtime)
        mock_delete_vol.assert_called_once_with(runtime)
        mock_delete_orch.assert_called_once_with(runtime)

        # Verify steps were set
        ops.set_step.assert_any_call(ORCHESTRATOR_STATUS_ID, "deleting_runtimes")
        ops.set_step.assert_any_call(ORCHESTRATOR_STATUS_ID, "cleaning_networks")
        ops.set_step.assert_any_call(ORCHESTRATOR_STATUS_ID, "removing_self")

    @patch("use_cases.docker_manager.selfdestruct._delete_all_runtime_containers")
    def test_error_sets_state(self, mock_delete_all):
        """Exception → operations_state.set_error."""
        runtime = _make_runtime()
        registry = MagicMock()
        vnic_repo = MagicMock()
        ops = MagicMock()
        buffer = MagicMock()
        mock_delete_all.side_effect = RuntimeError("Docker error")

        with pytest.raises(RuntimeError):
            self_destruct(
                container_runtime=runtime,
                client_registry=registry,
                vnic_repo=vnic_repo,
                operations_state=ops,
                devices_usage_buffer=buffer,
            )

        ops.set_error.assert_called_once_with(
            ORCHESTRATOR_STATUS_ID, "Docker error", "self_destruct"
        )
