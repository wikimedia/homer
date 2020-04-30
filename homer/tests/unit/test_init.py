"""__init__ module tests."""
import textwrap

from unittest import mock

import pytest

from jnpr.junos.exception import RpcTimeoutError

import homer

from homer import Homer
from homer.config import load_yaml_config
from homer.tests import get_fixture_path


def setup_tmp_path(file_name, path):
    """Initialize the temporary directory and configuration."""
    output = path / 'output'
    output.mkdir()
    config = load_yaml_config(get_fixture_path('cli', file_name))
    config['base_paths']['output'] = str(output)
    return output, config


def get_generated_files(path):
    """Get all the generated files in the output directory."""
    return [out_file.name for out_file in path.iterdir()
            if out_file.is_file() and out_file.suffix == Homer.OUT_EXTENSION]


def test_version():
    """Check that the __version__ package variable is set."""
    assert hasattr(homer, '__version__')


class TestHomer:
    """Homer class tests."""

    @pytest.fixture(autouse=True)
    def setup_method_fixture(self, tmp_path):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.output, self.config = setup_tmp_path('config.yaml', tmp_path)
        self.homer = Homer(self.config)

    def test_generate_ok(self):
        """It should generate the compiled configuration files for the matching devices."""
        spurious_file = self.output / 'spurious{suffix}'.format(suffix=Homer.OUT_EXTENSION)
        spurious_file.touch()  # To check that the file will be removed
        spurious_dir = self.output / 'spurious'
        spurious_dir.mkdir()

        ret = self.homer.generate('device*')

        assert ret == 0
        assert sorted(get_generated_files(self.output)) == ['device1.example.com.out', 'device2.example.com.out']
        expected = """
            roleB;
            siteB;
            device2.example.com;
            common_value;
            roleB_value;
            siteB_value;
            device2_value;
            common_private_value;
            roleB_private_value;
            siteB_private_value;
            device2_private_value;
        """
        with open(str(self.output / 'device2.example.com.out')) as f:
            assert textwrap.dedent(expected).lstrip('\n') == f.read()

    def test_generate_no_private(self):
        """It should execute the whole program based on CLI arguments."""
        config = self.config.copy()
        del config['base_paths']['private']

        ret = Homer(config).generate('device*')

        assert ret == 0
        assert sorted(get_generated_files(self.output)) == ['device1.example.com.out', 'device2.example.com.out']
        expected = """
            roleB;
            siteB;
            device2.example.com;
            common_value;
            roleB_value;
            siteB_value;
            device2_value;
        """
        with open(str(self.output / 'device2.example.com.out')) as f:
            assert textwrap.dedent(expected).lstrip('\n') == f.read()

    def test_execute_generate_fail_to_render(self):
        """It should skip devices that fails to render the configuration."""
        ret = self.homer.generate('site:siteC')

        assert ret == 1
        assert get_generated_files(self.output) == ['valid.example.com.out']

    @pytest.mark.parametrize('diff, omit_diff, expected, ret', (
        ('', False, '# No diff', 0),
        ('', True, '# No diff', 0),
        ('some diff', False, 'some diff', 99),
        ('some diff', True, '# Non-empty diff omitted, -o/--omit-diff set', 99),
    ))
    @mock.patch('homer.transports.junos.JunOSDevice')  # pylint: disable=too-many-arguments
    def test_execute_diff_ok(self, mocked_device, diff, omit_diff, expected, ret, capsys):
        """It should diff the compiled configuration with the live one."""
        mocked_device.return_value.cu.diff.return_value = diff
        return_code = self.homer.diff('device*', omit_diff=omit_diff)

        out, _ = capsys.readouterr()
        assert return_code == ret
        assert mocked_device.return_value.cu.diff.called
        assert expected in out

    @mock.patch('builtins.input')
    @mock.patch('homer.sys.stdout.isatty')
    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_commit_ok(self, mocked_device, mocked_isatty, mocked_input):
        """It should commit the compiled configuration to the device."""
        # TODO: to be expanded
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        ret = self.homer.commit('device*', message='commit message')
        assert ret == 0
        assert mocked_device.called

    @mock.patch('builtins.input')
    @mock.patch('homer.sys.stdout.isatty')
    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_commit_timeout(self, mocked_device, mocked_isatty, mocked_input, caplog):
        """It should retry TIMEOUT_ATTEMPTS times and report the failure."""
        message = 'commit message'
        mocked_device.return_value.cu.commit.side_effect = RpcTimeoutError(mocked_device, message, 30)
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        ret = self.homer.commit('device*', message=message)
        assert ret == 1
        assert 'Commit attempt 3/3 failed' in caplog.text


class TestHomerNetbox:
    """Homer class tests with Netbox enabled."""

    @pytest.fixture(autouse=True)
    @mock.patch('homer.pynetbox.api', autospec=True)
    def setup_method_fixture(self, mocked_pynetbox, tmp_path):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.output, self.config = setup_tmp_path('config-netbox.yaml', tmp_path)
        self.mocked_pynetbox = mocked_pynetbox
        self.homer = Homer(self.config)

    def test_init(self):
        """The instance should have setup the Netbox API."""
        self.mocked_pynetbox.assert_called_once_with('https://netbox.example.com', token='token')  # nosec

    @mock.patch('homer.NetboxDeviceData', autospec=True)
    @mock.patch('homer.NetboxData', autospec=True)
    def test_execute_generate(self, mocked_netbox_data, mocked_netbox_device_data):
        """It should generate the configuration for the given device, including netbox data."""
        mocked_netbox_data.return_value = {'netbox_key': 'netbox_value'}
        mocked_netbox_device_data.return_value = {'netbox_key': 'netbox_device_value'}

        ret = self.homer.generate('device*')

        assert ret == 0
        assert sorted(get_generated_files(self.output)) == ['device1.example.com.out', 'device2.example.com.out']
        expected = """
            roleB;
            siteB;
            device2.example.com;
            common_value;
            roleB_value;
            siteB_value;
            device2_value;
            common_private_value;
            roleB_private_value;
            siteB_private_value;
            device2_private_value;
            netbox_value;
            netbox_device_value;
            netbox_device_plugin;
        """
        with open(str(self.output / 'device2.example.com.out')) as f:
            assert textwrap.dedent(expected).lstrip('\n') == f.read()
