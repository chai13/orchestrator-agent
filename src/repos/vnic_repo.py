from typing import Optional, Union

from repos.interfaces import VNICRepoInterface
from tools.json_file import read_json_file, write_json_file
from tools.logger import log_debug, log_error, log_warning

VNIC_CONFIG_FILE = "/var/orchestrator/runtime_vnics.json"


class VNICRepo(VNICRepoInterface):
    """File-backed persistence for vNIC configurations."""

    def __init__(self):
        self._config_file = VNIC_CONFIG_FILE

    def save_configs(self, container_name: str, vnic_configs: list) -> None:
        try:
            existing_configs = read_json_file(self._config_file)
            existing_configs[container_name] = vnic_configs
            write_json_file(self._config_file, existing_configs)
            log_debug(
                f"Saved vNIC configurations for container {container_name}"
            )
        except Exception as e:
            log_error(
                f"Failed to save vNIC configurations for {container_name}: {e}"
            )

    def load_configs(self, container_name: Optional[str] = None) -> Union[dict, list]:
        try:
            all_configs = read_json_file(self._config_file)

            if container_name:
                return all_configs.get(container_name, [])
            else:
                return all_configs
        except Exception as e:
            log_error(f"Failed to load vNIC configurations: {e}")
            return [] if container_name else {}

    def delete_configs(self, container_name: str) -> None:
        try:
            all_configs = read_json_file(self._config_file)

            if container_name in all_configs:
                del all_configs[container_name]
                write_json_file(self._config_file, all_configs)
                log_debug(
                    f"Deleted vNIC configurations for container {container_name}"
                )
        except Exception as e:
            log_error(
                f"Failed to delete vNIC configurations for {container_name}: {e}"
            )
