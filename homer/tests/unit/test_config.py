"""Config module tests."""
import pytest

from homer.config import HierarchicalConfig, load_yaml_config
from homer.devices import Device
from homer.exceptions import HomerError
from homer.tests import get_fixture_path


@pytest.mark.parametrize('name', ('empty.yaml', 'non-existent.yaml'))
def test_load_yaml_config_no_content(name):
    """Loading an empty or non-existent config should return an empty dictionary."""
    assert {} == load_yaml_config(get_fixture_path('config', name))


def test_load_yaml_config_raise():
    """Loading an invalid config should raise Exception."""
    with pytest.raises(HomerError, match='Could not load config file'):
        load_yaml_config(get_fixture_path('config', 'invalid.yaml'))


def test_load_yaml_config_valid():
    """Loading a valid config should return its content."""
    config_dict = load_yaml_config(get_fixture_path('config', 'valid.yaml'))
    assert 'key' in config_dict


def test_hierarchical_config_get():
    """Calling the get() method on an instance of HierarchicalConfig should return the config for a given Device."""
    device = Device('device1.example.com', 'roleA', 'siteA', {'device_key': 'device_value'})
    config = HierarchicalConfig(get_fixture_path('public', 'config'))
    expected = {'common_key': 'common_value', 'role_key': 'role_value', 'site_key': 'site_value',
                'device_key': 'device_value'}
    assert config.get(device) == expected
