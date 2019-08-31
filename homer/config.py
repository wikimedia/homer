"""Config module."""
import itertools
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

    def __init__(self, base_path: str, *, private_base_path: str = ''):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path from where the configuration files should be loaded. The configuration
                files that will be loaded, if existing, are:
                - ``common.yaml``: common key:value pairs
                - ``roles.yaml``: one key for each role with key:value pairs of role-specific configuration
                - ``sites.yaml``: one key for each site with key:value pairs of role-specific configuration
            private_base_path (str, optional): the base path from where the private configuration files should be
                loaded, with the same structure of the above ``base_path`` argument. If existing, private
                configuration files cannot have top level keys in common with the public configuration.

        """
        self._configs = {}  # type: Dict[str, Dict]
        paths = {'public': base_path, 'private': private_base_path}
        for path, name in itertools.product(paths.keys(), ('common', 'roles', 'sites')):
            if paths[path]:
                config = load_yaml_config(os.path.join(paths[path], 'config', '{name}.yaml'.format(name=name)))
            else:
                config = {}

            self._configs['{p}_{n}'.format(p=path, n=name)] = config

    def get(self, device: Device) -> Dict:
        """Get the generated configuration for a specific device instance with all the overrides resolved.

        Arguments:
            device (homer.devices.Device): the device instance.

        Raises:
            homer.exceptions.HomerError: if any top level key is present in both the private and public configuration.

        Returns:
            dict: the generated device-specific configuration dictionary. The override order is:
            ``common``, ``role``, ``site``, ``device``. Public and private configuration are merged together.

        """
        public = {
            **self._configs['public_common'],
            **self._configs['public_roles'].get(device.role, {}),
            **self._configs['public_sites'].get(device.site, {}),
            **device.config,
            **{'role': device.role, 'site': device.site},  # Inject also role and site
        }
        private = {
            **self._configs['private_common'],
            **self._configs['private_roles'].get(device.role, {}),
            **self._configs['private_sites'].get(device.site, {}),
            **device.private,
        }
        if public.keys() & private.keys():
            raise HomerError('Configuration key(s) found in both public and private config: {keys}'.format(
                keys=public.keys() & private.keys()))

        return {**deepcopy(public), **deepcopy(private)}
