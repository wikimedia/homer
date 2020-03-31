"""Config module."""
import ipaddress
import itertools
import logging
import os
import re

from copy import deepcopy
from typing import Dict, Union

import yaml

from homer.devices import Device
from homer.exceptions import HomerError

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def ip_network_constructor(loader: yaml.constructor.BaseConstructor, node: str) -> Union[str,
                                                                                         ipaddress.IPv4Network,
                                                                                         ipaddress.IPv6Network,
                                                                                         ipaddress.IPv4Interface,
                                                                                         ipaddress.IPv6Interface]:
    """Casts a string into a ipaddress.ip_network or ip_interface object.

    Arguments:
        loader (yaml loader): YAML loaded on which to apply the constructor
        node: (str): string to be casted

    Returns:
        ipaddress: an IPv4 or v6 Network or Interface object
        str: if not possible, return the original string

    """
    value = loader.construct_scalar(node)
    try:
        return ipaddress.ip_network(value)
    except ValueError:
        try:
            return ipaddress.ip_interface(value)
        except ValueError as e:
            logger.debug('Casting to ip_network or ip_interface failed, defaulting to string (%s).', e)
            return value


def ip_address_constructor(loader: yaml.constructor.BaseConstructor, node: str) -> Union[str,
                                                                                         ipaddress.IPv4Address,
                                                                                         ipaddress.IPv6Address]:
    """Casts a string into a ipaddress.ip_address object.

    Arguments:
        loader (yaml loader): YAML loaded on which to apply the constructor
        node: (str): string to be casted

    Returns:
        ipaddress: an IPv4 or v6 address object
        str: if not possible, return the original string

    """
    value = loader.construct_scalar(node)
    try:
        return ipaddress.ip_address(value)
    except ValueError as e:
        logger.debug('Casting to ip_address failed, defaulting to string (%s).', e)
        return value


def load_yaml_config(config_file: str) -> Dict:
    """Parse a YAML config file and return it.

    Arguments:
        config_file (str): the path of the configuration file.

    Returns:
        dict: the parsed config or an empty dictionary if the file doesn't exists.

    Raises:
        HomerError: if failed to load the configuration.

    """
    network_re = re.compile(r"^(\d+\.\d+\.\d+\.\d+|(?:[\da-f]{0,4}:){2,7}[\da-f]{0,4})/\d+$")
    ip_re = re.compile(r"^(\d+\.\d+\.\d+\.\d+|(?:[\da-f]{0,4}:){2,7}[\da-f]{0,4})$")
    yaml.SafeLoader.add_constructor("!ip_network", ip_network_constructor)
    yaml.SafeLoader.add_implicit_resolver('!ip_network', network_re, None)
    yaml.SafeLoader.add_constructor("!ip_address", ip_address_constructor)
    yaml.SafeLoader.add_implicit_resolver('!ip_address', ip_re, None)

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
        role = device.metadata.get('role', '')
        site = device.metadata.get('site', '')
        # Deepcopying the common configurations to protect from any side effect
        public = {
            **deepcopy(self._configs['public_common']),
            **deepcopy(self._configs['public_roles'].get(role, {})),
            **deepcopy(self._configs['public_sites'].get(site, {})),
            **device.config,
            **{'metadata': device.metadata, 'hostname': device.fqdn},  # Inject also FQDN and device metadata
        }
        private = {
            **self._configs['private_common'],
            **self._configs['private_roles'].get(role, {}),
            **self._configs['private_sites'].get(site, {}),
            **device.private,
        }
        if public.keys() & private.keys():
            raise HomerError('Configuration key(s) found in both public and private config: {keys}'.format(
                keys=public.keys() & private.keys()))

        return {**public, **deepcopy(private)}
