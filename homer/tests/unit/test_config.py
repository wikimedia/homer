"""Config module tests."""
import pytest

from homer.config import load_yaml_config
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
