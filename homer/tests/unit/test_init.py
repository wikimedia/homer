"""__init__ module tests."""
import textwrap

from unittest import mock

import pytest

import homer

from homer.config import load_yaml_config
from homer.exceptions import HomerError
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


def test_execute_invalid_action():
    """Should raise HomerError if the action is not recognized."""
    with pytest.raises(HomerError, match='Invalid action invalid, expected one of'):
        homer.execute({}, 'invalid', '')


def test_execute_generate_ok(tmp_path):
    """It should generate the compiled configuration files for the matching devices."""
    output, config = setup_tmp_path(tmp_path)
    spurious_file = output / 'spurious{suffix}'.format(suffix=homer.OUT_EXTENSION)
    spurious_file.touch()  # To check that the file will be removed
    spurious_dir = output / 'spurious'
    spurious_dir.mkdir()

    ret = homer.execute(config, 'generate', 'device*')

    assert ret == 0
    files = [out_file.name for out_file in output.iterdir()
             if out_file.is_file() and out_file.suffix == homer.OUT_EXTENSION]
    assert sorted(files) == ['device1.example.com.out', 'device2.example.com.out']
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
    with open(str(output / 'device2.example.com.out')) as f:
        assert textwrap.dedent(expected).lstrip('\n') == f.read()


def test_execute_no_private(tmp_path):
    """It should execute the whole program based on CLI arguments."""
    output, config = setup_tmp_path(tmp_path)
    del config['base_paths']['private']

    ret = homer.execute(config, 'generate', 'device*')

    assert ret == 0
    files = [out_file.name for out_file in output.iterdir()
             if out_file.is_file() and out_file.suffix == homer.OUT_EXTENSION]
    assert sorted(files) == ['device1.example.com.out', 'device2.example.com.out']
    expected = """
        roleB;
        siteB;
        device2.example.com;
        common_value;
        roleB_value;
        siteB_value;
        device2_value;
    """
    with open(str(output / 'device2.example.com.out')) as f:
        assert textwrap.dedent(expected).lstrip('\n') == f.read()


def test_execute_generate_fail_to_render(tmp_path):
    """It should skip devices that fails to render the configuration."""
    output, config = setup_tmp_path(tmp_path)

    ret = homer.execute(config, 'generate', 'site:siteC')

    assert ret == 1
    files = [out_file.name for out_file in output.iterdir()
             if out_file.is_file() and out_file.suffix == homer.OUT_EXTENSION]
    assert files == ['valid.example.com.out']


@mock.patch('homer.transports.junos.JunOSDevice')
def test_execute_diff_ok(mocked_device, tmp_path):
    """It should diff the compiled configuration with the live one."""
    _, config = setup_tmp_path(tmp_path)
    # TODO: to be completed once the diff feature is added
    ret = homer.execute(config, 'diff', 'device*')
    assert ret == 0
    assert mocked_device.called
