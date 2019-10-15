"""Junos module tests."""
from unittest import mock

import pytest

from jnpr.junos.exception import CommitError, UnlockError
from lxml import etree

from homer.exceptions import HomerError
from homer.transports import junos


COMMIT_MESSAGE = 'commit message'
ERROR_RESPONSE = """
    <rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
               xmlns:junos="http://xml.juniper.net/junos/16.1I0/junos"
               xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
    <load-configuration-results>
    <rpc-error>
        <error-severity>warning</error-severity>
        <error-message>Error Message</error-message>
    </rpc-error>
    <rpc-error>
        <error-severity>warning</error-severity>
        <error-message>statement not found</error-message>
    </rpc-error>
    {insert}
    </load-configuration-results>
    </rpc-reply>
"""


@mock.patch('homer.transports.junos.ConnectedDevice', autospec=True)
def test_connected_device(mocked_device):
    """It should return a context manager around a connected JunOS device."""
    with junos.connected_device('device1.example.com') as device:
        mocked_device.assert_called_once_with('device1.example.com')
        assert hasattr(device, 'commit')
        assert not mocked_device.return_value.close.called

    mocked_device.return_value.close.assert_called_once_with()


@mock.patch('homer.transports.junos.JunOSDevice', autospec=True)
class TestConnectedDevice:
    """ConnectedDevice class tests."""

    def setup_method(self, _):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.fqdn = 'device1.example.com'

    def test_init(self, mocked_junos_device):
        """It should connect to the device."""
        junos.ConnectedDevice(self.fqdn)
        mocked_junos_device.assert_called_once_with(host=self.fqdn, port=22)

    def test_commit_ok(self, mocked_junos_device):
        """It should commit the new config."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        device = junos.ConnectedDevice(self.fqdn)
        callback = mock.Mock()

        device.commit('config', COMMIT_MESSAGE, callback)

        callback.assert_called_once_with('device1.example.com', 'diff')
        mocked_junos_device.return_value.cu.commit.assert_called_once_with(confirm=2, comment=COMMIT_MESSAGE)

    def test_commit_prepare_failed(self, mocked_junos_device):
        """It should raise HomerError if unable to prepare the commit."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.side_effect = ValueError
        device = junos.ConnectedDevice(self.fqdn)
        callback = mock.Mock()
        with pytest.raises(HomerError, match='Failed to prepare commit on'):
            device.commit('config', COMMIT_MESSAGE, callback)

        callback.assert_not_called()
        mocked_junos_device.return_value.cu.commit.assert_not_called()

    def test_commit_commit_error(self, mocked_junos_device):
        """On CommitError it should raise HomerError with the error message from the CommitError."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit.side_effect = CommitError(
            etree.XML(ERROR_RESPONSE.format(insert='')))
        device = junos.ConnectedDevice(self.fqdn)
        callback = mock.Mock()

        with pytest.raises(
                HomerError, match='Failed to commit configuration on {fqdn}: Error Message'.format(fqdn=self.fqdn)):
            device.commit('config', COMMIT_MESSAGE, callback)

        callback.assert_called_once_with('device1.example.com', 'diff')
        mocked_junos_device.return_value.cu.commit.assert_called_once_with(confirm=2, comment=COMMIT_MESSAGE)

    def test_commit_commit_error_unknown(self, mocked_junos_device):
        """On CommitError it should raise HomerError with the CommitError message if unable to parse it."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit.side_effect = CommitError(
            etree.XML(ERROR_RESPONSE.format(insert='<ok/>')))
        device = junos.ConnectedDevice(self.fqdn)
        callback = mock.Mock()

        with pytest.raises(
                HomerError, match='Failed to commit configuration on {fqdn}: CommitError'.format(fqdn=self.fqdn)):
            device.commit('config', COMMIT_MESSAGE, callback)

        callback.assert_called_once_with('device1.example.com', 'diff')
        mocked_junos_device.return_value.cu.commit.assert_called_once_with(confirm=2, comment=COMMIT_MESSAGE)

    def test_commit_generic_error(self, mocked_junos_device):
        """On any other exception it should raise HomerError."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit.side_effect = ValueError
        device = junos.ConnectedDevice(self.fqdn)
        callback = mock.Mock()

        with pytest.raises(HomerError, match=r'Failed to commit configuration on {fqdn}$'.format(fqdn=self.fqdn)):
            device.commit('config', COMMIT_MESSAGE, callback)

        callback.assert_called_once_with('device1.example.com', 'diff')
        mocked_junos_device.return_value.cu.commit.assert_called_once_with(confirm=2, comment=COMMIT_MESSAGE)

    def test_commit_check_ok(self, mocked_junos_device):
        """It should commit check the new config and clean rollback the staged one."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == 'diff'
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with()
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with()

    def test_commit_check_commit_error(self, mocked_junos_device, caplog):
        """On CommitError it should log the error message from the CommitError."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit_check.side_effect = CommitError(
            etree.XML(ERROR_RESPONSE.format(insert='')))
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert not success
        assert diff == 'diff'
        assert 'Failed to commit check configuration on {fqdn}: Error Message'.format(fqdn=self.fqdn) in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with()
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with()

    def test_commit_check_generic_error(self, mocked_junos_device, caplog):
        """On any other exception it should log the stacktrace from the exception."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit_check.side_effect = ValueError('Error Message')
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert not success
        assert diff == 'diff'
        assert 'Failed to commit check configuration on {fqdn}: Error Message'.format(fqdn=self.fqdn) in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with()
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with()

    def test_commit_check_rollback_error(self, mocked_junos_device, caplog):
        """It should log any rollback error."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.rollback.side_effect = ValueError(50)
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == 'diff'
        assert 'Invalid rollback ID on {fqdn}: 50'.format(fqdn=self.fqdn) in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with()
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with()

    def test_close_ok(self, mocked_junos_device):
        """It should unlock and close the connection."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        device = junos.ConnectedDevice(self.fqdn)

        device.close()

        mocked_junos_device.return_value.cu.unlock.assert_called_once_with()
        mocked_junos_device.return_value.close.assert_called_once_with()

    def test_close_unlock_error(self, mocked_junos_device):
        """On UnlockError it should continue to close the connection."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.unlock.side_effect = UnlockError(
            etree.XML(ERROR_RESPONSE.format(insert='')))
        device = junos.ConnectedDevice(self.fqdn)

        device.close()

        mocked_junos_device.return_value.cu.unlock.assert_called_once_with()
        mocked_junos_device.return_value.close.assert_called_once_with()