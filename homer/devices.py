"""Devices module."""
from collections import defaultdict, UserDict
from typing import Any, Dict, List, NamedTuple


Device = NamedTuple('Device', [('fqdn', str), ('role', str), ('site', str), ('config', Dict)])


class Devices(UserDict):  # pylint: disable=too-many-ancestors
    """Collection of devices, accessible by FQDN as a dict or role and site via dedicated accessors."""

    def __init__(self, devices: Dict[str, Dict[Any, Any]]):
        """Initialize the instance.

        Arguments:
            devices (dict): the devices configuration with FQDN as key and a dictionary with role, site and
                device-specific configuration as value.

        """
        super().__init__()
        self._roles = defaultdict(list)  # type: defaultdict
        self._sites = defaultdict(list)  # type: defaultdict

        for fqdn, data in devices.items():
            device = Device(fqdn, data['role'], data['site'], data['config'])
            self.data[fqdn] = device
            self._roles[device.role].append(device)
            self._sites[device.site].append(device)

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
