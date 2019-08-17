"""Config module."""
import os

from typing import Dict

import yaml

from homer.exceptions import HomerError


def load_yaml_config(config_file: str) -> Dict:
    """Parse a YAML config file and return it.

    Arguments:
        config_file (str): the path of the configuration file.

    Returns:
        dict: the parsed config or an empty dictionary if the file doesn't exists.

    Raises:
        HomerError: if failed to load the configuration.

    """
    config = {}  # type: Dict
    if not os.path.exists(config_file):
        return config

    try:
        with open(config_file, 'r') as fh:
            config = yaml.safe_load(fh)

    except Exception as e:  # pylint: disable=broad-except
        raise HomerError('Could not load config file {file}: {e}'.format(file=config_file, e=e)) from e

    if config is None:
        config = {}

    return config
