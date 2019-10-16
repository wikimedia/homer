"""Devices module."""
import fnmatch
import logging

from collections import defaultdict, UserDict
from typing import Any, Dict, List, NamedTuple, Optional

from homer.exceptions import HomerError


Device = NamedTuple('Device', [('fqdn', str), ('role', str), ('site', str), ('config', Dict), ('private', Dict)])
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Devices(UserDict):  # pylint: disable=too-many-ancestors
    """Collection of devices, accessible by FQDN as a dict or role and site via dedicated accessors."""

    role_prefix = 'role'
    site_prefix = 'site'

    def __init__(self, devices: Dict[str, Dict[Any, Any]], private_config: Optional[Dict[str, Any]] = None):
        """Initialize the instance.

        Arguments:
            devices (dict): the devices configuration with FQDN as key and a dictionary with role, site and
                device-specific configuration as value.
            private_config (dict, optional): an optional devices private configuration with FQDN as key and a
                dictionary of device-specific configuration as value. It cannot have top level keys in common with the
                same device public configuration.

        """
        super().__init__()
        if private_config is None:
            private_config = {}
        self._roles = defaultdict(list)  # type: defaultdict
        self._sites = defaultdict(list)  # type: defaultdict

        for fqdn, data in devices.items():
            device = Device(fqdn, data['role'], data['site'], data.get('config', {}), private_config.get(fqdn, {}))
            self.data[fqdn] = device
            self._roles[device.role].append(device)
            self._sites[device.site].append(device)

        logger.info('Initialized %d devices in %d role(s) and %d site(s)',
                    len(self.data), len(self._roles), len(self._sites))

    def role(self, name: str) -> List[Device]:
        """Get all the devices with a specific role.

        Arguments:
            name (str): the role name to filter for.

        Returns:
            list: a list of Device objects.

        """
        if name in self._roles:  # Avoid to create empty objects in defaultdict
            return self._roles[name]
        return []

    def site(self, name: str) -> List[Device]:
        """Get all the devices within a specific site.

        Arguments:
            name (str): the site name to filter for.

        Returns:
            list: a list of Device objects.

        """
        if name in self._sites:  # Avoid to create empty objects in defaultdict
            return self._sites[name]
        return []

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
        if ':' in query_string:  # Role or site query
            prefix, query = query_string.split(':', 1)
            if prefix not in (self.role_prefix, self.site_prefix):
                raise HomerError('Unknown query prefix: {prefix}'.format(prefix=prefix))
            results = getattr(self, prefix)(query)
        else:  # FQDN query
            results = [device for fqdn, device in self.items() if fnmatch.fnmatch(fqdn, query_string)]

        logger.info("Matched %d device(s) for query '%s'", len(results), query_string)
        return results
