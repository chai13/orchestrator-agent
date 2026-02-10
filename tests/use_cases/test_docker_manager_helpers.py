import pytest
from unittest.mock import MagicMock, patch

from use_cases.docker_manager import stop_and_remove_container, remove_internal_network


class _NotFoundError(Exception):
    """Fake NotFoundError for mocking container_runtime."""
    pass


def _make_runtime():
    """Create a MagicMock container_runtime with a real NotFoundError exception class."""
    mock_runtime = MagicMock()
    mock_runtime.NotFoundError = _NotFoundError
    return mock_runtime


class TestStopAndRemoveContainer:
    def test_stops_and_removes(self):
        mock_runtime = _make_runtime()
        mock_container = MagicMock()
        mock_runtime.get_container.return_value = mock_container

        stop_and_remove_container("plc1", container_runtime=mock_runtime)

        mock_runtime.get_container.assert_called_once_with("plc1")
        mock_container.stop.assert_called_once_with(timeout=10)
        mock_container.remove.assert_called_once_with(force=True)

    def test_not_found(self):
        mock_runtime = _make_runtime()
        mock_runtime.get_container.side_effect = _NotFoundError

        # Should not raise
        stop_and_remove_container("plc1", container_runtime=mock_runtime)

    def test_other_error_raises(self):
        mock_runtime = _make_runtime()
        mock_container = MagicMock()
        mock_runtime.get_container.return_value = mock_container
        mock_container.stop.side_effect = RuntimeError("Docker daemon error")

        with pytest.raises(RuntimeError, match="Docker daemon error"):
            stop_and_remove_container("plc1", container_runtime=mock_runtime)


class TestRemoveInternalNetwork:
    def test_removes_network(self):
        mock_runtime = _make_runtime()
        mock_network = MagicMock()
        mock_network.attrs = {"Containers": {}}
        mock_runtime.get_network.return_value = mock_network

        remove_internal_network("plc1", container_runtime=mock_runtime)

        mock_runtime.get_network.assert_called_once_with("plc1_internal")
        mock_network.reload.assert_called_once()
        mock_network.remove.assert_called_once()

    def test_not_found(self):
        mock_runtime = _make_runtime()
        mock_runtime.get_network.side_effect = _NotFoundError

        # Should not raise
        remove_internal_network("plc1", container_runtime=mock_runtime)

    def test_disconnect_all(self):
        mock_runtime = _make_runtime()
        mock_network = MagicMock()
        mock_network.attrs = {"Containers": {"cid1": {}, "cid2": {}}}
        mock_runtime.get_network.return_value = mock_network

        remove_internal_network("plc1", container_runtime=mock_runtime, disconnect_all=True)

        assert mock_network.disconnect.call_count == 2
        mock_network.remove.assert_called_once()

    @patch("use_cases.docker_manager.get_self_container")
    def test_disconnects_orchestrator_only(self, mock_get_self):
        mock_runtime = _make_runtime()
        mock_network = MagicMock()
        mock_main = MagicMock()
        mock_main.id = "orch-id"
        mock_get_self.return_value = mock_main
        mock_network.attrs = {"Containers": {"orch-id": {}, "other-id": {}}}
        mock_runtime.get_network.return_value = mock_network

        remove_internal_network("plc1", container_runtime=mock_runtime, disconnect_all=False)

        mock_network.disconnect.assert_called_once_with(mock_main, force=True)
        mock_network.remove.assert_called_once()
