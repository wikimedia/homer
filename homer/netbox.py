"""Netbox module."""
import ipaddress
import logging

from collections import UserDict
from typing import Any, Dict, List, Optional, Sequence

import pynetbox

from homer.devices import Device
from homer.exceptions import HomerError


logger = logging.getLogger(__name__)


class BaseNetboxData(UserDict):
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
        method_name = f'_get_{key}'
        if not hasattr(self, method_name):
            raise KeyError(key)

        if key not in self.data:
            try:
                self.data[key] = getattr(self, method_name)()
            except Exception as e:
                raise HomerError(f'Failed to get key {key}') from e

        return self.data[key]


class BaseNetboxDeviceData(BaseNetboxData):
    """Base class to gather device-specific data dynamically from Netbox."""

    def __init__(self, api: pynetbox.api, device: Device):
        """Initialize the dictionary.

        Arguments:
            api (pynetbox.api): the Netbox API instance.
            device (homer.devices.Device): the device for which to gather the data.

        """
        super().__init__(api)
        self._device = device


class NetboxData(BaseNetboxData):
    """Dynamic dictionary to gather the required generic data from Netbox."""

    def _get_vlans(self) -> List[Dict[str, Any]]:
        """Returns all the vlans defined in Netbox.

        Returns:
            list: a list of vlans.

        """
        return [dict(i) for i in self._api.ipam.vlans.all()]


class NetboxDeviceData(BaseNetboxDeviceData):
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

    def _get_circuits(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Returns a list of circuits connected to the device.

        Returns:
            list: A list of circuits.

        """
        device_id = self._device.metadata['netbox_object'].id
        circuits = {}
        for a_int in self._api.dcim.interfaces.filter(device_id=device_id):
            # b_int is either the patch panel interface facing out or the initial interface
            # if no patch panel
            if a_int.link_peer_type == 'dcim.frontport' and a_int.link_peer.rear_port:
                b_int = a_int.link_peer.rear_port
            else:
                # If the patch panel isn't patched through
                b_int = a_int
            if b_int.link_peer_type == 'circuits.circuittermination':
                circuits[a_int.name] = dict(self._api.circuits.circuits.get(b_int.link_peer.circuit.id))

        return circuits

    def _get_inventory(self) -> Optional[List[Dict[Any, Any]]]:
        """Returns the list of inventory items on the device.

        Returns:
            list: A list of inventory items.

        """
        device_id = self._device.metadata['netbox_object'].id
        return [dict(i) for i in self._api.dcim.inventory_items.filter(device_id=device_id)]

    def _get_vlans(self) -> Dict[int, Any]:
        """Returns all the vlans defined on a device.

        Returns:
            dict: a dict of vlans.

        """
        vlans = {}
        device_id = self._device.metadata['netbox_object'].id

        for interface in self._api.dcim.interfaces.filter(device_id=device_id):
            if interface.untagged_vlan and interface.untagged_vlan.vid not in vlans:
                vlans[interface.untagged_vlan.vid] = interface.untagged_vlan
            if interface.tagged_vlans:
                for tagged_vlan in interface.tagged_vlans:
                    if tagged_vlan.vid not in vlans:
                        vlans[tagged_vlan.vid] = tagged_vlan
        return vlans


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
        devices: Dict[str, Dict[str, str]] = {}
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
        devices: Dict[str, Dict[str, str]] = {}
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
            'status': device.status.value,
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
