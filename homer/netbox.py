"""Netbox module."""
import ipaddress
import logging

from collections import UserDict
from typing import Any, Dict, List, Optional, Sequence

import pynetbox

from homer.devices import Device


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class BaseNetboxData(UserDict):  # pylint: disable=too-many-ancestors
    """Base class to gather data dynamically from Netbox."""

    def __init__(self, api: pynetbox.api):
        """Initialize the dictionary.

        Arguments:
            api (pynetbox.api): the Netbox API instance.

        """
        super().__init__()
        self._api = api

    def __getitem__(self, key: Any) -> Any:
        """Dynamically call the related method, if exists, to return the requested data.

        Parameters according to Python's datamodel, see:
        https://docs.python.org/3/reference/datamodel.html#object.__getitem__

        Returns:
            mixed: the dynamically gathered data.

        """
        method_name = '_get_{key}'.format(key=key)
        if not hasattr(self, method_name):
            raise KeyError(key)

        if key not in self.data:
            self.data[key] = getattr(self, method_name)()
        return self.data[key]


class BaseNetboxDeviceData(BaseNetboxData):  # pylint: disable=too-many-ancestors
    """Base class to gather device-specific data dynamically from Netbox."""

    def __init__(self, api: pynetbox.api, device: Device):
        """Initialize the dictionary.

        Arguments:
            api (pynetbox.api): the Netbox API instance.
            device (homer.devices.Device): the device for which to gather the data.

        """
        super().__init__(api)
        self._device = device


class NetboxData(BaseNetboxData):  # pylint: disable=too-many-ancestors
    """Dynamic dictionary to gather the required generic data from Netbox."""

    def _get_vlans(self) -> List[Dict[str, Any]]:
        """Returns all the vlans defined in Netbox.

        Returns:
            list: a list of vlans.

        """
        return [dict(i) for i in self._api.ipam.vlans.all()]


class NetboxDeviceData(BaseNetboxDeviceData):  # pylint: disable=too-many-ancestors
    """Dynamic dictionary to gather the required device-specific data from Netbox."""

    def _get_virtual_chassis_members(self) -> Optional[List[Dict[str, Any]]]:
        """Returns a list of devices part of the same virtual chassis or None.

        Returns:
            list: a list of devices.
            None: the device is not part of a virtual chassis.

        """
        if not self._device.metadata['netbox_object'].virtual_chassis:
            return None

        vc_id = self._device.metadata['netbox_object'].virtual_chassis.id
        return [dict(i) for i in self._api.dcim.devices.filter(virtual_chassis_id=vc_id)]


class NetboxInventory:
    """Use Netbox as inventory to gather the list of devices to manage."""

    def __init__(self, api: pynetbox.api, device_roles: Sequence[str], device_statuses: Sequence[str]):
        """Initialize the instance.

        Arguments:
            api (pynetbox.api): the Netbox API instance.
            device_roles (list): a sequence of Netbox device role slug strings to filter the devices.
            device_statuses (list): a sequence of Netbox device status label or value strings to filter the devices.

        """
        self._api = api
        self._device_roles = device_roles
        self._device_statuses = [status.lower() for status in device_statuses]

    def get_devices(self) -> Dict[str, Dict[str, str]]:
        """Return all the devices based on configuration with their role and site.

        Returns:
            dict: a dictionary with the device FQDN as keys and a metadata dictionary as value.

        """
        devices = self._get_devices()
        devices.update(self._get_virtual_chassis_devices())
        return devices

    def _get_virtual_chassis_devices(self) -> Dict[str, Dict[str, str]]:
        """Get the devices part of virtual chassis according to the configuration.

        Returns:
            dict: a dictionary with the device FQDN as keys and a metadata dictionary as value.

        """
        devices = {}  # type: Dict[str, Dict[str, str]]
        for vc in self._api.dcim.virtual_chassis.all():
            device = vc.master
            if not vc.domain:
                logger.error(
                    'Unable to determine hostname for virtual chassis of %s, domain property not set, skipping.',
                    device.name
                )
                continue
            if device.status.value not in self._device_statuses:
                logger.debug('Skipping device %s with status %s', device.name, device.status.label)
                continue
            if device.device_role.slug not in self._device_roles:
                logger.debug('Skipping device %s with role %s', device.name, device.device_role.slug)
                continue

            devices[vc.domain] = NetboxInventory._get_device_data(device)

        return devices

    def _get_devices(self) -> Dict[str, Dict[str, str]]:
        """Get the devices based on role, status and virtual chassis membership.

        Returns:
            dict: a dictionary with the device FQDN as keys and a metadata dictionary as value.

        """
        devices = {}  # type: Dict[str, Dict[str, str]]
        for device in self._api.dcim.devices.filter(
                role=self._device_roles, status=self._device_statuses, virtual_chassis_member=False):
            if device.primary_ip4 is not None and device.primary_ip4.dns_name:
                fqdn = device.primary_ip4.dns_name
            elif device.primary_ip6 is not None and device.primary_ip6.dns_name:
                fqdn = device.primary_ip6.dns_name
            elif device.platform is None:
                logger.debug('Device %s missing FQDN and Platform, assuming non-manageable, skipping.', device.name)
                continue
            else:
                logger.error('Unable to determine FQDN for device %s, skipping.', device.name)
                continue

            devices[fqdn] = NetboxInventory._get_device_data(device)

        return devices

    @staticmethod
    def _get_device_data(device: pynetbox.models.dcim.Devices) -> Dict[str, str]:
        """Return the metadata needed from a Netbox device instance.

        Arguments:
            device (pynetbox.models.dcim.Devices): the Netbox device instance.

        Returns:
            dict: the dictionary with the device metadata.

        """
        metadata = {
            'role': device.device_role.slug,
            'site': device.site.slug,
            'type': device.device_type.slug,
            # Inject the Netbox object too to be future-proof and allow to get additional metadata without
            # the need of modifying homer's code. It also allow to use it inside NetboxData.
            'netbox_object': device,
        }

        # Convert Netbox interfaces into IPs
        if device.primary_ip4 is not None:
            metadata['ip4'] = ipaddress.ip_interface(device.primary_ip4.address).ip.compressed
        if device.primary_ip6 is not None:
            metadata['ip6'] = ipaddress.ip_interface(device.primary_ip6.address).ip.compressed

        return metadata
