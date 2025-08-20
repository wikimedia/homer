"""JSON-RPC module."""
import logging

from contextlib import contextmanager
from typing import Iterator, Optional, Union

import requests

from homer.diff import DiffStore
from homer.exceptions import HomerConnectError, HomerError, HomerTimeoutError
from homer.interactive import ApprovalStatus, ask_approval
from homer.templates import DeviceConfigurationBase
from homer.transports import color_diff, DEFAULT_JSONRPC_PORT, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)


@contextmanager
# pylint: disable-next=too-many-arguments
def connected_device(fqdn: str, *, username: str = '', password: str = '', ssh_config: Optional[str] = None,
                     port: int = DEFAULT_JSONRPC_PORT, output_format: str = 'text',
                     timeout: int = DEFAULT_TIMEOUT) -> Iterator['ConnectedDevice']:
    """Context manager to perform actions on a connected device via JSON-RPC.

    Arguments:
        fqdn (str): the FQDN of the JSON-RPC device.
        username (str): the username to use to connect to the device.
        password (str): the password for the JSON-RPC API.
        ssh_config (Optional[str]): unused in the JSON-RPC transport.
        port (int, optional): the port to use to connect to the device.
        timeout (int, optional): the timeout in seconds to use when operating on the device.
        output_format (str, optional): the diff format to be used by the device (yaml/text/json) (default: text)

    Yields:
        ConnectedDevice: the Requests Session definition instance.

    """
    del ssh_config  # For pylint
    device = ConnectedDevice(fqdn, username=username, password=password, port=port, timeout=timeout,
                             output_format=output_format)
    try:
        yield device
    finally:
        device.close()


