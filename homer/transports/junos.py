"""JunOS module."""
import logging

from contextlib import contextmanager
from typing import Iterator, Optional, Tuple, Union

from jnpr.junos import Device as JunOSDevice
from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError, RpcTimeoutError, UnlockError
from jnpr.junos.utils.config import Config
from ncclient.operations.errors import TimeoutExpiredError

from homer.diff import DiffStore
from homer.exceptions import HomerConnectError, HomerError, HomerTimeoutError
from homer.interactive import ApprovalStatus, ask_approval
from homer.templates import DeviceConfigurationBase
from homer.transports import color_diff, DEFAULT_PORT, DEFAULT_TIMEOUT


logger = logging.getLogger(__name__)


@contextmanager
# pylint: disable-next=too-many-arguments
def connected_device(fqdn: str, *, username: str = '', ssh_config: Optional[str] = None,
                     port: int = DEFAULT_PORT, timeout: int = DEFAULT_TIMEOUT) -> Iterator['ConnectedDevice']:
    """Context manager to perform actions on a connected Juniper device.

    Arguments:
        fqdn: the FQDN of the Juniper device.
        username: the username to use to connect to the Juniper device.
        ssh_config: an ssh_config file if you want other than ~/.ssh/config
        port: the port to use to connect to the device.
        timeout: the timeout in seconds to use when operating on the device.

    Yields:
        The Juniper connected device instance.

    """
    try:
        device = ConnectedDevice(fqdn, username=username, ssh_config=ssh_config, port=port, timeout=timeout)
    except ConnectError as e:
        raise HomerConnectError(f'Unable to connect to {fqdn}') from e

    try:
        yield device
    finally:
        device.close()


