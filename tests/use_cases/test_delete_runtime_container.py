import pytest
from unittest.mock import MagicMock, patch, call

from use_cases.docker_manager.delete_runtime_container import (
    _delete_runtime_container_sync,
    start_deletion,
)


class _NotFoundError(Exception):
    pass


def _make_runtime():
    mock_runtime = MagicMock()
    mock_runtime.NotFoundError = _NotFoundError
    return mock_runtime


def _make_deps():
    runtime = _make_runtime()
    registry = MagicMock()
    vnic_repo = MagicMock()
    serial_repo = MagicMock()
    ops = MagicMock()
    buffer = MagicMock()
    return runtime, registry, vnic_repo, serial_repo, ops, buffer


def _call_sync(name, runtime, registry, vnic_repo, serial_repo, ops, buffer):
    return _delete_runtime_container_sync(
        name,
        container_runtime=runtime,
        client_registry=registry,
        vnic_repo=vnic_repo,
        serial_repo=serial_repo,
        operations_state=ops,
        devices_usage_buffer=buffer,
    )


class TestDeleteRuntimeContainerSync:
    @patch("use_cases.docker_manager.delete_runtime_container.stop_and_remove_container")
    @patch("use_cases.docker_manager.delete_runtime_container.remove_internal_network")
    def test_sync_deletion_success(self, mock_remove_net, mock_stop):
        """Full cleanup sequence verified via mock calls."""
        runtime, registry, vnic_repo, serial_repo, ops, buffer = _make_deps()
        registry.contains.return_value = True

        _call_sync("plc1", runtime, registry, vnic_repo, serial_repo, ops, buffer)

        mock_stop.assert_called_once_with("plc1", container_runtime=runtime)
        registry.remove_client.assert_called_once_with("plc1")
        buffer.remove_device.assert_called_once_with("plc1")
        vnic_repo.delete_configs.assert_called_once_with("plc1")
        serial_repo.delete_configs.assert_called_once_with("plc1")
        mock_remove_net.assert_called_once_with("plc1", container_runtime=runtime)

    @patch("use_cases.docker_manager.delete_runtime_container.stop_and_remove_container")
    @patch("use_cases.docker_manager.delete_runtime_container.remove_internal_network")
    def test_sync_deletion_sets_steps(self, mock_remove_net, mock_stop):
        """set_step called with 'stopping_container' and 'removing_networks'."""
        runtime, registry, vnic_repo, serial_repo, ops, buffer = _make_deps()

        _call_sync("plc1", runtime, registry, vnic_repo, serial_repo, ops, buffer)

        ops.set_step.assert_any_call("plc1", "stopping_container")
        ops.set_step.assert_any_call("plc1", "removing_networks")

    @patch("use_cases.docker_manager.delete_runtime_container.stop_and_remove_container")
    @patch("use_cases.docker_manager.delete_runtime_container.remove_internal_network")
    def test_sync_deletion_clears_state_on_success(self, mock_remove_net, mock_stop):
        """clear_state called on successful completion."""
        runtime, registry, vnic_repo, serial_repo, ops, buffer = _make_deps()

        _call_sync("plc1", runtime, registry, vnic_repo, serial_repo, ops, buffer)

        ops.clear_state.assert_called_once_with("plc1")

    @patch("use_cases.docker_manager.delete_runtime_container.stop_and_remove_container")
    def test_sync_deletion_sets_error_on_failure(self, mock_stop):
        """Exception → set_error called, re-raises."""
        runtime, registry, vnic_repo, serial_repo, ops, buffer = _make_deps()
        mock_stop.side_effect = RuntimeError("Docker daemon error")

        with pytest.raises(RuntimeError, match="Docker daemon error"):
            _call_sync("plc1", runtime, registry, vnic_repo, serial_repo, ops, buffer)

        ops.set_error.assert_called_once_with("plc1", "Docker daemon error", "delete")

    @patch("use_cases.docker_manager.delete_runtime_container.stop_and_remove_container")
    @patch("use_cases.docker_manager.delete_runtime_container.remove_internal_network")
    def test_sync_deletion_continues_after_registry_error(self, mock_remove_net, mock_stop):
        """Registry error doesn't stop deletion."""
        runtime, registry, vnic_repo, serial_repo, ops, buffer = _make_deps()
        registry.remove_client.side_effect = RuntimeError("registry error")

        # Should NOT raise
        _call_sync("plc1", runtime, registry, vnic_repo, serial_repo, ops, buffer)

        # Deletion continues — vnic_repo and serial_repo still called
        vnic_repo.delete_configs.assert_called_once()
        serial_repo.delete_configs.assert_called_once()
        mock_remove_net.assert_called_once()
        ops.clear_state.assert_called_once_with("plc1")


class TestStartDeletion:
    @pytest.mark.asyncio
    @patch("tools.operations_state.begin_operation")
    @patch("use_cases.docker_manager.delete_runtime_container.delete_runtime_container")
    @patch("use_cases.docker_manager.delete_runtime_container.asyncio")
    async def test_start_deletion_success(self, mock_asyncio, mock_delete, mock_begin):
        """Returns (status_dict, True) on success."""
        mock_begin.return_value = (None, True)
        ctx = MagicMock()

        result, started = await start_deletion("plc1", ctx=ctx)

        assert started is True
        assert result["status"] == "deleting"
        assert result["device_id"] == "plc1"

    @pytest.mark.asyncio
    @patch("tools.operations_state.begin_operation")
    async def test_start_deletion_already_in_progress(self, mock_begin):
        """Returns (error, False) when operation already in progress."""
        error = {"status": "error", "error": "already in progress"}
        mock_begin.return_value = (error, False)
        ctx = MagicMock()

        result, started = await start_deletion("plc1", ctx=ctx)

        assert started is False
        assert result["status"] == "error"
