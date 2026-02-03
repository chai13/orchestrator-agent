## Main Execution Script
from controllers import main_websocket_task
from tools.logger import *
from tools.dns_utils import (
    wait_for_dns,
    calculate_backoff,
    is_dns_error,
    DNS_HEALTH_CHECK_RETRIES,
)
import argparse
import asyncio
from time import sleep

## AWS Server Address
SERVER_HOST = "api.autonomylogic.com:3001"


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
