"""JunOS module."""
import logging

from contextlib import contextmanager
from typing import Callable, Iterator, Tuple

from jnpr.junos import Device as JunOSDevice
from jnpr.junos.exception import CommitError, UnlockError
from jnpr.junos.utils.config import Config

from homer.exceptions import HomerError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@contextmanager
def connected_device(fqdn: str) -> Iterator['ConnectedDevice']:
    """Context manager to perform actions on a connected Juniper device.

    Arguments:
        fqdn (str): the FQDN of the Juniper device.

    Yields:
        ConnectedDevice: the Juniper connected device instance.

    """
    device = ConnectedDevice(fqdn)
    try:
        yield device
    finally:
        device.close()


# pylint: disable=no-member
# Pylint doesn't recognize the 'cu' member in junos.Device instances and generated-members seems to have a bug
class ConnectedDevice:
    """Juniper transport to manage a JunOS connected device."""

    def __init__(self, fqdn: str):
        """Initialize the instance and open the connection to the device.

        Arguments:
            fqdn (str): the FQDN of the Juniper device.

        """
        self._fqdn = fqdn
        logger.debug('Connecting to device %s', self._fqdn)
        self._device = JunOSDevice(host=self._fqdn, port=22)
        self._device.open()
        self._device.bind(cu=Config)

    def commit(self, config: str, message: str, callback: Callable) -> None:
        """Commit the loaded configuration.

        Arguments:
            config (str): the device new configuration.
            message (str): the commit message to use.
            callback (callable): a callable function that accepts two parameters: a string with the FQDN of the
                current device and a string with the diff between the current configuration and the new one. The
                callback must raise any exception if the execution should be interrupted and the config rollbacked or
                return :py:data:`None`.

        Raises:
            HomerError: when failing to commit the configuration.

        """
        try:
            diff = self._prepare(config)
            if diff is None:
                logger.info('Empty diff for %s, skipping.', self._fqdn)
                return
            callback(self._fqdn, diff)
        except Exception as e:  # pylint: disable=broad-except
            self._rollback()
            raise HomerError('Failed to prepare commit on {fqdn}'.format(fqdn=self._fqdn)) from e

        logger.info('Committing the configuration on %s', self._fqdn)
        try:
            self._device.cu.commit(confirm=2, comment=message)
            self._device.cu.commit_check()
        except CommitError as e:
            raise HomerError('Failed to commit configuration on {fqdn}: {reason}'.format(
                fqdn=self._fqdn, reason=ConnectedDevice._parse_commit_error(e))) from e
        except Exception as e:
            raise HomerError('Failed to commit configuration on {fqdn}'.format(fqdn=self._fqdn)) from e

    def commit_check(self, config: str) -> Tuple[bool, str]:
        """Perform commit check, reuturn the diff and rollback.

        Arguments:
            config (str): the device new configuration.

        Returns:
            tuple: a two-element tuple with a boolean as first item that is :py:data:`True` on success and
            :py:data:`False` on failure and a string as second item with the difference between the current
            configuration and the new one or an empty string on failure.

        """
        success = False
        diff = ''
        try:
            diff = self._prepare(config)
            logger.info('Running commit check on %s', self._fqdn)
            self._device.cu.commit_check()
            success = True
        except CommitError as e:
            logger.error('Failed to commit check configuration on %s: %s',
                         self._fqdn, ConnectedDevice._parse_commit_error(e))
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to commit check configuration on %s: %s', self._fqdn, e)
            logger.debug('Full stacktrace', exc_info=True)
        finally:
            self._rollback()

        return success, diff

    def close(self) -> None:
        """Close the connection with the device."""
        try:
            self._device.cu.unlock()
        except UnlockError:
            pass
        self._device.close()

    def _prepare(self, config: str) -> str:
        """Prepare the new configuration to be committed.

        Arguments:
            config (str): the device new configuration.

        Returns:
            str: the differences between the current config and the new one.

        """
        logger.debug('Preparing the configuration on %s', self._fqdn)
        self._device.cu.lock()
        self._device.cu.load(config, format='text', merge=False)
        return self._device.cu.diff()

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