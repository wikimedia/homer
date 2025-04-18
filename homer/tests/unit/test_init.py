"""__init__ module tests."""
import json
import textwrap

from pathlib import Path
from unittest import mock

import pytest

from jnpr.junos.exception import ConfigLoadError, RpcTimeoutError
from lxml import etree

import homer

from homer.config import load_yaml_config
from homer.diff import DiffStore
from homer.tests import get_fixture_path
from homer.tests.unit.transports.test_junos import ERROR_RESPONSE


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
            if out_file.is_file() and out_file.suffix == homer.Homer.OUT_EXTENSION]


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
        self.homer = homer.Homer(self.config)

    def teardown_method(self):
        """Cleanup."""
        DiffStore.reset()

    def test_generate_ok(self):
        """It should generate the compiled configuration files for the matching devices."""
        spurious_file = self.output / f'spurious{homer.Homer.OUT_EXTENSION}'
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
        with open(str(self.output / 'device2.example.com.out'), encoding='utf-8') as f:
            assert textwrap.dedent(expected).lstrip('\n') == f.read()

    def test_generate_no_private(self):
        """It should execute the whole program based on CLI arguments."""
        config = self.config.copy()
        del config['base_paths']['private']

        ret = homer.Homer(config).generate('device*')

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
        with open(str(self.output / 'device2.example.com.out'), encoding='utf-8') as f:
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
    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_diff_ok(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, mocked_device, diff, omit_diff, expected, ret, capsys):
        """It should diff the compiled configuration with the live one."""
        mocked_device.return_value.cu.diff.return_value = diff
        return_code = self.homer.diff('device*', omit_diff=omit_diff)

        out, _ = capsys.readouterr()
        assert return_code == ret
        assert mocked_device.return_value.cu.diff.called
        assert expected in out

    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_diff_raise(self, mocked_device, capsys, caplog):
        """It should skip the device that raises an HomerLoadError."""
        mocked_device.return_value.cu.load.side_effect = ConfigLoadError(
            etree.XML(ERROR_RESPONSE.format(insert='')))
        return_code = self.homer.diff('device1*')

        out, _ = capsys.readouterr()
        assert return_code == 1
        assert 'Failed to get diff for device1.example.com: ConfigLoadError(' in caplog.text
        assert "Changes for 1 devices: ['device1.example.com']\n# Failed" in out

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
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
    @mock.patch('homer.interactive.sys.stdout.isatty')
    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_commit_timeout(self, mocked_device, mocked_isatty, mocked_input, caplog):
        """It should retry TIMEOUT_ATTEMPTS times and report the failure."""
        message = 'commit message'
        mocked_device.return_value.cu.diff.return_value = 'diff'
        mocked_device.return_value.cu.commit.side_effect = RpcTimeoutError(mocked_device, message, 30)
        mocked_isatty.return_value = True
        mocked_input.return_value = 'yes'
        ret = self.homer.commit('device*', message=message)
        assert ret == 1
        assert 'Attempt 3/3 failed' in caplog.text

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    @mock.patch('homer.transports.junos.JunOSDevice')
    @pytest.mark.parametrize('input_value, expected', (
        ('no', 'Change rejected'),
        ('invalid', 'Too many invalid answers, commit aborted'),
    ))
    def test_execute_commit_abort(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, mocked_device, mocked_isatty, mocked_input, input_value, expected, caplog):
        """It should skip a device and log a warning if the commit is aborted."""
        message = 'commit message'
        mocked_isatty.return_value = True
        mocked_input.return_value = input_value
        mocked_device.return_value.cu.diff.return_value = 'diff'
        ret = self.homer.commit('device*', message=message)
        assert ret == 1
        assert expected in caplog.text
        mocked_device.return_value.cu.commit.assert_not_called()

    @mock.patch('homer.interactive.sys.stdout.isatty')
    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_commit_notty(self, mocked_device, mocked_isatty, caplog):
        """It should skip a device and log a warning if the commit is aborted."""
        mocked_isatty.return_value = False
        mocked_device.return_value.cu.diff.return_value = 'diff'
        ret = self.homer.commit('device*', message='commit message')
        assert ret == 1
        assert 'Not in a TTY, unable to ask for confirmation' in caplog.text
        mocked_device.return_value.cu.commit.assert_not_called()


