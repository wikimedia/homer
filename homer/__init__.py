"""Homer package."""
import logging
import os

from typing import Dict

from pkg_resources import DistributionNotFound, get_distribution

from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Devices
from homer.exceptions import HomerError
from homer.templates import Renderer


try:
    __version__ = get_distribution('homer').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Homer package."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def execute(main_config: Dict, action: str, query: str) -> int:
    """Execute Homer based on the given configuration, action and query.

    Arguments:
        main_config (dict): the configuration dictionary.
        action (str): the action to perform.
        query (str): the query to filter the devices to act on.

    Returns:
        int: ``0`` on success, ``1`` on failure.

    """
    logger.debug('Initialized with configuration: %s', main_config)
    logger.info('Executing %s on %s', action, query)

    private_base_path = main_config['base_paths'].get('private', '')
    config = HierarchicalConfig(main_config['base_paths']['public'], private_base_path)
    devices_config = load_yaml_config(os.path.join(main_config['base_paths']['public'], 'config', 'devices.yaml'))
    private_devices_config = {}  # type: dict
    if private_base_path:
        private_devices_config = load_yaml_config(os.path.join(private_base_path, 'config', 'devices.yaml'))

    devices = Devices(devices_config, private_devices_config)
    renderer = Renderer(main_config['base_paths']['public'])
    failed = False
    for fqdn, device in devices.items():
        logger.info('Generating configuration for %s', fqdn)
        try:
            template = renderer.render(device.role, config.get(device))
        except HomerError:
            logger.exception('Device %s failed to render the template, skipping.', fqdn)
            failed = True

        print(template)

    if failed:
        logger.error('Homer run had issues')
        return 1

    logger.info('Homer run completed successfully')
    return 0
