"""
Debug Channel Handler

Manages a dedicated 'debug' WebRTC DataChannel for bridging the OpenPLC
debug protocol from the browser to a runtime container.

Message Protocol:
    Browser -> Agent:
        {"type": "debug_start", "device_id": "plc1", "username": "dev", "password": "dev", "port": 8443}

    Agent -> Browser (per step):
        {"type": "debug_step", "command": "DEBUG_GET_MD5", "raw_request": "...", "raw_response": "...", "parsed": {...}}

    Agent -> Browser (final):
        {"type": "debug_complete", "status": "success", "steps": [...]}

    Agent -> Browser (error):
        {"type": "debug_error", "error": "..."}
"""

from tools.logger import log_info, log_debug, log_error, log_warning
from use_cases.debug_client.validate_session import validate_debug_session
import json
import asyncio


class DebugChannelHandler:
    """
    Handles a 'debug'-labeled WebRTC DataChannel.

    On receiving a debug_start message, authenticates with the runtime,
    runs the debug session, and streams each step result back to the browser.
    """

    def __init__(self, data_channel, session_id, session_manager, client_registry,
                 *, http_client_factory, debug_socket_factory):
        """
        Initialize debug channel handler.

        Args:
            data_channel: RTCDataChannel instance (label='debug')
            session_id: Associated WebRTC session ID
            session_manager: WebRTCSessionManager instance
            client_registry: ClientRepo instance for device IP lookups
            http_client_factory: Callable returning an HTTPClientRepo instance
            debug_socket_factory: Callable returning a DebugSocketRepo instance
        """
        self.channel = data_channel
        self.session_id = session_id
        self.session_manager = session_manager
        self.client_registry = client_registry
        self._http_client_factory = http_client_factory
        self._debug_socket_factory = debug_socket_factory
        self._closed = False
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up debug data channel event handlers."""
        log_info(f"Setting up debug channel handlers for session {self.session_id}")

        @self.channel.on("open")
        def on_open():
            log_info(f"Debug channel OPEN for session {self.session_id}")
            self._send_message({"type": "debug_ready"})

        @self.channel.on("close")
        def on_close():
            log_info(f"Debug channel CLOSED for session {self.session_id}")
            self.close()

        @self.channel.on("error")
        def on_error(error):
            log_error(f"Debug channel ERROR for session {self.session_id}: {error}")

        @self.channel.on("message")
        def on_message(message):
            asyncio.create_task(self._handle_message(message))

    async def _handle_message(self, raw_message):
        """Handle incoming debug channel message."""
        if self._closed:
            return

        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            message = json.loads(raw_message)
            msg_type = message.get("type")

            if self.session_manager:
                self.session_manager.touch_session(self.session_id)

            if msg_type == "debug_start":
                await self._handle_debug_start(message)
            else:
                log_debug(f"Unknown debug channel message type: {msg_type}")

        except json.JSONDecodeError as e:
            log_error(f"Invalid JSON on debug channel {self.session_id}: {e}")
        except Exception as e:
            log_error(f"Error handling debug channel message {self.session_id}: {e}")

    async def _handle_debug_start(self, message):
        """
        Handle debug_start message.

        Creates fresh repo instances via the injected factories,
        runs the debug session in a worker thread, and streams results
        back to the browser.
        """
        device_id = message.get("device_id")
        username = message.get("username", "dev")
        password = message.get("password", "dev")
        port = message.get("port", 8443)

        log_info(f"Debug session requested for device {device_id}")

        # Look up device IP
        client = self.client_registry.get_client(device_id)
        if not client:
            self._send_message({
                "type": "debug_error",
                "error": f"Device {device_id} not found",
            })
            return

        device_ip = client["ip"]
        log_info(f"Starting debug session for {device_id} at {device_ip}:{port}")

        # Capture the event loop for thread-safe callbacks
        loop = asyncio.get_running_loop()

        def on_step(step):
            """Called from worker thread after each debug step completes."""
            loop.call_soon_threadsafe(
                self._send_message,
                {"type": "debug_step", **step},
            )

        try:
            # Create fresh repos for this debug session
            http_client = self._http_client_factory()
            debug_socket = self._debug_socket_factory()

            result = await asyncio.to_thread(
                validate_debug_session,
                device_ip,
                username,
                password,
                http_client=http_client,
                debug_socket=debug_socket,
                port=port,
                on_step=on_step,
            )

            self._send_message({
                "type": "debug_complete",
                "status": result.get("status", "error"),
                "steps": result.get("steps", []),
                "error": result.get("error"),
            })

        except Exception as e:
            log_error(f"Debug session failed for {device_id}: {e}")
            self._send_message({
                "type": "debug_error",
                "error": str(e),
            })

    def _send_message(self, message):
        """Send a JSON message on the debug channel."""
        if self._closed or not self.channel:
            return

        try:
            if self.channel.readyState == "open":
                self.channel.send(json.dumps(message))
            else:
                log_debug(f"Cannot send debug message, channel state: {self.channel.readyState}")
        except Exception as e:
            log_error(f"Error sending debug message in session {self.session_id}: {e}")

    def close(self):
        """Close the debug channel handler and cleanup."""
        if self._closed:
            return

        self._closed = True
        log_info(f"Closing debug channel handler for session {self.session_id}")

        if self.channel:
            try:
                self.channel.close()
            except Exception as e:
                log_debug(f"Error closing debug channel: {e}")

        log_info(f"Debug channel handler closed for session {self.session_id}")

    @property
    def is_closed(self):
        """Check if handler is closed."""
        return self._closed
