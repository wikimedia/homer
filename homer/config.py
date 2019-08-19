"""Config module."""
import os

from copy import deepcopy
from typing import Dict

import yaml

from homer.devices import Device
from homer.exceptions import HomerError


def load_yaml_config(config_file: str) -> Dict:
    """Parse a YAML config file and return it.

    Arguments:
        config_file (str): the path of the configuration file.

    Returns:
        dict: the parsed config or an empty dictionary if the file doesn't exists.

    Raises:
        HomerError: if failed to load the configuration.

    """
    config = {}  # type: Dict
    if not os.path.exists(config_file):
        return config

    try:
        with open(config_file, 'r') as fh:
            config = yaml.safe_load(fh)

    except Exception as e:  # pylint: disable=broad-except
        raise HomerError('Could not load config file {file}: {e}'.format(file=config_file, e=e)) from e

    if config is None:
        config = {}

    return config


class HierarchicalConfig:
    """Load configuration with hierarchical override based on role, site and device."""

    def __init__(self, base_path: str):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path from where the configuration files should be loaded. The configuration
                files that will be loaded, if existing, are:
                - ``common.yaml``: common key:value pairs
                - ``roles.yaml``: one key for each role with key:valye pairs of role-specific configuration
                - ``sites.yaml``: one key for each site with key:valye pairs of role-specific configuration

        """
        # Not using setattr dynamically to allow mypy to work.
        self._common = load_yaml_config(os.path.join(base_path, 'common.yaml'))
        self._roles = load_yaml_config(os.path.join(base_path, 'roles.yaml'))
        self._sites = load_yaml_config(os.path.join(base_path, 'sites.yaml'))

    def get(self, device: Device) -> Dict:
        """Get the generated configuration for a specific device instance with all the overrides resolved.

        Arguments:
            device (homer.devices.Device): the device instance.

        Returns:
            dict: the generated device-specific configuration dictionary. The override order is:
            ``common``, ``role``, ``site``, ``device``.

        """
        common = deepcopy(self._common)
        role = deepcopy(self._roles.get(device.role, {}))
        site = deepcopy(self._sites.get(device.site, {}))
        return {**common, **role, **site, **device.config}
