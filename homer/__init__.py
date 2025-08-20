"""Homer package."""
import json
import logging
import os
import pathlib
import sys


from collections import defaultdict
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable, DefaultDict, Dict, List, Mapping, Optional, Tuple

import pynetbox

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from homer.capirca import CapircaGenerate
from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Device, Devices
from homer.exceptions import HomerAbortError, HomerConnectError, HomerError, HomerTimeoutError
from homer.netbox import NetboxData, NetboxDeviceData, NetboxInventory
from homer.templates import DeviceConfigurationBase, JinjaDeviceConfiguration, JinjaRenderer, PythonRenderer
from homer.transports import DEFAULT_JSONRPC_PORT, DEFAULT_PORT, DEFAULT_TIMEOUT, json_rpc, junos

TIMEOUT_ATTEMPTS = 3
"""The number of attempts to try when there is a timeout."""
DIFF_EXIT_CODE = 99
"""The exit code used when the diff command is executed and there is a diff."""

try:
    __version__ = version(__name__)  # Must be the same used as 'name' in setup.py
    """The version of the current Homer package."""
except PackageNotFoundError:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed

logger = logging.getLogger(__name__)


class Homer:  # pylint: disable=too-many-instance-attributes
    """The instance to run Homer."""

    OUT_EXTENSION = '.out'
    """The extension for the generated output files."""

    def __init__(self, main_config: Mapping):  # noqa: MC0001
        """Initialize the instance.

        Arguments:
            main_config: the configuration dictionary.

        """
        logger.debug('Initialized with configuration: %s', main_config)
        self._main_config = main_config
        self.private_base_path = self._main_config['base_paths'].get('private', '')
        self._config = HierarchicalConfig(
            self._main_config['base_paths']['public'], private_base_path=self.private_base_path)

        self._netbox_api = None
        self._device_plugin = None
        self._capirca = None
        if self._main_config.get('netbox', {}):
            self._netbox_api = pynetbox.api(
                self._main_config['netbox']['url'], token=self._main_config['netbox']['token'], threading=True)
            retry_session = Session()
            retry_adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1))
            retry_session.mount('http://', retry_adapter)
            retry_session.mount('https://', retry_adapter)
            retry_session.headers.update({'User-Agent': f'Homer {__version__}'})
            self._netbox_api.http_session = retry_session
            if self._main_config['netbox'].get('plugin', ''):
                self._device_plugin = import_module(
                    self._main_config['netbox']['plugin']).NetboxDeviceDataPlugin
            if not self._main_config.get('capirca', {}).get('disabled', False):
                self._capirca = CapircaGenerate(self._main_config, self._netbox_api)

        devices_all_config = load_yaml_config(
            os.path.join(self._main_config['base_paths']['public'], 'config', 'devices.yaml'))
        devices_config = {fqdn: data.get('config', {}) for fqdn, data in devices_all_config.items()}

        netbox_inventory = self._main_config.get('netbox', {}).get('inventory', {})
        devices = devices_all_config.copy()
        for data in devices.values():
            data.pop('config', None)

        if netbox_inventory:
            # Get the data from Netbox while keeping any existing metadata from the devices.yaml file.
            # The data from Netbox overrides the existing keys for each device, if both present.
            netbox_devices = NetboxInventory(
                self._netbox_api,
                netbox_inventory['device_roles'],
                netbox_inventory['device_statuses']).get_devices()
            for fqdn, data in netbox_devices.items():
                if fqdn in devices:
                    devices[fqdn].update(data)
                else:
                    devices[fqdn] = data

        private_devices_config: Dict = {}
        if self.private_base_path:
            private_devices_config = load_yaml_config(
                os.path.join(self.private_base_path, 'config', 'devices.yaml'))

        self._ignore_warning = self._main_config.get('transports', {}).get('junos', {}).get('ignore_warning', False)
        self._transport_username = self._main_config.get('transports', {}).get('username', '')
        self._transport_password = self._main_config.get('transports', {}).get('password', '')
        self._transport_timeout = self._main_config.get('transports', {}).get('timeout', DEFAULT_TIMEOUT)
        self._transport_jsonrpc_port = self._main_config.get('transports', {}).get('jsonrpc_port', DEFAULT_JSONRPC_PORT)
        self._transport_jsonrpc_output = self._main_config.get('transports', {}).get('json_rpc_output', 'text')
        self._port = self._main_config.get('transports', {}).get('port', DEFAULT_PORT)
        transport_ssh_config = self._main_config.get('transports', {}).get('ssh_config', None)
        if transport_ssh_config is not None:
            transport_ssh_config = str(pathlib.Path(transport_ssh_config).expanduser())
        self._transport_ssh_config = transport_ssh_config
        self._devices = Devices(devices, devices_config, private_devices_config)
        module_dir = Path(self._main_config['base_paths']['public']) / 'modules'
        if module_dir.is_dir():
            sys.path.append(str(module_dir))

        self._renderers = {
            'python': PythonRenderer(self._main_config['base_paths']['public'], self.private_base_path),
            'jinja': JinjaRenderer(self._main_config['base_paths']['public'], self.private_base_path),
        }
        self._transports = {'json_rpc': json_rpc, 'junos': junos}
        self._output_base_path = Path(self._main_config['base_paths']['output'])

    def generate(self, query: str) -> int:
        """Generate the configuration only saving it locally, no remote action is performed.

        Arguments:
            query: the query to select the devices.

        Return:
            ``0`` on success, a small positive integer on failure.

        """
        logger.info('Generating configuration for query %s', query)
        self._prepare_out_dir()
        successes, _ = self._execute(self._device_generate, query)
        return Homer._parse_results(successes)

    def diff(self, query: str, *, omit_diff: bool = False) -> int:
        """Generate the configuration and check the diff with the current live one.

        Arguments:
            query: the query to select the devices.
            omit_diff: whether to not show the actual diff to avoid leak of private data.

        Return:
            ``0`` on success, a small positive integer on failure.

        """
        logger.info('Generating diff for query %s', query)
        successes, diffs = self._execute(self._device_diff, query)
        has_diff = False
        for diff, diff_devices in diffs.items():
            print(f'Changes for {len(diff_devices)} devices: {diff_devices}')
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
            query: the query to select the devices.
            message: the commit message to use.

        Return:
            ``0`` on success, a small positive integer on failure.

        """
        logger.info('Committing config for query %s with message: %s', query, message)
        successes, _ = self._execute(self._device_commit, query, message=message)
        return Homer._parse_results(successes)

    def _device_generate(self, device: Device, device_config: DeviceConfigurationBase,
                         _: int) -> Tuple[bool, Optional[str]]:
        """Save the generated configuration in a local file.

        Arguments:
            device (homer.devices.Device): the device instance.
            device_config (homer.templates.DeviceConfigurationBase): the generated configuration for the device.
            attempt (int, unused): the current attempt number.

        Returns:
            A two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string or None that is not used but is required by the callback API.

        """
        output_path = self._output_base_path / f'{device.fqdn}{Homer.OUT_EXTENSION}'
        with open(str(output_path), 'w', encoding='utf-8') as f:
            # Juniper (Jinja)
            if isinstance(device_config, JinjaDeviceConfiguration):
                f.write(str(device_config))
            else:  # Use JSON for Nokia generate
                json.dump(device_config, f, indent=4)
            logger.info('Written configuration for %s in %s', device.fqdn, output_path)

        return True, None

    def _device_diff(self, device: Device, device_config: str, _: int) -> Tuple[bool, Optional[str]]:
        """Perform a configuration diff between the generated configuration and the live one.

        Arguments:
            device: the device instance.
            device_config: the generated configuration for the device.
            attempt: the current attempt number.

        Returns:
            A two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string that contains the configuration differences or None if unable
            to load the new configuration in the device to generate the diff.

        """
        transport_type = device.metadata.get('transport', 'junos')
        with self._transports[transport_type].connected_device(**device.metadata['connect_args']) as connection:
            return connection.commit_check(device_config, self._ignore_warning)

    def _device_commit(self, device: Device,  # noqa: MC0001
                       device_config: DeviceConfigurationBase, attempt: int, *,
                       message: str = '-') -> Tuple[bool, Optional[str]]:
        """Commit a new configuration to the device.

        Arguments:
            device: the device instance.
            device_config: the generated configuration for the device.
            attempt: the current attempt number.
            message: the commit message to use.

        Raises:
            HomerTimeoutError: on timeout.

        Returns:
            A two-element tuple with a boolean as first parameter that represent the success of the operation
            or not and a second element with a string or None that is not used but is required by the callback API.

        """
        is_retry = attempt != 1

        transport_type = device.metadata.get('transport', 'junos')
        with self._transports[transport_type].connected_device(**device.metadata['connect_args']) as connection:
            try:
                connection.commit(device_config, message, ignore_warning=self._ignore_warning,
                                  is_retry=is_retry)
                return True, ''
            except HomerTimeoutError:
                raise  # To be caught later for automatic retry
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

    # pylint: disable-msg=too-many-locals,too-many-nested-blocks,too-many-branches
    def _execute(self, callback: Callable, query: str, **kwargs: str) -> Tuple[Dict, DefaultDict]:  # noqa: MC0001
        """Execute Homer based on the given action and query.

        Arguments:
            callback: the callback to call for each device.
            query: the query to filter the devices to act on.
            **kwargs: any additional keyword argument to pass to the callback

        Returns:
            A two-element tuple, with the first item as a dictionary that contains two keys (:py:data:`True`
            and :py:data:`False`) and as value a list of device FQDN that were successful (True) or failed (False)
            the operation and a second element a :py:class:`collections.defaultdict` that has as keys the
            configuration differences and as values the list of device FQDN that reported that diff.

        """
        diffs: DefaultDict[str, list] = defaultdict(list)
        successes: Dict[bool, list] = {True: [], False: []}
        netbox_data = None
        if self._netbox_api is not None:
            logger.info('Gathering global Netbox data')
            netbox_data = NetboxData(self._netbox_api, self._main_config['base_paths'])

        for device in self._devices.query(query):
            logger.info('Generating configuration for %s', device.fqdn)
            try:
                device_data = self._config.get(device)

                # Set renderer and transport based on match criteria in homer config and device metadata
                # TODO add a default or show a nice error if those keys are missing from config.yaml
                for device_attribute in ('renderer', 'transport'):
                    selector = self._main_config['selectors'][device_attribute]
                    for option_name, match_criteria in selector.items():
                        for elements in match_criteria:
                            if all(device.metadata.get(key) == value for key, value in elements.items()):
                                device.metadata[device_attribute] = option_name

                # Set the args for device connection we use for diff and commit
                device.metadata['connect_args'] = {
                    'fqdn': device.fqdn,
                    'username': self._transport_username,
                    'timeout': device.metadata.get('timeout', self._transport_timeout)
                }
                transport_type = device.metadata.get('transport', 'junos')
                if transport_type == 'junos':
                    device.metadata['connect_args']['port'] = self._port
                    device.metadata['connect_args']['ssh_config'] = self._transport_ssh_config
                elif transport_type == 'json_rpc':
                    device.metadata['connect_args']['port'] = self._transport_jsonrpc_port
                    device.metadata['connect_args']['password'] = self._transport_password
                    device.metadata['connect_args']['output_format'] = self._transport_jsonrpc_output

                # Override global port and timeout if defined in the device config
                if 'port' in device.metadata:
                    device.metadata['connect_args']['port'] = device.metadata['port']
                if 'timeout' in device.metadata:
                    device.metadata['connect_args']['timeout'] = device.metadata['timeout']

                # Render the ACLs using Capirca
                if self._capirca and 'capirca' in device_data:
                    generated_acls = self._capirca.generate_acls(device_data['capirca'])
                else:
                    generated_acls = []

                if netbox_data is not None:
                    device_data['netbox'] = {
                        'global': netbox_data,
                        'device': NetboxDeviceData(self._netbox_api, self._main_config['base_paths'], device),
                    }

                    if self._device_plugin is not None:
                        device_data['netbox']['device_plugin'] = self._device_plugin(self._netbox_api,
                                                                                     self._main_config['base_paths'],
                                                                                     device)
                # Render the configuration based on yaml + netbox data
                device_config = self._renderers[device.metadata.get('renderer', 'jinja')].render(
                    device.metadata['role'], device_data, generated_acls)
            except HomerError:
                logger.exception('Device %s failed to render the template, skipping.', device.fqdn)
                successes[False].append(device.fqdn)
                continue

            for attempt in range(1, TIMEOUT_ATTEMPTS + 1):
                try:
                    device_success, device_diff = callback(device, device_config, attempt, **kwargs)
                    break
                except (HomerTimeoutError, HomerConnectError) as e:
                    logger.error('Attempt %d/%d failed: %s', attempt, TIMEOUT_ATTEMPTS, e)
            else:
                device_success = False
                device_diff = ''

            successes[device_success].append(device.fqdn)
            diffs[device_diff].append(device.fqdn)

        return successes, diffs

    @staticmethod
    def _parse_results(successes: Mapping[bool, List[Device]]) -> int:
        """Parse the results dictionary, log and return the appropriate exit status code.

        Arguments:
            successes: a dictionary that contains two keys (:py:data:`True` and :py:data:`False`) and as value
                a list of device FQDN that were successful (True) or failed (False) the operation.

        Return:
            ``0`` on success, a small positive integer on failure.

        """
        if successes[False]:
            logger.error('Homer run had issues on %d devices: %s', len(successes[False]), successes[False])
            return 1

        logger.info('Homer run completed successfully on %d devices: %s', len(successes[True]), successes[True])
        return 0
