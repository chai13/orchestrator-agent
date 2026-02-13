"""Tests for debug channel tracking in WebRTCSessionManager."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Patch aiortc before importing session_manager so RTCPeerConnection
# doesn't require a real event loop or native libraries during unit tests.
_mock_pc_instance = AsyncMock()

with patch("controllers.webrtc_controller.types.RTCConfiguration"), \
     patch("controllers.webrtc_controller.types.RTCIceServer"), \
     patch("controllers.webrtc_controller.session_manager.RTCPeerConnection", return_value=_mock_pc_instance):
    from controllers.webrtc_controller.session_manager import WebRTCSessionManager


@pytest.fixture
def manager():
    return WebRTCSessionManager()


# ---------------------------------------------------------------------------
# Session fields
# ---------------------------------------------------------------------------


class TestSessionFields:
    @pytest.mark.asyncio
    async def test_session_has_debug_channel_fields(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        session = manager.get_session("s1")
        assert session is not None
        assert "debug_channel" in session
        assert session["debug_channel"] is None
        assert "debug_channel_handler" in session
        assert session["debug_channel_handler"] is None


# ---------------------------------------------------------------------------
# set / get debug channel
# ---------------------------------------------------------------------------


class TestDebugChannel:
    @pytest.mark.asyncio
    async def test_set_debug_channel(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        mock_channel = MagicMock()
        result = manager.set_debug_channel("s1", mock_channel)

        assert result is True
        session = manager.get_session("s1")
        assert session["debug_channel"] is mock_channel

    @pytest.mark.asyncio
    async def test_set_debug_channel_handler(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        mock_handler = MagicMock()
        result = manager.set_debug_channel_handler("s1", mock_handler)

        assert result is True
        session = manager.get_session("s1")
        assert session["debug_channel_handler"] is mock_handler

    @pytest.mark.asyncio
    async def test_get_debug_channel_handler(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        mock_handler = MagicMock()
        manager.set_debug_channel_handler("s1", mock_handler)

        assert manager.get_debug_channel_handler("s1") is mock_handler

    def test_get_debug_channel_handler_missing_session(self, manager):
        assert manager.get_debug_channel_handler("nonexistent") is None


# ---------------------------------------------------------------------------
# Close / replace sessions clean up debug handler
# ---------------------------------------------------------------------------


class TestDebugHandlerCleanup:
    @pytest.mark.asyncio
    async def test_close_session_closes_debug_handler(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        mock_handler = MagicMock()
        manager.set_debug_channel_handler("s1", mock_handler)

        await manager.close_session("s1")

        mock_handler.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_replace_session_closes_debug_handler(self, manager):
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-1")

        mock_handler = MagicMock()
        manager.set_debug_channel_handler("s1", mock_handler)

        # Create another session with the same ID — should close the old one
        with patch(
            "controllers.webrtc_controller.session_manager.RTCPeerConnection",
            return_value=AsyncMock(),
        ):
            await manager.create_session("s1", "device-2")

        mock_handler.close.assert_called_once()
