"""Homer package."""
import logging
import os

from pkg_resources import DistributionNotFound, get_distribution

from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Devices


try:
    __version__ = get_distribution('homer').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Homer package."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def execute(main_config: dict, action: str, query: str) -> None:
    """Execute Homer based on the given configuration, action and query."""
    logger.debug('Initialized with configuration: %s', main_config)
    logger.info('Executing %s on %s', action, query)

    private_base_path = main_config['base_paths'].get('private', '')
    config = HierarchicalConfig(main_config['base_paths']['public'], private_base_path)
    devices_config = load_yaml_config(os.path.join(main_config['base_paths']['public'], 'config', 'devices.yaml'))
    private_devices_config = {}  # type: dict
    if private_base_path:
        private_devices_config = load_yaml_config(os.path.join(private_base_path, 'config', 'devices.yaml'))

    devices = Devices(devices_config, private_devices_config)

    print(config)
    print(devices)
