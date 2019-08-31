"""Homer package."""
import logging
import os
import pathlib

from collections import defaultdict
from typing import Dict

from pkg_resources import DistributionNotFound, get_distribution

from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Devices
from homer.exceptions import HomerError
from homer.templates import Renderer
from homer.transports.junos import connected_device


try:
    __version__ = get_distribution('homer').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Homer package."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed

ACTIONS = ('generate', 'diff', 'commit')
OUT_EXTENSION = '.out'
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def execute(main_config: Dict, action: str, query: str) -> int:  # # noqa: MC0001 pylint: disable=too-many-locals
    """Execute Homer based on the given configuration, action and query.

    Arguments:
        main_config (dict): the configuration dictionary.
        action (str): the action to perform, one of :py:data:`homer.ACTIONS`.
        query (str): the query to filter the devices to act on.

    Returns:
        int: ``0`` on success, ``1`` on failure.

    """
    # TODO: convert to a class with methods
    if action not in ACTIONS:
        raise HomerError('Invalid action {action}, expected one of: {actions}'.format(action=action, actions=ACTIONS))

    logger.debug('Initialized with configuration: %s', main_config)
    logger.info('Executing %s on %s', action, query)

    private_base_path = main_config['base_paths'].get('private', '')
    config = HierarchicalConfig(main_config['base_paths']['public'], private_base_path=private_base_path)
    devices_config = load_yaml_config(os.path.join(main_config['base_paths']['public'], 'config', 'devices.yaml'))
    private_devices_config = {}  # type: dict
    if private_base_path:
        private_devices_config = load_yaml_config(os.path.join(private_base_path, 'config', 'devices.yaml'))

    devices = Devices(devices_config, private_devices_config).query(query)
    renderer = Renderer(main_config['base_paths']['public'])
    output_base_path = pathlib.Path(main_config['base_paths']['output'])
    if action == 'generate':
        _prepare_out_dir(output_base_path)

    diffs = defaultdict(list)  # type: defaultdict
    successes = {True: [], False: []}  # type: dict
    for device in devices:
        logger.info('Generating configuration for %s', device.fqdn)
        try:
            device_config = renderer.render(device.role, config.get(device))
        except HomerError:
            logger.exception('Device %s failed to render the template, skipping.', device.fqdn)
            successes[False].append(device.fqdn)
            continue

        if action == 'generate':
            output_path = output_base_path / '{fqdn}{out}'.format(fqdn=device.fqdn, out=OUT_EXTENSION)
            with open(str(output_path), 'w') as f:
                f.write(device_config)
                logger.info('Written configuration for %s in %s', device.fqdn, output_path)
        elif action == 'diff':
            with connected_device(device.fqdn) as connection:
                device_success, device_diff = connection.commit_check(device_config)
                diffs[device_diff].append(device.fqdn)
                successes[device_success].append(device.fqdn)

    if action == 'diff':
        for diff, diff_devices in diffs.items():
            print('Diff for {n} devices: {devices}'.format(n=len(diff_devices), devices=diff_devices))
            print(diff)
            print('---------------')

    if successes[False]:
        logger.error('Homer run had issues on %d devices: %s', len(successes[False]), successes[False])
        return 1

    logger.info('Homer run completed successfully on %d devices: %s', len(devices), [d.fqdn for d in devices])
    return 0


def _prepare_out_dir(out_dir: pathlib.Path) -> None:
    """Prepare the out directory creating the directory if doesn't exists and deleting any pre-generate file.

    Arguments:
        out_dir (pathlib.Path): the path to prepare.

    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        if path.is_file() and path.suffix == OUT_EXTENSION:
            path.unlink()
