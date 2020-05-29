"""Homer package."""
import logging
import os
import pathlib
import sys

from collections import defaultdict
from importlib import import_module
from typing import Callable, DefaultDict, Dict, List, Mapping, Optional, Tuple

import pynetbox

from pkg_resources import DistributionNotFound, get_distribution

from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Device, Devices
from homer.exceptions import HomerAbortError, HomerError, HomerTimeoutError
from homer.netbox import NetboxData, NetboxDeviceData, NetboxInventory
from homer.templates import Renderer
from homer.transports.junos import connected_device


TIMEOUT_ATTEMPTS = 3
""":py:class:`int`: the number of attempts to try when there is a timeout."""
DIFF_EXIT_CODE = 99
""":py:class:`int`: the exit code used when the diff command is executed and there is a diff."""


try:
    __version__ = get_distribution('homer').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Homer package."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Homer:
    """The instance to run Homer."""

    OUT_EXTENSION = '.out'
    """:py:class:`str`: the extension for the generated output files."""

    def __init__(self, main_config: Mapping):
        """Initialize the instance.

        Arguments:
            main_config (dict): the configuration dictionary.

        """
        logger.debug('Initialized with configuration: %s', main_config)
        self._main_config = main_config
        private_base_path = self._main_config['base_paths'].get('private', '')
        self._config = HierarchicalConfig(
            self._main_config['base_paths']['public'], private_base_path=private_base_path)

        self._netbox_api = None
        self._device_plugin = None
        if self._main_config.get('netbox', {}):
            self._netbox_api = pynetbox.api(
                self._main_config['netbox']['url'], token=self._main_config['netbox']['token'])
            if self._main_config['netbox'].get('plugin', ''):
                self._device_plugin = import_module(  # type: ignore
                    self._main_config['netbox']['plugin']).NetboxDeviceDataPlugin

        devices_all_config = load_yaml_config(
            os.path.join(self._main_config['base_paths']['public'], 'config', 'devices.yaml'))
        devices_config = {fqdn: data.get('config', {}) for fqdn, data in devices_all_config.items()}

        netbox_inventory = self._main_config.get('netbox', {}).get('inventory', {})
        if netbox_inventory:
            devices = NetboxInventory(
                self._netbox_api, netbox_inventory['device_roles'], netbox_inventory['device_statuses']).get_devices()
        else:
            devices = devices_all_config.copy()
            for data in devices.values():
                data.pop('config', None)

        private_devices_config = {}  # type: dict
        if private_base_path:
            private_devices_config = load_yaml_config(
                os.path.join(private_base_path, 'config', 'devices.yaml'))

        self._ignore_warning = self._main_config.get('transports', {}).get('junos', {}).get('ignore_warning', False)
        self._transport_username = self._main_config.get('transports', {}).get('username', '')
        self._transport_ssh_config = self._main_config.get('transports', {}).get('ssh_config', None)
        self._devices = Devices(devices, devices_config, private_devices_config)
        self._renderer = Renderer(self._main_config['base_paths']['public'])
        self._output_base_path = pathlib.Path(self._main_config['base_paths']['output'])

    def generate(self, query: str) -> int:
        """Generate the configuration only saving it locally, no remote action is performed.

        Arguments:
            query (str): the query to select the devices.

        Return:
            int: ``0`` on success, a small positive integer on failure.

        """
        logger.info('Generating configuration for query %s', query)
        self._prepare_out_dir()
        successes, _ = self._execute(self._device_generate, query)
        return Homer._parse_results(successes)

    def diff(self, query: str, *, omit_diff: bool = False) -> int:
        """Generate the configuration and check the diff with the current live one.

        Arguments:
            query (str): the query to select the devices.
            omit_diff (bool, optional): whether to not show the actual diff to avoid leak of private data.

        Return:
            int: ``0`` on success, a small positive integer on failure.

        """
        logger.info('Generating diff for query %s', query)
        successes, diffs = self._execute(self._device_diff, query)
        has_diff = False
        for diff, diff_devices in diffs.items():
            print('Changes for {n} devices: {devices}'.format(n=len(diff_devices), devices=diff_devices))
            if diff is None:
                print('# Failed')
            elif not diff:
                print('# No diff')
            else:
                has_diff = True
                if omit_diff:
                    print('# Non-empty diff omitted, -o/--omit-diff set')
                else:
                    print(diff)
            print('---------------')

        ret = Homer._parse_results(successes)
        if ret == 0 and has_diff:
            return DIFF_EXIT_CODE

        return ret

    def commit(self, query: str, *, message: str = '-') -> int:
        """Commit the generated configuration asking for confirmation.

        Arguments:
            query (str): the query to select the devices.
            message (str): the commit message to use.

        Return:
            int: ``0`` on success, a small positive integer on failure.

        """
        logger.info('Committing config for query %s with message: %s', query, message)
        successes, _ = self._execute(self._device_commit, query, message=message)
        return Homer._parse_results(successes)

    def _device_generate(self, device: Device, device_config: str, _: int) -> Tuple[bool, Optional[str]]:
        """Save the generated configuration in a local file.

        Arguments:
            device (homer.devices.Device): the device instance.
            device_config (str): the generated configuration for the device.
            attempt (int, unused): the current attempt number.

        Returns:
            tuple: a two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string or None that is not used but is required by the callback API.

        """
        output_path = self._output_base_path / '{fqdn}{out}'.format(fqdn=device.fqdn, out=Homer.OUT_EXTENSION)
        with open(str(output_path), 'w') as f:
            f.write(device_config)
            logger.info('Written configuration for %s in %s', device.fqdn, output_path)

        return True, None

    def _device_diff(self, device: Device, device_config: str,
                     _: int) -> Tuple[bool, Optional[str]]:  # pylint: disable=no-self-use
        """Perform a configuration diff between the generated configuration and the live one.

        Arguments:
            device (homer.devices.Device): the device instance.
            device_config (str): the generated configuration for the device.
            attempt (int, unused): the current attempt number.

        Returns:
            tuple: a two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string that contains the configuration differences or None if unable
            to load the new configuration in the device to generate the diff.

        """
        with connected_device(device.fqdn, username=self._transport_username,
                              ssh_config=self._transport_ssh_config) as connection:
            return connection.commit_check(device_config, self._ignore_warning)

    def _device_commit(self, device: Device, device_config: str,  # noqa: MC0001; pylint: disable=no-self-use
                       attempt: int, *, message: str = '-') -> Tuple[bool, Optional[str]]:
        """Commit a new configuration to the device.

        Arguments:
            device (homer.devices.Device): the device instance.
            device_config (str): the generated configuration for the device.
            attempt (int): the current attempt number.
            message (str): the commit message to use.

        Raises:
            HomerTimeoutError: on timeout.

        Returns:
            tuple: a two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string or None that is not used but is required by the callback API.

        """
        def callback(fqdn: str, diff: str) -> None:
            """Callback as required by :py:class:`homer.transports.junos.ConnectedDevice.commit`."""
            if not sys.stdout.isatty():
                raise HomerError('Not in a TTY, unable to ask for confirmation')

            print('Configuration diff for {fqdn}:\n{diff}'.format(fqdn=fqdn, diff=diff))
            print('Type "yes" to commit, "no" to abort.')

            for _ in range(2):
                resp = input('> ')
                if resp == 'yes':
                    break
                if resp == 'no':
                    raise HomerAbortError('Commit aborted')

                print(('Invalid response, please type "yes" to commit or "no" to abort. After 2 wrong answers the '
                       'commit will be aborted.'))
            else:
                raise HomerAbortError('Too many invalid answers, commit aborted')

        is_retry = (attempt != 1)
        with connected_device(device.fqdn, username=self._transport_username,
                              ssh_config=self._transport_ssh_config) as connection:
            try:
                connection.commit(device_config, message, callback, ignore_warning=self._ignore_warning,
                                  is_retry=is_retry)
                return True, ''
            except HomerTimeoutError:
                raise  # To be catched later for automatic retry
            except HomerAbortError as e:
                logger.warning('%s on %s', e, device.fqdn)
            except Exception as e:  # pylint: disable=broad-except
                logger.error('Failed to commit on %s: %s', device.fqdn, e)
                logger.debug('Traceback:', exc_info=True)

            return False, ''

    def _prepare_out_dir(self) -> None:
        """Prepare the out directory creating the directory if doesn't exists and deleting any pre-generated file."""
        self._output_base_path.mkdir(parents=True, exist_ok=True)
        for path in self._output_base_path.iterdir():
            if path.is_file() and path.suffix == Homer.OUT_EXTENSION:
                path.unlink()

    def _execute(self, callback: Callable, query: str, **kwargs: str) -> Tuple[Dict, DefaultDict]:
        """Execute Homer based on the given action and query.

        Arguments:
            callback (Callable): the callback to call for each device.
            query (str): the query to filter the devices to act on.
            **kwargs (str): any additional keyword argument to pass to the callback

        Returns:
            tuple: a two-element tuple, with the first item as a dictionary that contains two keys (:py:data:`True`
            and :py:data:`False`) and as value a list of device FQDN that were successful (True) or failed (False)
            the operation and a second element a :py:class:`collections.defaultdict` that has as keys the
            configuration differences and as values the list of device FQDN that reported that diff.

        """
        diffs = defaultdict(list)  # type: defaultdict
        successes = {True: [], False: []}  # type: dict
        netbox_data = None
        if self._netbox_api is not None:
            logger.info('Gathering global Netbox data')
            netbox_data = NetboxData(self._netbox_api)

        for device in self._devices.query(query):
            logger.info('Generating configuration for %s', device.fqdn)

            try:
                device_data = self._config.get(device)
                if netbox_data is not None:
                    device_data['netbox'] = {
                        'global': netbox_data,
                        'device': NetboxDeviceData(self._netbox_api, device),
                    }
                    if self._device_plugin is not None:
                        device_data['netbox']['device_plugin'] = self._device_plugin(self._netbox_api, device)

                device_config = self._renderer.render(device.metadata['role'], device_data)
            except HomerError:
                logger.exception('Device %s failed to render the template, skipping.', device.fqdn)
                successes[False].append(device.fqdn)
                continue

            for attempt in range(1, TIMEOUT_ATTEMPTS + 1):
                try:
                    device_success, device_diff = callback(device, device_config, attempt, **kwargs)
                    break
                except HomerTimeoutError as e:
                    logger.error('Commit attempt %d/%d failed: %s', attempt, TIMEOUT_ATTEMPTS, e)
            else:
                device_success = False
                device_diff = ''

            successes[device_success].append(device.fqdn)
            diffs[device_diff].append(device.fqdn)

        return successes, diffs

    @staticmethod
    def _parse_results(successes: Mapping[bool, List[Device]]) -> int:
        """Parse the results dictionary, log and return the approriate exit status code.

        Arguments:
            successes (dict): a dictionary that contains two keys (:py:data:`True` and :py:data:`False`) and as value
                a list of device FQDN that were successful (True) or failed (False) the operation.

        Return:
            int: ``0`` on success, a small positive integer on failure.

        """
        if successes[False]:
            logger.error('Homer run had issues on %d devices: %s', len(successes[False]), successes[False])
            return 1

        logger.info('Homer run completed successfully on %d devices: %s', len(successes[True]), successes[True])
        return 0
