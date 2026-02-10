import os
import socket
from tools.logger import log_debug, log_warning

HOST_NAME = os.getenv("HOST_NAME", "orchestrator-agent-devcontainer")


def get_self_container(*, container_runtime):
    """
    Detect the orchestrator-agent's own container from inside the container.

    Tries multiple methods in order:
    1. HOSTNAME environment variable (Docker sets this to container ID by default)
    2. socket.gethostname() (usually returns container ID)
    3. HOST_NAME environment variable (explicit override)
    4. Search by label edge.autonomy.role=orchestrator-agent

    Args:
        container_runtime: Optional ContainerRuntimeRepo adapter (defaults to singleton)

    Returns the container object or None if not found.
    """
    container_id = os.getenv("HOSTNAME")
    if container_id:
        try:
            container = container_runtime.get_container(container_id)
            log_debug(f"Found self container via HOSTNAME env: {container.name}")
            return container
        except container_runtime.NotFoundError:
            log_debug(f"HOSTNAME env {container_id} not found as container")

    try:
        hostname = socket.gethostname()
        container = container_runtime.get_container(hostname)
        log_debug(f"Found self container via socket.gethostname(): {container.name}")
        return container
    except container_runtime.NotFoundError:
        log_debug(f"socket.gethostname() {hostname} not found as container")
    except Exception as e:
        log_debug(f"Error getting hostname: {e}")

    if HOST_NAME:
        try:
            container = container_runtime.get_container(HOST_NAME)
            log_debug(f"Found self container via HOST_NAME env: {container.name}")
            return container
        except container_runtime.NotFoundError:
            log_debug(f"HOST_NAME env {HOST_NAME} not found as container")

    try:
        containers = container_runtime.list_containers(
            filters={"label": "edge.autonomy.role=orchestrator-agent"}
        )
        if containers:
            container = containers[0]
            log_debug(f"Found self container via label: {container.name}")
            return container
    except Exception as e:
        log_debug(f"Error searching by label: {e}")

    log_warning("Could not detect self container using any method")
    return None
