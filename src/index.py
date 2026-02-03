## Main Execution Script
from controllers import main_websocket_task
from tools.logger import *
import argparse
import asyncio
import socket
import random
from time import sleep

## AWS Server Address
SERVER_HOST = "api.autonomylogic.com:3001"

# Reconnection configuration
RECONNECT_DELAY_BASE = 1.0  # Initial delay in seconds
RECONNECT_DELAY_MAX = 30.0  # Maximum delay in seconds
RECONNECT_JITTER = 0.3  # Jitter factor (30%)
DNS_HEALTH_CHECK_TIMEOUT = 5.0  # DNS health check timeout in seconds
DNS_HEALTH_CHECK_RETRIES = 3  # Number of DNS health check retries


def wait_for_dns(host: str, port: int, max_retries: int = DNS_HEALTH_CHECK_RETRIES) -> bool:
    """
    Wait until DNS resolution succeeds for the given host.

    This helps avoid rapid reconnection attempts when the network is still
    transitioning (e.g., after WiFi change).

    Args:
        host: Hostname to resolve
        port: Port number (for getaddrinfo)
        max_retries: Maximum number of DNS resolution attempts

    Returns:
        True if DNS resolution succeeded, False if all retries failed
    """
    for attempt in range(max_retries):
        try:
            # Force fresh DNS lookup by not using any caching hints
            socket.setdefaulttimeout(DNS_HEALTH_CHECK_TIMEOUT)
            result = socket.getaddrinfo(
                host, port,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
                0,
                socket.AI_ADDRCONFIG  # Only return addresses reachable from this host
            )
            if result:
                log_debug(f"DNS health check passed for {host}:{port}")
                return True
        except socket.gaierror as e:
            log_warning(f"DNS health check failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(2)  # Wait before retry
        except Exception as e:
            log_warning(f"DNS health check error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(2)

    return False


def calculate_backoff(attempt: int) -> float:
    """
    Calculate reconnection delay with exponential backoff and jitter.

    Args:
        attempt: Current reconnection attempt number (0-indexed)

    Returns:
        Delay in seconds before next reconnection attempt
    """
    # Exponential backoff: base * 2^attempt, capped at max
    delay = min(RECONNECT_DELAY_BASE * (2 ** attempt), RECONNECT_DELAY_MAX)

    # Add jitter (±30%) to prevent thundering herd
    jitter = delay * RECONNECT_JITTER * (2 * random.random() - 1)
    delay = max(RECONNECT_DELAY_BASE, delay + jitter)

    return delay


def is_dns_error(error: Exception) -> bool:
    """
    Check if the error is related to DNS resolution failure.

    Args:
        error: The exception to check

    Returns:
        True if this appears to be a DNS-related error
    """
    error_str = str(error).lower()
    dns_error_indicators = [
        "name resolution",
        "getaddrinfo",
        "nodename nor servname",
        "name or service not known",
        "temporary failure",
        "dns",
    ]
    return any(indicator in error_str for indicator in dns_error_indicators)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrator Agent")
    parser.add_argument(
        "-l",
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (use -l or --log-level)",
    )
    args = parser.parse_args()

    set_log_level(args.log_level)

    reconnect_attempt = 0

    while True:
        try:
            # Parse host and port for DNS health check
            host_parts = SERVER_HOST.split(":")
            host = host_parts[0]
            port = int(host_parts[1]) if len(host_parts) > 1 else 443

            # DNS health check before attempting connection
            # This prevents rapid retry loops when DNS is unavailable
            if reconnect_attempt > 0:
                log_info(f"Performing DNS health check for {host}...")
                if not wait_for_dns(host, port):
                    log_warning(
                        f"DNS resolution failed after {DNS_HEALTH_CHECK_RETRIES} attempts. "
                        f"Network may still be transitioning."
                    )
                    # Apply backoff even for DNS failures
                    delay = calculate_backoff(reconnect_attempt)
                    log_warning(f"Waiting {delay:.1f}s before next attempt...")
                    sleep(delay)
                    reconnect_attempt += 1
                    continue

            log_info(f"Attempting to connect to server at {SERVER_HOST}...")
            asyncio.run(main_websocket_task(SERVER_HOST))

            # If we get here, connection was successful and then closed normally
            # Reset attempt counter for fresh reconnection
            reconnect_attempt = 0

        except KeyboardInterrupt:
            log_warning("Keyboard interrupt received. Closing connection and exiting.")
            break
        except Exception as e:
            log_error(f"Error on websocket interface: {e}")

            # Calculate delay based on error type
            if is_dns_error(e):
                # DNS errors get longer delays to allow network to stabilize
                delay = calculate_backoff(reconnect_attempt + 2)  # Extra penalty for DNS errors
                log_warning(
                    f"DNS-related error detected. Waiting {delay:.1f}s to allow network to stabilize..."
                )
            else:
                delay = calculate_backoff(reconnect_attempt)
                log_warning(f"Reconnecting in {delay:.1f}s (attempt {reconnect_attempt + 1})...")

            sleep(delay)
            reconnect_attempt += 1
