"""Devices module."""
import fnmatch
import logging

from collections import UserDict
from operator import attrgetter
from typing import List, Mapping, MutableMapping, NamedTuple, Optional


Device = NamedTuple('Device', [('fqdn', str), ('metadata', MutableMapping), ('config', Mapping), ('private', Mapping)])
logger = logging.getLogger(__name__)


class Devices(UserDict):
    """Collection of devices, accessible by FQDN as a dict or role and site via dedicated accessors."""

    def __init__(self, devices: Mapping[str, MutableMapping[str, str]], devices_config: Mapping[str, Mapping],
                 private_config: Optional[Mapping[str, Mapping]] = None):
        """Initialize the instance.

        Arguments:
            devices: the devices configuration with FQDN as key and a dictionary with the device metadata as value.
            devices_config: the devices configuration with FQDN as key and a dictionary with the device-specific
                configuration as value.
            private_config: an optional dictionary of the devices private configuration with the FQDN
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
        """Get the devices matching the query, supporting comma-separated sub-queries.

        This method processes a query string that can include:
        - Comma-separated sub-queries (e.g., "host*,db*") to match multiple patterns.
        - Key-value pairs (e.g., "key:value") to filter devices by metadata.
        - FQDN glob patterns (e.g., "host*") to match device FQDNs.

        The results are deduplicated and sorted by FQDN before returning.

        Arguments:
            query_string: The query string to filter devices. Can include comma-separated sub-queries,
                        key-value pairs, or FQDN glob patterns.

        Raises:
            homer.exceptions.HomerError: If the query is invalid or cannot be processed.

        Returns:
            A sorted list of unique Device objects matching the query.

        """
        results: list[Device] = []
        for sub_query_string in query_string.split(','):  # allow multiple sub queries, comma-separated
            for result in self._query(sub_query_string):
                if result not in results:
                    results.append(result)
        logger.info("Matched %d device(s) for query '%s'", len(results), query_string)
        return sorted(results, key=attrgetter('fqdn'))

    def _query(self, query_string: str) -> list[Device]:
        """Internal method to execute a single query and return matching devices.

        Supports two query types:
        - Key-value queries (e.g., "key:value") to filter devices by metadata.
        - FQDN glob patterns (e.g., "host*") to match device FQDNs.

        Arguments:
            query_string: The query string to filter devices. Can be a key-value pair or an FQDN glob pattern.

        Returns:
            A list of Device objects matching the query.

        """
        if ':' in query_string:  # Simple key-value query
            key, value = query_string.split(':', 1)
            return [device for device in self.data.values() if device.metadata.get(key, None) == value]
        # FQDN query
        # only do a full fqdn match if there is a dot in the query string.
        devices: list[Device] = []
        for fqdn, device in self.items():
            name = fqdn if '.' in query_string else fqdn.split('.')[0]
            if fnmatch.fnmatch(name, query_string):
                devices.append(device)
        return devices
