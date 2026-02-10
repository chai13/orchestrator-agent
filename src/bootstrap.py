"""
Composition root: creates and wires all repos at startup.

This module provides a centralized AppContext that holds all repo instances,
enabling dependency injection throughout the application. Use get_context() to
access the singleton context.
"""

from repos import (
    ContainerRuntimeRepo,
    VNICRepo,
    SerialRepo,
    ClientRepo,
    HTTPClientRepo,
    NetworkInterfaceCacheRepo,
)
from tools.operations_state import OperationsStateTracker
from tools.devices_usage_buffer import DevicesUsageBuffer
from tools.network_event_listener import NetworkEventListener
from tools.logger import log_info


class AppContext:
    """Holds all instantiated repos for dependency injection."""

    def __init__(self):
        self.container_runtime = ContainerRuntimeRepo()
        self.vnic_repo = VNICRepo()
        self.serial_repo = SerialRepo()
        self.client_registry = ClientRepo()
        self.http_client = HTTPClientRepo()
        self.network_interface_cache = NetworkInterfaceCacheRepo()
        self.operations_state = OperationsStateTracker()
        self.devices_usage_buffer = DevicesUsageBuffer()
        self.network_event_listener = NetworkEventListener(
            interface_cache=self.network_interface_cache,
        )

        # Register existing clients for usage data collection at bootstrap time
        clients = self.client_registry.list_clients()
        if clients:
            for client_name in clients:
                self.devices_usage_buffer.add_device(client_name)
                log_info(f"Registered existing client {client_name} for usage data collection")


_context = None


def get_context() -> AppContext:
    """Return the singleton AppContext, creating it on first access."""
    global _context
    if _context is None:
        _context = AppContext()
    return _context
