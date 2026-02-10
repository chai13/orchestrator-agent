import threading
from typing import Optional

from repos.interfaces import SerialRepoInterface
from tools.json_file import read_json_file, write_json_file
from tools.logger import log_debug, log_error, log_warning
from tools.utils import matches_device_id

SERIAL_CONFIG_FILE = "/var/orchestrator/data/serial_configs.json"


class SerialRepo(SerialRepoInterface):
    """File-backed persistence for serial port configurations."""

    def __init__(self):
        self._file_lock = threading.Lock()
        self._config_file = SERIAL_CONFIG_FILE

    def save_configs(self, container_name: str, serial_configs: list) -> None:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)

                initialized_configs = []
                for config in serial_configs:
                    initialized_configs.append({
                        "name": config.get("name"),
                        "device_id": config.get("device_id"),
                        "container_path": config.get("container_path"),
                        "status": "disconnected",
                        "current_host_path": None,
                        "major": None,
                        "minor": None,
                    })

                all_configs[container_name] = {"serial_ports": initialized_configs}
                write_json_file(self._config_file, all_configs)
                log_debug(
                    f"Saved {len(serial_configs)} serial configuration(s) for container {container_name}"
                )
            except Exception as e:
                log_error(
                    f"Failed to save serial configurations for {container_name}: {e}"
                )

    def load_configs(self, container_name: Optional[str] = None) -> dict:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)

                if container_name:
                    return all_configs.get(container_name, {"serial_ports": []})
                else:
                    return all_configs
            except Exception as e:
                log_error(f"Failed to load serial configurations: {e}")
                return {"serial_ports": []} if container_name else {}

    def delete_configs(self, container_name: str) -> None:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)

                if container_name in all_configs:
                    del all_configs[container_name]
                    write_json_file(self._config_file, all_configs)
                    log_debug(
                        f"Deleted serial configurations for container {container_name}"
                    )
                else:
                    log_debug(
                        f"No serial configurations found for container {container_name}"
                    )
            except Exception as e:
                log_error(
                    f"Failed to delete serial configurations for {container_name}: {e}"
                )

    def update_status(
        self, container_name: str, port_name: str, status: str, **kwargs
    ) -> None:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)

                if container_name not in all_configs:
                    log_warning(
                        f"Cannot update serial status: container {container_name} not found"
                    )
                    return

                container_config = all_configs[container_name]
                serial_ports = container_config.get("serial_ports", [])

                port_found = False
                for port_config in serial_ports:
                    if port_config.get("name") == port_name:
                        port_config["status"] = status

                        if "current_host_path" in kwargs:
                            port_config["current_host_path"] = kwargs[
                                "current_host_path"
                            ]
                        if "major" in kwargs:
                            port_config["major"] = kwargs["major"]
                        if "minor" in kwargs:
                            port_config["minor"] = kwargs["minor"]

                        if status == "disconnected":
                            port_config["current_host_path"] = None
                            port_config["major"] = None
                            port_config["minor"] = None

                        port_found = True
                        break

                if not port_found:
                    log_warning(
                        f"Serial port '{port_name}' not found in container {container_name}"
                    )
                    return

                write_json_file(self._config_file, all_configs)
                log_debug(
                    f"Updated serial port '{port_name}' status to '{status}' for container {container_name}"
                )
            except Exception as e:
                log_error(
                    f"Failed to update serial status for {container_name}/{port_name}: {e}"
                )

    def get_by_device_id(self, device_id: str) -> list:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)
                matches = []

                for container_name, container_config in all_configs.items():
                    for port_config in container_config.get("serial_ports", []):
                        config_device_id = port_config.get("device_id", "")
                        if matches_device_id(config_device_id, device_id):
                            matches.append(
                                {
                                    "container_name": container_name,
                                    "serial_config": port_config.copy(),
                                }
                            )

                return matches
            except Exception as e:
                log_error(
                    f"Failed to find serial port by device_id '{device_id}': {e}"
                )
                return []

    def get_all_configured_ports(self) -> list:
        with self._file_lock:
            try:
                all_configs = read_json_file(self._config_file)
                all_ports = []

                for container_name, container_config in all_configs.items():
                    for port_config in container_config.get("serial_ports", []):
                        all_ports.append(
                            {
                                "container_name": container_name,
                                "serial_config": port_config.copy(),
                            }
                        )

                return all_ports
            except Exception as e:
                log_error(f"Failed to get all configured serial ports: {e}")
                return []
