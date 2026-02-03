from .websocket_controller import (
    init as init_websocket_controller,
    get_client as get_websocket_client,
)
from tools.logger import *
from tools.network_event_listener import network_event_listener


async def main_websocket_task(server_url, dns_ttl: int = 30):
    """
    Main function to connect the WebSocket client to the server.

    Creates a fresh Socket.IO client and HTTP session for each connection
    attempt. This ensures DNS is re-resolved after network changes.

    Args:
        server_url: The server URL to connect to (host:port format)
        dns_ttl: DNS cache TTL in seconds. Lower values help with network
                changes but increase DNS queries.
    """
    client = None
    try:
        # Create fresh client with new HTTP session for DNS refresh
        client = await get_websocket_client(dns_ttl=dns_ttl)
        init_websocket_controller(client)

        await network_event_listener.start()
        log_info("Network event listener started")

        await client.connect(
            f"https://{server_url}",
        )
        log_info(f"Connected to WebSocket server at {server_url}")
        await client.wait()
    finally:
        # Cleanup: close HTTP session to release resources
        if client is not None:
            try:
                if client.http and not client.http.closed:
                    await client.http.close()
                    log_debug("Closed HTTP session")
            except Exception as e:
                log_debug(f"Error closing HTTP session: {e}")


async def main_webrtc_task(*args, **kwargs):
    raise NotImplementedError("WebRTC task is not implemented yet.")
