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


class AppContext:
    """Holds all instantiated repos for dependency injection."""

    def __init__(self):
        self.container_runtime = ContainerRuntimeRepo()
        self.vnic_repo = VNICRepo()
        self.serial_repo = SerialRepo()
        self.client_registry = ClientRepo()
        self.http_client = HTTPClientRepo()
        self.network_interface_cache = NetworkInterfaceCacheRepo()


_context = None


def get_context() -> AppContext:
    """Return the singleton AppContext, creating it on first access."""
    global _context
    if _context is None:
        _context = AppContext()
    return _context
