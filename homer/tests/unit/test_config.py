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


def test_hierarchical_config_get_no_private():
    """Calling the get() method on an instance of HierarchicalConfig should return the config for a given Device."""
    device = Device('device1.example.com', 'roleA', 'siteA', {'device_key': 'device1_value'}, {})
    config = HierarchicalConfig(get_fixture_path('public'))
    expected = {'common_key': 'common_value', 'role_key': 'roleA_value', 'site_key': 'siteA_value',
                'device_key': 'device1_value', 'role': 'roleA', 'site': 'siteA'}
    assert config.get(device) == expected


def test_hierarchical_config_get_with_private():
    """Calling the get() method on an instance of HierarchicalConfig should include the private config, if any."""
    device = Device('device1.example.com', 'roleA', 'siteA', {'device_key': 'device1_value'},
                    {'device_private_key': 'device1_private_value'})
    config = HierarchicalConfig(get_fixture_path('public'), private_base_path=get_fixture_path('private'))
    expected = {'common_key': 'common_value', 'role_key': 'roleA_value', 'site_key': 'siteA_value',
                'device_key': 'device1_value', 'common_private_key': 'common_private_value',
                'role_private_key': 'roleA_private_value', 'site_private_key': 'siteA_private_value',
                'device_private_key': 'device1_private_value', 'role': 'roleA', 'site': 'siteA'}
    assert config.get(device) == expected


def test_hierarchical_config_get_duplicate_keys():
    """If there are duplicate keys between public and private configuration."""
    device = Device('device1.example.com', 'roleA', 'siteA', {'device_key': 'device_value'},
                    {'role_key': 'duplicated_key'})
    config = HierarchicalConfig(get_fixture_path('public'), private_base_path=get_fixture_path('private'))
    with pytest.raises(HomerError, match=r'Configuration key\(s\) found in both public and private config'):
        config.get(device)
