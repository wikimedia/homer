"""Devices module."""
import fnmatch
import logging

from collections import UserDict
from operator import attrgetter
from typing import List, Mapping, NamedTuple, Optional


Device = NamedTuple('Device', [('fqdn', str), ('metadata', Mapping), ('config', Mapping), ('private', Mapping)])
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Devices(UserDict):  # pylint: disable=too-many-ancestors
    """Collection of devices, accessible by FQDN as a dict or role and site via dedicated accessors."""

    def __init__(self, devices: Mapping[str, Mapping[str, str]], devices_config: Mapping[str, Mapping],
                 private_config: Optional[Mapping[str, Mapping]] = None):
        """Initialize the instance.

        Arguments:
            devices (dict): the devices configuration with FQDN as key and a dictionary with the device metadata as
                value.
            devices_config (dict): the devices configuration with FQDN as key and a dictionary with the device-specific
                configuration as value.
            private_config (dict, optional): an optional dictionary of the devices private configuration with the FQDN
                as key and a dictionary of device-specific private configuration as value. It cannot have top level
                keys in common with the same device public configuration.

        """
        super().__init__()
        if private_config is None:
            private_config = {}

        for fqdn, metadata in devices.items():
            self.data[fqdn] = Device(fqdn, metadata, devices_config.get(fqdn, {}), private_config.get(fqdn, {}))

        logger.info('Initialized %d devices', len(self.data))

    def query(self, query_string: str) -> List[Device]:
        """Get the devices matching the query.

        Todo:
            If needed, expand the query capabilities with a proper syntax using pyparsing.

        Arguments:
            query_string (str): the query_string to use to filter for.

        Raises:
            homer.exceptions.HomerError: on invalid query.

        Returns:
            list: a list of Device objects.

        """
        if ':' in query_string:  # Simple key-value query
            key, value = query_string.split(':', 1)
            results = [device for device in self.data.values() if device.metadata.get(key, None) == value]
        else:  # FQDN query
            results = [device for fqdn, device in self.items() if fnmatch.fnmatch(fqdn, query_string)]

        logger.info("Matched %d device(s) for query '%s'", len(results), query_string)
        return sorted(results, key=attrgetter('fqdn'))
