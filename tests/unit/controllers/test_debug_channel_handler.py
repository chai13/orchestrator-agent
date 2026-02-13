"""Tests for controllers.webrtc_controller.data_channel.debug_channel_handler."""

from unittest.mock import MagicMock, AsyncMock, patch, call
import json

import pytest

from controllers.webrtc_controller.data_channel.debug_channel_handler import (
    DebugChannelHandler,
)


def _make_channel():
    """Create a mock RTCDataChannel that records .on() decorator registrations."""
    channel = MagicMock()
    channel.readyState = "open"
    handlers = {}

    def fake_on(event):
        def decorator(fn):
            handlers[event] = fn
            return fn
        return decorator

    channel.on = MagicMock(side_effect=fake_on)
    return channel, handlers


def _make_deps():
    """Create standard mocked dependencies including injected factories."""
    channel, handlers = _make_channel()
    session_manager = MagicMock()
    client_registry = MagicMock()
    http_client_factory = MagicMock()
    debug_socket_factory = MagicMock()
    return channel, handlers, session_manager, client_registry, http_client_factory, debug_socket_factory


def _make_handler(channel, sm, cr, http_factory, debug_factory):
    """Build a DebugChannelHandler with all injected dependencies."""
    return DebugChannelHandler(
        channel, "sess-1", sm, cr,
        http_client_factory=http_factory,
        debug_socket_factory=debug_factory,
    )


# ---------------------------------------------------------------------------
# Setup / event registration
# ---------------------------------------------------------------------------


class TestSetup:
    def test_setup_registers_event_handlers(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        _make_handler(channel, sm, cr, hf, df)

        assert "open" in handlers
        assert "close" in handlers
        assert "error" in handlers
        assert "message" in handlers

    def test_debug_ready_sent_on_open(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        _make_handler(channel, sm, cr, hf, df)

        handlers["open"]()

        channel.send.assert_called_once()
        sent = json.loads(channel.send.call_args[0][0])
        assert sent == {"type": "debug_ready"}


# ---------------------------------------------------------------------------
# debug_start handling
# ---------------------------------------------------------------------------


class TestDebugStart:
    @pytest.mark.asyncio
    async def test_debug_start_looks_up_device(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        cr.get_client.return_value = {"ip": "10.0.0.5"}
        handler = _make_handler(channel, sm, cr, hf, df)

        msg = json.dumps({
            "type": "debug_start",
            "device_id": "plc-1",
            "username": "dev",
            "password": "dev",
            "port": 8443,
        })

        with patch(
            "controllers.webrtc_controller.data_channel.debug_channel_handler.validate_debug_session"
        ) as mock_validate:
            mock_validate.return_value = {"status": "success", "steps": []}
            await handler._handle_message(msg)

        cr.get_client.assert_called_once_with("plc-1")

    @pytest.mark.asyncio
    async def test_debug_start_device_not_found(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        cr.get_client.return_value = None
        handler = _make_handler(channel, sm, cr, hf, df)

        msg = json.dumps({
            "type": "debug_start",
            "device_id": "missing-plc",
        })

        await handler._handle_message(msg)

        # Should send debug_error with "not found" message
        calls = channel.send.call_args_list
        sent = json.loads(calls[-1][0][0])
        assert sent["type"] == "debug_error"
        assert "not found" in sent["error"].lower()

    @pytest.mark.asyncio
    async def test_debug_start_calls_validate_session(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        cr.get_client.return_value = {"ip": "10.0.0.5"}
        handler = _make_handler(channel, sm, cr, hf, df)

        msg = json.dumps({
            "type": "debug_start",
            "device_id": "plc-1",
            "username": "admin",
            "password": "secret",
            "port": 9999,
        })

        with patch(
            "controllers.webrtc_controller.data_channel.debug_channel_handler.validate_debug_session"
        ) as mock_validate:
            mock_validate.return_value = {"status": "success", "steps": []}
            await handler._handle_message(msg)

            mock_validate.assert_called_once()
            args, kwargs = mock_validate.call_args
            assert args[0] == "10.0.0.5"
            assert args[1] == "admin"
            assert args[2] == "secret"
            assert kwargs["port"] == 9999
            assert kwargs["http_client"] is hf.return_value
            assert kwargs["debug_socket"] is df.return_value

    @pytest.mark.asyncio
    async def test_debug_complete_sent_on_success(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        cr.get_client.return_value = {"ip": "10.0.0.5"}
        handler = _make_handler(channel, sm, cr, hf, df)

        msg = json.dumps({
            "type": "debug_start",
            "device_id": "plc-1",
        })

        with patch(
            "controllers.webrtc_controller.data_channel.debug_channel_handler.validate_debug_session"
        ) as mock_validate:
            mock_validate.return_value = {
                "status": "success",
                "steps": [{"command": "DEBUG_GET_MD5"}],
            }
            await handler._handle_message(msg)

        calls = channel.send.call_args_list
        sent = json.loads(calls[-1][0][0])
        assert sent["type"] == "debug_complete"
        assert sent["status"] == "success"
        assert len(sent["steps"]) == 1

    @pytest.mark.asyncio
    async def test_debug_error_sent_on_exception(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        cr.get_client.return_value = {"ip": "10.0.0.5"}
        handler = _make_handler(channel, sm, cr, hf, df)

        msg = json.dumps({
            "type": "debug_start",
            "device_id": "plc-1",
        })

        with patch(
            "controllers.webrtc_controller.data_channel.debug_channel_handler.validate_debug_session"
        ) as mock_validate:
            mock_validate.side_effect = RuntimeError("connection lost")
            await handler._handle_message(msg)

        calls = channel.send.call_args_list
        sent = json.loads(calls[-1][0][0])
        assert sent["type"] == "debug_error"
        assert "connection lost" in sent["error"]


# ---------------------------------------------------------------------------
# Close and cleanup
# ---------------------------------------------------------------------------


class TestCloseAndCleanup:
    def test_close_sets_closed_flag(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        handler = _make_handler(channel, sm, cr, hf, df)

        assert handler.is_closed is False
        handler.close()
        assert handler.is_closed is True

    def test_no_messages_after_close(self):
        channel, handlers, sm, cr, hf, df = _make_deps()
        handler = _make_handler(channel, sm, cr, hf, df)

        handler.close()
        channel.send.reset_mock()

        handler._send_message({"type": "debug_ready"})
        channel.send.assert_not_called()

    def test_unknown_message_type_ignored(self):
        """Sending an unknown message type does not crash."""
        channel, handlers, sm, cr, hf, df = _make_deps()
        handler = _make_handler(channel, sm, cr, hf, df)

        # Should not raise
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            handler._handle_message(json.dumps({"type": "unknown_thing"}))
        )
