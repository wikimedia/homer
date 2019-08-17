"""CLI module tests."""
import argparse

from homer import cli
from homer.tests import get_fixture_path


def test_argument_parser():
    """It should return an ArgumentParser parser."""
    assert isinstance(cli.argument_parser(), argparse.ArgumentParser)


def test_main():
    """It should execute the whole program based on CLI arguments."""
    config_path = get_fixture_path('cli', 'config.yaml')
    assert cli.main(['-c', config_path, 'compile', 'test.example.com']) is None