class TestHomerNetbox:
    """Homer class tests with Netbox enabled."""

    @pytest.fixture(autouse=True)
    @mock.patch('homer.NetboxData', autospec=True)
    @mock.patch('homer.pynetbox.api')  # Pynetbox objects lazily resolve API objects, can't use autospec=True
    def setup_method_fixture(self, mocked_pynetbox, mocked_netbox_data, requests_mock, tmp_path):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.output, self.config = setup_tmp_path('config-netbox.yaml', tmp_path)
        mocked_pynetbox.return_value.base_url = 'https://localhost/api'
        self.mocked_pynetbox = mocked_pynetbox
        self.requests_mock = requests_mock
        device_list = json.loads(
            Path(get_fixture_path('netbox', 'device_list.json')).read_text(encoding="UTF-8")
        )
        self.requests_mock.post('/graphql/', json=device_list)  # nosec
        capirca_script = self.mocked_pynetbox.return_value.extras.scripts.get.return_value.result
        capirca_script.status = 'Completed'
        capirca_script.completed = '2025-04-01 10:00:00Z'
        capirca_script.data.output = 'device1 = 10.0.0.1\ndevices_group = device1'
        mocked_netbox_data.return_value = {'netbox_key': 'netbox_value'}

        self.homer = homer.Homer(self.config)

    def teardown_method(self):
        """Cleanup."""
        DiffStore.reset()

    def test_init(self):
        """The instance should have setup the Netbox API."""
        self.mocked_pynetbox.assert_called_once_with('https://netbox.example.com',  # nosec
                                                     token='token',
                                                     threading=True)

    @mock.patch('homer.NetboxDeviceData', autospec=True)
    def test_execute_generate(self, mocked_netbox_device_data):
        """It should generate the configuration for the given device, including netbox data."""
        mocked_netbox_device_data.return_value = {'netbox_key': 'netbox_device_value'}
        ret = self.homer.generate('device*')

        assert ret == 0
        assert sorted(get_generated_files(self.output)) == ['device1-vc1.example.com.out',
                                                            'device1.example.com.out',
                                                            'device2.example.com.out']
        expected = """
            roleA;
            siteA;
            device2.example.com;
            common_value;
            roleA_value;
            siteA_value;
            device2_value;
            common_private_value;
            roleA_private_value;
            siteA_private_value;
            device2_private_value;
            netbox_value;
            netbox_device_value;
            netbox_device_plugin;
        """
        with open(str(self.output / 'device2.example.com.out'), encoding='utf-8') as f:
            assert textwrap.dedent(expected).lstrip('\n') == f.read()

    @mock.patch('homer.NetboxDeviceData', autospec=True)
    @mock.patch('homer.NetboxInventory', autospec=True)
    @mock.patch('homer.transports.junos.ConnectedDevice', autospec=True)
    @pytest.mark.parametrize('name, suffix, port, timeout', (('device1', 'A', 22, 30),
                                                             ('device2', 'B', 2222, 10)))
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def test_execute_diff_inventory(self, mocked_connected_device, mocked_netbox_inventory,
                                    mocked_netbox_device_data, name, suffix, port, timeout):
        """It should generate the configuration for the given device, including netbox data."""
        fqdn = f'{name}.example.com'
        mocked_connected_device.return_value.commit_check.return_value = (True, '')
        mocked_netbox_inventory.return_value.get_devices.return_value = {
            fqdn: {
                'role': f'role{suffix}',
                'site': f'site{suffix}',
                'type': f'type{suffix}',
                'status': 'active',
                'netbox_object': mock.MagicMock(),
            }
        }
        mocked_netbox_device_data.return_value = {'netbox_key': 'netbox_device_value'}

        ret = self.homer.diff(f'{fqdn}')

        assert ret == 0
        mocked_connected_device.assert_called_once_with(fqdn, username='', ssh_config=None,
                                                        port=port, timeout=timeout)
