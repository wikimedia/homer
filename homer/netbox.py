"""Netbox module."""
import ipaddress
import logging

from collections import UserDict
from typing import Any, Dict, List, Sequence

import pynetbox

from homer.devices import Device


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class NetboxData(UserDict):  # pylint: disable=too-many-ancestors
    """Dynamic dictionary to gather the required data from Netbox."""

    def __init__(self, api: pynetbox.api, device: Device):
        """Initialize the dictionary.

        Parameters:
            api (pynetbox.api): the Netbox API instance.
            device (homer.devices.Device): the device for which to gather the data.

        """
        super().__init__()
        self._api = api
        self._device = device

    def __getitem__(self, key: Any) -> Any:
        """Dynamically call the related method, if exists, to return the requested data.

        Parameters:
            According to Python's datamodel, see:
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


class NetboxInventory:
    """Use Netbox as inventory to gather the list of devices to manage."""

    def __init__(self, api: pynetbox.api, device_roles: Sequence[str], device_statuses: Sequence[str]):
        """Initialize the instance.

        Parameters:
            api (pynetbox.api): the Netbox API instance.
            device_roles (list): a sequence of Netbox device role slug strings to filter the devices.
            device_statuses (list): a sequence of Netbox device status label strings to filter the devices.

        """
        self._api = api
        self._device_roles = device_roles
        self._device_statuses = self._get_statuses_ids(device_statuses)

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
            else:
                logger.error('Unable to determine FQDN for device %s, skipping.', device.name)
                continue

            devices[fqdn] = NetboxInventory._get_device_data(device)

        return devices

    def _get_statuses_ids(self, labels: Sequence[str]) -> List[int]:
        """Convert a sequence of Netbox status labels into their IDs.

        Parameters:
            labels (list): a list of strings with the status labels.

        Returns:
            list: a list with the integer IDs corresponding to the status labels.

        """
        choices = {choice['label']: choice['value'] for choice in self._api.dcim.choices()['device:status']}
        return [value for label, value in choices.items() if label in labels]

    @staticmethod
    def _get_device_data(device: pynetbox.models.dcim.Devices) -> Dict[str, str]:
        """Return the metadata needed from a Netbox device instance.

        Parameters:
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