class ConnectedDevice:
    """JSON-RPC transport to manage a JSON-RPC-capable connected device."""

    def __init__(self, fqdn: str, *, username: str = '', password: str = '',  # pylint: disable=too-many-arguments
                 port: int, timeout: int = DEFAULT_TIMEOUT, output_format: str = 'text'):
        """Initialize the instance and open the connection to the device.

        Arguments:
            fqdn (str): the FQDN of the Juniper device.
            username (str): the username to use to connect to the Juniper device.
            password (str): the password for the JSON-RPC API.
            port (int): the port where JSON-RPC is listening.
            timeout (int, optional): the timeout in seconds to use when operating on the device.
            output_format (str, optional): the diff format to be used by the device (yaml/text/json) (default: text)

        """
        self._fqdn = fqdn
        self._port = port
        self._timeout = timeout
        logger.debug('Connecting to device %s:%s (user=%s timeout=%d)',
                     self._fqdn, self._port, username, self._timeout)
        # TODO handle proxy when running Homer on laptop towards WMF device
        self._device = requests.Session()
        self._device.auth = (username, password)  # noqa - unused-attribute
        self._device.headers.update({"User-Agent": "Homer"})
        self._output_format = output_format

    def commit(self, config: DeviceConfigurationBase, message: str, *,  # noqa: MC0001
               ignore_warning: Union[bool, str, list[str]] = False, is_retry: bool = False) -> None:
        """Commit the loaded configuration.

        Arguments:
            config (homer.templates.DeviceConfigurationBase): the device new configuration.
            message (str): the commit message to use. (Not used with JSON-RPC)
            ignore_warning (mixed, optional): the warnings to tell JunOS to ignore (Not used with JSON-RPC).
            is_retry (bool, optional): whether this is a retry and the commit_check should be run anyway, also if the
                diff is empty.

        Raises:
            HomerTimeoutError: on timeout.
            HomerError: on commit error.
            Exception: on generic failure.

        """
        del ignore_warning  # For pylint
        del message  # For pylint
        diff = self._prepare(config)
        if not diff:
            if not is_retry:
                logger.info('Empty diff for %s, skipping device.', self._fqdn)
                return
        else:
            print(f'Change for {self._fqdn}:\n{diff}')
            diff_store = DiffStore()
            diff_status = diff_store.status(diff)
            if diff_status is True:
                logger.info('Committing already approved change on %s', self._fqdn)
            elif diff_status is False:
                logger.info('Skipping already rejected change on %s', self._fqdn)
                return
            else:
                answer = ask_approval()
                if answer is ApprovalStatus.REJECT_SINGLE:
                    logger.info('Change rejected')
                    return
                if answer is ApprovalStatus.REJECT_ALL:
                    diff_store.reject(diff)
                    logger.info('Change rejected for all devices')
                    return
                if answer is ApprovalStatus.APPROVE_ALL:
                    diff_store.approve(diff)
                    logger.info('Change approved for all devices')
                elif answer is not ApprovalStatus.APPROVE_SINGLE:
                    raise HomerError(f'Unknown approval status {answer}')

                logger.info('Committing the change on %s', self._fqdn)

        try:
            if diff:
                commit_payload = {"jsonrpc": "2.0",
                                  "id": 0,
                                  "method": "set",
                                  "params": {
                                      "confirm-timeout": 10,  # in seconds
                                      "commands": config
                                  }}
                self.send_jsonrpc_request(payload=commit_payload)
                confirm_payload = {"jsonrpc": "2.0",
                                   "id": 0,
                                   "method": "set",
                                   "params": {
                                       "datastore": "tools",
                                       "commands": [
                                           {
                                               "action": "update",
                                               "path": "/system/configuration/confirmed-accept"
                                           }
                                       ]
                                   }
                                   }

                self.send_jsonrpc_request(payload=confirm_payload)
                logger.debug('Commit confirmed on %s', self._fqdn)
        except requests.Timeout as e:
            raise HomerTimeoutError(str(e)) from e
        except requests.RequestException as e:
            raise HomerConnectError(f'Commit error: {e}') from e

    def _prepare(self, config: DeviceConfigurationBase) -> str:
        """Prepare the new configuration to be committed.

        Arguments:
            config (homer.templates.DeviceConfigurationBase): the device new configuration.

        Raises:
            Exception: on generic failure.

        Returns:
            str: the differences between the current config and the new one.

        """
        logger.debug('Preparing the configuration on %s', self._fqdn)
        diff_request_payload = {"jsonrpc": "2.0",
                                "id": 0,
                                "method": "diff",
                                "params": {
                                    "commands": config,
                                    "output-format": self._output_format
                                }}
        response = self.send_jsonrpc_request(payload=diff_request_payload)
        if 'result' in response.json() and len(response.json()['result']) > 0:
            return color_diff(response.json()['result'][0])
        return ''

    def commit_check(self, config: DeviceConfigurationBase,
                     ignore_warning: Union[bool, str, list[str]] = False) -> tuple[bool, Optional[str]]:
        """Perform a commit validate and return the diff.

        Arguments:
            config (homer.templates.DeviceConfigurationBase): the changes to make on the device
            ignore_warning (mixed, optional): the warnings to tell JunOS to ignore (Not used with JSON-RPC).

        Returns:
            tuple: a two-element tuple with a boolean as first item that is :py:data:`True` on success and
            :py:data:`False` on failure and a string as second item with the difference between the current
            configuration and the new one, empty string on no diff and :py:data:`None` on failure.

        """
        del ignore_warning  # For pylint
        success = False
        try:
            diff = self._prepare(config)
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to get diff for %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)
            return False, None

        if not diff:
            logger.info('Empty diff for %s, skipping device.', self._fqdn)
            return True, diff

        logger.info('Running commit validate on %s', self._fqdn)
        validate_request_payload = {"jsonrpc": "2.0",
                                    "id": 0,
                                    "method": "validate",
                                    "params": {
                                        "commands": config
                                    }}
        response = self.send_jsonrpc_request(payload=validate_request_payload, raise_on_error=False)
        if 'error' not in response.json():
            success = True
        else:
            logger.error('Commit validate error on %s: %s', self._fqdn, response.json()['error']['message'])

        return success, diff

    def send_jsonrpc_request(self, payload: dict, raise_on_error: bool = True) -> requests.models.Response:
        """Send a JSON-RPC request, verify that it went well and return the response."""
        response = self._device.post(f"https://{self._fqdn}:{self._port}/jsonrpc", json=payload)
        if not response.ok:
            raise HomerError(response.text)
        if 'error' in response.json() and raise_on_error:
            raise HomerError(response.json()['error']['message'])
        return response

    def close(self) -> None:
        """Close the connection with the device."""
        self._device.close()
