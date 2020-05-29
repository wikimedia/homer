"""JunOS module."""
import logging

from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, Tuple, Union

from jnpr.junos import Device as JunOSDevice
from jnpr.junos.exception import CommitError, ConfigLoadError, RpcTimeoutError, UnlockError
from jnpr.junos.utils.config import Config
from ncclient.operations.errors import TimeoutExpiredError

from homer.exceptions import HomerError, HomerTimeoutError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@contextmanager
def connected_device(fqdn: str, *, username: str = '', ssh_config: Optional[str] = None) -> Iterator['ConnectedDevice']:
    """Context manager to perform actions on a connected Juniper device.

    Arguments:
        fqdn (str): the FQDN of the Juniper device.
        username (str): the username to use to connect to the Juniper device.
        ssh_config (Optional[str]): an ssh_config file if you want other than ~/.ssh/config

    Yields:
        ConnectedDevice: the Juniper connected device instance.

    """
    device = ConnectedDevice(fqdn, username=username, ssh_config=ssh_config)
    try:
        yield device
    finally:
        device.close()


# pylint: disable=no-member
# Pylint doesn't recognize the 'cu' member in junos.Device instances and generated-members seems to have a bug
class ConnectedDevice:
    """Juniper transport to manage a JunOS connected device."""

    def __init__(self, fqdn: str, *, username: str = '', ssh_config: Optional[str] = None):
        """Initialize the instance and open the connection to the device.

        Arguments:
            fqdn (str): the FQDN of the Juniper device.
            username (str): the username to use to connect to the Juniper device.
            ssh_config (Optional[str]): an ssh_config file if you want other than ~/.ssh/config

        """
        self._fqdn = fqdn
        logger.debug('Connecting to device %s (user %s ssh_config %s)', self._fqdn, username, ssh_config)
        self._device = JunOSDevice(host=self._fqdn, user=username, port=22, ssh_config=ssh_config)
        self._device.open()
        self._device.bind(cu=Config)

    def commit(self, config: str, message: str, callback: Callable, *,  # noqa, mccabe: MC0001 too complex (11)
               ignore_warning: Union[bool, str, List[str]] = False, is_retry: bool = False) -> None:
        """Commit the loaded configuration.

        Arguments:
            config (str): the device new configuration.
            message (str): the commit message to use.
            callback (callable): a callable function that accepts two parameters: a string with the FQDN of the
                current device and a string with the diff between the current configuration and the new one. The
                callback must raise any exception if the execution should be interrupted and the config rollbacked or
                return :py:data:`None`.
            ignore_warning (mixed, optional): the warnings to tell JunOS to ignore, see:
                https://junos-pyez.readthedocs.io/en/2.3.0/jnpr.junos.utils.html#jnpr.junos.utils.config.Config.load
            is_retry (bool, optional): whether this is a retry and the commit_check should be run anyway, also if the
                diff is empty.

        Raises:
            HomerTimeoutError: on timeout.
            HomerError: on commit error.
            Exception: on generic failure.

        """
        diff = self._prepare(config, ignore_warning)
        if not diff:
            if not is_retry:
                logger.info('Empty diff for %s, skipping device.', self._fqdn)
                return
        else:
            try:
                callback(self._fqdn, diff)
            except Exception:
                self._rollback()
                raise

        logger.info('Committing the configuration on %s', self._fqdn)
        try:
            if diff:
                self._device.cu.commit(confirm=2, comment=message)
            self._device.cu.commit_check()
        except RpcTimeoutError as e:
            raise HomerTimeoutError(str(e))
        except CommitError as e:
            raise HomerError('Commit error: {err}'.format(err=ConnectedDevice._parse_commit_error(e))) from e

    def commit_check(self, config: str,
                     ignore_warning: Union[bool, str, List[str]] = False) -> Tuple[bool, Optional[str]]:
        """Perform commit check, reuturn the diff and rollback.

        Arguments:
            config (str): the device new configuration.

        Returns:
            tuple: a two-element tuple with a boolean as first item that is :py:data:`True` on success and
            :py:data:`False` on failure and a string as second item with the difference between the current
            configuration and the new one, empty string on no diff and :py:data:`None` on failure.

        """
        success = False
        try:
            diff = self._prepare(config, ignore_warning)
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to get diff for %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)
            self._rollback()
            return False, None

        if not diff:
            logger.info('Empty diff for %s, skipping device.', self._fqdn)
            self._rollback()
            return True, diff

        logger.info('Running commit check on %s', self._fqdn)
        try:
            self._device.cu.commit_check()
            success = True
        except CommitError as e:
            logger.error('Commit check error on %s: %s', self._fqdn, ConnectedDevice._parse_commit_error(e))
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to commit check on %s: %s', self._fqdn, e)
            logger.debug('Traceback:', exc_info=True)
        finally:
            self._rollback()

        return success, diff

    def close(self) -> None:
        """Close the connection with the device."""
        try:
            self._device.cu.unlock()
        except UnlockError:
            pass
        try:
            self._device.close()
        except TimeoutExpiredError:
            logger.warning('Unable to close the connection to the device: TimeoutExpiredError')

    def _prepare(self, config: str, ignore_warning: Union[bool, str, List[str]] = False) -> str:
        """Prepare the new configuration to be committed.

        Arguments:
            config (str): the device new configuration.

        Raises:
            Exception: on generic failure.

        Returns:
            str: the differences between the current config and the new one.

        """
        logger.debug('Preparing the configuration on %s', self._fqdn)
        diff = ''
        try:
            self._device.cu.lock()
            self._device.cu.load(config, format='text', merge=False, ignore_warning=ignore_warning)
            diff = self._device.cu.diff()
        except ConfigLoadError:
            raise
        except Exception:
            self._rollback()
            raise

        if diff is None:
            diff = ''

        return diff

    def _rollback(self) -> None:
        """Rollback the current staged configuration."""
        logger.debug('Rolling back staged config on %s', self._fqdn)
        try:
            self._device.cu.rollback()
        except ValueError as e:
            logger.error('Invalid rollback ID on %s: %s', self._fqdn, e)

    @staticmethod
    def _parse_commit_error(exc: CommitError) -> str:
        """Parse a CommitError exception and returnonly the reason.

        Arguments:
            exc (jnpr.junos.exception.CommitError): the exception to parse.

        Returns:
            str: the reason for the commit errror.

        """
        if exc.rsp.find('.//ok') is None:
            return exc.rsp.findtext('.//error-message')
        return str(exc)
