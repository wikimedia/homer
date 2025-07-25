"""Junos module tests."""
import re

from unittest import mock

import pytest

from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError, RpcTimeoutError, UnlockError
from lxml import etree
from ncclient.operations.errors import TimeoutExpiredError

from homer.diff import DiffStore
from homer.exceptions import HomerConnectError, HomerError, HomerTimeoutError
from homer.transports import junos


COMMIT_MESSAGE = 'commit message'
ERROR_RESPONSE = """
    <rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
               xmlns:junos="http://xml.juniper.net/junos/16.1I0/junos"
               xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
    <load-configuration-results>
    <rpc-error>
        <error-severity>warning</error-severity>
        <bad-element>Bad Element</bad-element>
        <error-path>Error Path</error-path>
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
GENERATED_DIFF = """
[edit test-block1]
-     removed-line 1;
+     added-line 2;
[edit test-block2]
     term block1 { ... }
!    term block2 { ... }
"""
EXPECTED_DIFF = """
[edit test-block1]
\x1b[31m-     removed-line 1;\x1b[39m
\x1b[32m+     added-line 2;\x1b[39m
[edit test-block2]
     term block1 { ... }
\x1b[33m!    term block2 { ... }\x1b[39m
"""


@mock.patch('homer.transports.junos.ConnectedDevice', autospec=True)
def test_connected_device_ok(mocked_device):
    """It should return a context manager around a connected JunOS device."""
    with junos.connected_device('device1.example.com', username='username') as device:
        mocked_device.assert_called_once_with('device1.example.com', username='username', ssh_config=None,
                                              port=22, timeout=30)
        assert hasattr(device, 'commit')
        assert not mocked_device.return_value.close.called

    mocked_device.return_value.close.assert_called_once_with()


@mock.patch('homer.transports.junos.ConnectedDevice', autospec=True)
def test_connected_device_connect_error(mocked_device):
    """It should raise HomerConnectError if there is an error connecting to the device."""
    mocked_device.side_effect = ConnectError('device1.example.com')
    with pytest.raises(HomerConnectError, match='Unable to connect to device1.example.com'):
        with junos.connected_device('device1.example.com', username='username', timeout=10) as _:
            raise RuntimeError  # It should not execute this

        mocked_device.assert_called_once_with('device1.example.com', username='username', ssh_config=None, timeout=10)
        mocked_device.return_value.close.assert_not_called()


@mock.patch('homer.transports.junos.JunOSDevice', autospec=True)
class TestConnectedDevice:
    """ConnectedDevice class tests."""

    def setup_method(self):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.fqdn = 'device1.example.com'

    def teardown_method(self):
        """Cleanup."""
        DiffStore.reset()

    def test_init(self, mocked_junos_device):
        """It should connect to the device."""
        junos.ConnectedDevice(self.fqdn)
        mocked_junos_device.assert_called_once_with(host=self.fqdn, user='', port=22, ssh_config=None,
                                                    conn_open_timeout=30)

    def test_diff_ok(self, mocked_junos_device):
        """It should print a colored diff of the config."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = GENERATED_DIFF
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == EXPECTED_DIFF

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_commit_ok(self, mocked_isatty, mocked_input, mocked_junos_device):
        """It should commit the new config."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        device = junos.ConnectedDevice(self.fqdn)

        device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_called_once_with(
            confirm=2, comment=COMMIT_MESSAGE, timeout=30)

    @pytest.mark.parametrize('is_retry', (True, False))
    def test_commit_empty_diff(self, mocked_junos_device, is_retry):
        """It should skip the approval on empty diff and based on the is_retry parameter run commit_check or not."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = None
        device = junos.ConnectedDevice(self.fqdn, timeout=10)

        device.commit('config', COMMIT_MESSAGE, is_retry=is_retry)

        mocked_junos_device.return_value.cu.commit.assert_not_called()
        if is_retry:
            mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=10)
        else:
            mocked_junos_device.return_value.cu.commit_check.assert_not_called()

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_commit_abort(self, mocked_isatty, mocked_input, mocked_junos_device):
        """It should abort the commit and not log exception."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_isatty.return_value = True
        mocked_input.return_value = 'no'
        device = junos.ConnectedDevice(self.fqdn)

        with pytest.raises(HomerError):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_not_called()

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_commit_timeout(self, mocked_isatty, mocked_input, mocked_junos_device):
        """It should catch the timeout exception separately."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit.side_effect = RpcTimeoutError(
            mocked_junos_device, 'commit-configuration', 30)
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        device = junos.ConnectedDevice(self.fqdn)

        with pytest.raises(HomerTimeoutError):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit_check.assert_not_called()

    def test_commit_prepare_failed_load(self, mocked_junos_device):
        """It should raise if unable to load the configuration."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.load.side_effect = ConfigLoadError(
            etree.XML(ERROR_RESPONSE.format(insert='')))
        device = junos.ConnectedDevice(self.fqdn)

        with pytest.raises(ConfigLoadError):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_not_called()
        mocked_junos_device.return_value.cu.rollback.assert_not_called()

    def test_commit_prepare_failed_diff(self, mocked_junos_device):
        """It should raise HomerError if unable to get the diff for the commit."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.side_effect = ValueError
        device = junos.ConnectedDevice(self.fqdn)

        with pytest.raises(ValueError):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_not_called()

    @pytest.mark.parametrize('insert, expected, remove_line', (
        ('', 'Commit error: Error Message\nIn Error Path (Bad Element)', False),
        ('', 'Commit error: CommitError', True),
        ('<ok/>', 'Commit error: CommitError', False),
    ))
    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_commit_commit_error(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, mocked_isatty, mocked_input, mocked_junos_device, insert, expected, remove_line
    ):
        """On CommitError it should raise HomerError with the error message from the CommitError."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        error_response = ERROR_RESPONSE
        if remove_line:
            error_response = ERROR_RESPONSE.replace('        <bad-element>Bad Element</bad-element>\n', '')
        mocked_junos_device.return_value.cu.commit.side_effect = CommitError(
            etree.XML(error_response.format(insert=insert)))
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        device = junos.ConnectedDevice(self.fqdn, timeout=10)

        with pytest.raises(HomerError, match=re.escape(expected)):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_called_once_with(
            confirm=2, comment=COMMIT_MESSAGE, timeout=10)

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_commit_generic_error(self, mocked_isatty, mocked_input, mocked_junos_device):
        """On any other exception it should raise HomerError."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit.side_effect = ValueError
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        device = junos.ConnectedDevice(self.fqdn)

        with pytest.raises(ValueError):
            device.commit('config', COMMIT_MESSAGE)

        mocked_junos_device.return_value.cu.commit.assert_called_once_with(
            confirm=2, comment=COMMIT_MESSAGE, timeout=30)

    def test_commit_check_ok(self, mocked_junos_device):
        """It should commit check the new config and clean rollback the staged one."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == 'diff'
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=30)
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with(ignore_warning=False)

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
        assert f'Commit check error on {self.fqdn}: Error Message\nIn Error Path (Bad Element)' in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=30)
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with(ignore_warning=False)

    def test_commit_check_generic_error(self, mocked_junos_device, caplog):
        """On any other exception it should log the stacktrace from the exception."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.commit_check.side_effect = ValueError(
            'Error Message\nIn Error Path (Bad Element)')
        device = junos.ConnectedDevice(self.fqdn, timeout=10)

        success, diff = device.commit_check('config')

        assert not success
        assert diff == 'diff'
        assert f'Failed to commit check on {self.fqdn}: Error Message' in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=10)
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with(ignore_warning=False)

    def test_commit_check_rollback_value_error(self, mocked_junos_device, caplog):
        """It should log any rollback ValueError exception."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.rollback.side_effect = ValueError(50)
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == 'diff'
        assert f'Invalid rollback ID on {self.fqdn}: 50' in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=30)
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with(ignore_warning=False)

    def test_commit_check_rollback_error(self, mocked_junos_device, caplog):
        """It should log any rollback generic error."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.cu.diff.return_value = 'diff'
        mocked_junos_device.return_value.cu.rollback.side_effect = RpcTimeoutError(
            mocked_junos_device, 'load-configuration', 30)
        device = junos.ConnectedDevice(self.fqdn)

        success, diff = device.commit_check('config')

        assert success
        assert diff == 'diff'
        assert f'Failed to rollback on {self.fqdn}: RpcTimeoutError' in caplog.text
        mocked_junos_device.return_value.cu.commit_check.assert_called_once_with(timeout=30)
        mocked_junos_device.return_value.cu.rollback.assert_called_once_with(ignore_warning=False)

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

    def test_close_timeout(self, mocked_junos_device):
        """On TimeoutExpiredError it should not fail."""
        mocked_junos_device.return_value.cu = mock.MagicMock(spec_set=junos.Config)
        mocked_junos_device.return_value.close.side_effect = TimeoutExpiredError
        device = junos.ConnectedDevice(self.fqdn)

        device.close()

        mocked_junos_device.return_value.cu.unlock.assert_called_once_with()
        mocked_junos_device.return_value.close.assert_called_once_with()
