"""__init__ module tests."""
import textwrap

from unittest import mock

import pytest

import homer

from homer import Homer
from homer.config import load_yaml_config
from homer.tests import get_fixture_path


def setup_tmp_path(path):
    """Initialize the temporary directory and configuration."""
    output = path / 'output'
    output.mkdir()
    config = load_yaml_config(get_fixture_path('cli', 'config.yaml'))
    config['base_paths']['output'] = str(output)
    return output, config


def test_version():
    """Check that the __version__ package variable is set."""
    assert hasattr(homer, '__version__')


class TestHomer:
    """Homer class tests."""

    @pytest.fixture(autouse=True)
    def setup_method_fixture(self, tmp_path):
        """Initialize the instance."""
        # pylint: disable=attribute-defined-outside-init
        self.output, self.config = setup_tmp_path(tmp_path)
        self.homer = Homer(self.config)

    def get_generated_files(self):
        """Get all the generated files in the output directory."""
        return [out_file.name for out_file in self.output.iterdir()
                if out_file.is_file() and out_file.suffix == Homer.OUT_EXTENSION]

    def test_execute_generate_ok(self):
        """It should generate the compiled configuration files for the matching devices."""
        spurious_file = self.output / 'spurious{suffix}'.format(suffix=Homer.OUT_EXTENSION)
        spurious_file.touch()  # To check that the file will be removed
        spurious_dir = self.output / 'spurious'
        spurious_dir.mkdir()

        ret = self.homer.generate('device*')

        assert ret == 0
        assert sorted(self.get_generated_files()) == ['device1.example.com.out', 'device2.example.com.out']
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

    def test_execute_no_private(self):
        """It should execute the whole program based on CLI arguments."""
        config = self.config.copy()
        del config['base_paths']['private']

        ret = Homer(config).generate('device*')

        assert ret == 0
        assert sorted(self.get_generated_files()) == ['device1.example.com.out', 'device2.example.com.out']
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
        assert self.get_generated_files() == ['valid.example.com.out']

    @mock.patch('homer.transports.junos.JunOSDevice')
    def test_execute_diff_ok(self, mocked_device):
        """It should diff the compiled configuration with the live one."""
        # TODO: to be expanded
        ret = self.homer.diff('device*')
        assert ret == 0
        assert mocked_device.called