# pylint: disable=no-member
# Pylint doesn't recognize the 'cu' member in junos.Device instances and generated-members seems to have a bug
class ConnectedDevice:
    """Juniper transport to manage a JunOS connected device."""

    def __init__(self, fqdn: str, *, username: str = '', ssh_config: Optional[str] = None,
                 port: int = DEFAULT_PORT, timeout: int = DEFAULT_TIMEOUT):
        """Initialize the instance and open the connection to the device.

        Arguments:
            fqdn: the FQDN of the Juniper device.
            username: the username to use to connect to the Juniper device.
            ssh_config: an ssh_config file if you want other than ~/.ssh/config
            port: the port to use to connect to the device.
            timeout: the timeout in seconds to use when operating on the device.

        """
        self._fqdn = fqdn
        self._port = port
        self._timeout = timeout
        logger.debug('Connecting to device %s (user=%s ssh_config=%s timeout=%d)',
                     self._fqdn, username, ssh_config, self._timeout)
        self._device = JunOSDevice(host=self._fqdn, user=username, port=self._port, ssh_config=ssh_config,
                                   conn_open_timeout=self._timeout)
        self._device.open()
        self._device.bind(cu=Config)

    def commit(self, config: DeviceConfigurationBase, message: str, *,  # noqa: MC0001
               ignore_warning: Union[bool, str, list[str]] = False, is_retry: bool = False) -> None:
        """Commit the loaded configuration.

        Arguments:
            config: the device new configuration.
            message: the commit message to use.
            ignore_warning: the warnings to tell JunOS to ignore, see below docs
                https://junos-pyez.readthedocs.io/en/2.3.0/jnpr.junos.utils.html#jnpr.junos.utils.config.Config.load
                also note the comments in the pyez decorators.py, substring match is default, regex is also possible
            is_retry: whether this is a retry and the commit_check should be run anyway, also if the
                diff is empty.

        Raises:
            homer.exceptions.HomerTimeoutError: on timeout.
            homer.exceptions.HomerError: on commit error.
            Exception: on generic failure.

        """
        diff = self._prepare(config, ignore_warning)
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
                self._rollback(ignore_warning=ignore_warning)
                return
            else:
                try:
                    answer = ask_approval()
                    if answer is ApprovalStatus.REJECT_SINGLE:
                        raise HomerError('Change rejected')
                    if answer is ApprovalStatus.REJECT_ALL:
                        diff_store.reject(diff)
                        raise HomerError('Change rejected for all devices')
                    if answer is ApprovalStatus.APPROVE_ALL:
                        diff_store.approve(diff)
                        logger.info('Change approved for all devices')
                    elif answer is not ApprovalStatus.APPROVE_SINGLE:
                        raise HomerError(f'Unknown approval status {answer}')
                except HomerError:
                    self._rollback(ignore_warning=ignore_warning)
                    raise

                logger.info('Committing the change on %s', self._fqdn)

        try:
            if diff:
                self._device.cu.commit(confirm=2, comment=message, timeout=self._timeout)
            self._device.cu.commit_check(timeout=self._timeout)
        except RpcTimeoutError as e:
            raise HomerTimeoutError(str(e)) from e
        except CommitError as e:
            raise HomerError(f'Commit error: {ConnectedDevice._parse_commit_error(e)}') from e

    def commit_check(self, config: DeviceConfigurationBase,
                     ignore_warning: Union[bool, str, list[str]] = False) -> Tuple[bool, Optional[str]]:
        """Perform commit check, return the diff and rollback.

        Arguments:
            config: the device new configuration.

        Returns:
            A two-element tuple with a boolean as first item that is :py:data:`True` on success and
            :py:data:`False` on failure and a string as second item with the difference between the current
            configuration and the new one, empty string on no diff and :py:data:`None` on failure.

        """
        success = False
        try:
            diff = self._prepare(config, ignore_warning)
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to get diff for %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)
            self._rollback(ignore_warning=ignore_warning)
            return False, None

        if not diff:
            logger.info('Empty diff for %s, skipping device.', self._fqdn)
            self._rollback(ignore_warning=ignore_warning)
            return True, diff

        logger.info('Running commit check on %s', self._fqdn)
        try:
            self._device.cu.commit_check(timeout=self._timeout)
            success = True
        except CommitError as e:
            logger.error('Commit check error on %s: %s', self._fqdn, ConnectedDevice._parse_commit_error(e))
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to commit check on %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)
        finally:
            self._rollback(ignore_warning=ignore_warning)

        return success, diff

    def close(self) -> None:
        """Close the connection with the device."""
        try:
            self._device.cu.unlock()
        except UnlockError:
            pass
        try:
            self._device.close()
        except (RpcTimeoutError, TimeoutExpiredError) as e:
            logger.warning('Unable to close the connection to the device: %s', e)

    def _prepare(self, config: DeviceConfigurationBase, ignore_warning: Union[bool, str, list[str]] = False) -> str:
        """Prepare the new configuration to be committed.

        Arguments:
            config: the device new configuration.

        Raises:
            Exception: on generic failure.

        Returns:
            The differences between the current config and the new one.

        """
        logger.debug('Preparing the configuration on %s', self._fqdn)
        diff = ''
        try:
            self._device.cu.lock()
            self._device.cu.load(str(config), format='text', merge=False, ignore_warning=ignore_warning)
            diff = self._device.cu.diff(ignore_warning=ignore_warning)
        except ConfigLoadError:
            raise
        except Exception:
            self._rollback(ignore_warning=ignore_warning)
            raise

        if diff is None:
            diff = ''

        return color_diff(diff)

    def _rollback(self, ignore_warning: Union[bool, str, list[str]] = False) -> None:
        """Rollback the current staged configuration."""
        logger.debug('Rolling back staged config on %s', self._fqdn)
        try:
            self._device.cu.rollback(ignore_warning=ignore_warning)
        except ValueError as e:
            logger.error('Invalid rollback ID on %s: %s', self._fqdn, e)
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to rollback on %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)

    @staticmethod
    def _parse_commit_error(exc: CommitError) -> str:
        """Parse a CommitError exception and returnonly the reason.

        Arguments:
            exc: the exception to parse.

        Returns:
            The reason for the commit errror.

        """
        if exc.rsp.find('.//ok') is None:
            try:
                path = exc.rsp.findtext('.//error-path').strip()
                element = exc.rsp.findtext('.//bad-element').strip()
                message = exc.rsp.findtext('.//error-message').strip()
                return f'{message}\nIn {path} ({element})'
            except AttributeError:
                pass
        return str(exc)
