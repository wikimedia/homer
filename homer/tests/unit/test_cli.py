"""CLI module tests."""
import argparse

import yaml

from homer import cli
from homer.config import load_yaml_config
from homer.tests import get_fixture_path


def test_argument_parser():
    """It should return an ArgumentParser parser."""
    assert isinstance(cli.argument_parser(), argparse.ArgumentParser)


def test_main(tmp_path):
    """It should execute the whole program based on CLI arguments."""
    output = tmp_path / 'output'
    output.mkdir()
    config = load_yaml_config(get_fixture_path('cli', 'config.yaml'))
    config['base_paths']['output'] = str(output)
    config_path = tmp_path / 'config.yaml'
    with open(str(config_path), 'w') as f:
        yaml.dump(config, f)

    assert cli.main(['-c', str(config_path), 'device1.example.com', 'generate']) == 0
