"""Netbox module tests."""
# pylint: disable=attribute-defined-outside-init
from collections import UserDict
from unittest import mock

import pytest

from pynetbox import api

from homer.devices import Device
from homer.netbox import BaseNetboxData, NetboxData, NetboxDeviceData, NetboxInventory


class NetboxObject:  # pylint: disable=too-many-instance-attributes
    """Helper class to mimic pynetbox objects."""

    def __iter__(self):
        """Allow to convert the object to dict."""
        return iter(vars(self).items())


def mock_netbox_device(name, role, site, status,  # pylint: disable=too-many-arguments,too-many-branches
                       ip4=False, ip6=False, virtual_chassis=False, platform=True):
    """Returns a mocked Netbox device object."""
    device = NetboxObject()
    device.name = name
    device.device_role = NetboxObject()
    device.device_role.slug = role
    device.site = NetboxObject()
    device.site.slug = site
    device.status = NetboxObject()
    device.status.value = status.lower()
    device.status.label = status
    device.device_type = NetboxObject()
    device.device_type.slug = 'typeA'

    if ip4:
        device.primary_ip4 = NetboxObject()
        device.primary_ip4.address = '127.0.0.1/32'
        device.primary_ip4.dns_name = name
    else:
        device.primary_ip4 = None

    if ip6:
        device.primary_ip6 = NetboxObject()
        device.primary_ip6.address = '::1/128'
        device.primary_ip6.dns_name = name
    else:
        device.primary_ip6 = None

    if virtual_chassis:
        device.virtual_chassis = NetboxObject()
        device.virtual_chassis.id = 1  # pylint: disable=invalid-name
    else:
        device.virtual_chassis = None

    if platform:
        device.platform = NetboxObject()
        device.platform.slug = 'osA'
    else:
        device.platform = None

    return device


def mock_netbox_virtual_chassis(master, domain):
    """Returns a mocked Netbox virtual chassis object."""
    vc = NetboxObject()
    vc.master = master
    vc.domain = domain
    return vc


class TestBaseNetboxData:
    """BaseNetboxData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock(specset=api)
        self.netbox_data = BaseNetboxData(self.netbox_api)

    def test_init(self):
        """An instance of BaseNetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, BaseNetboxData)
        assert isinstance(self.netbox_data, UserDict)

    def test_getitem_fail(self):
        """Should raise KeyError if there is no method for that key."""
        with pytest.raises(KeyError, match='key1'):
            self.netbox_data['key1']  # pylint: disable=pointless-statement


class TestNetboxData:
    """NetboxData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock(specset=api)
        self.netbox_data = NetboxData(self.netbox_api)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxData)
        assert isinstance(self.netbox_data, UserDict)

    def test_vlans(self):
        """It should return the defined vlans."""
        vlan = NetboxObject()
        vlan.id = 1
        self.netbox_api.ipam.vlans.all.return_value = [vlan]
        assert self.netbox_data['vlans'] == [{'id': 1}]


class TestNetboxDeviceData:
    """NetboxDeviceData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock(specset=api)
        netbox_device = mock_netbox_device('device1.example.com', 'role1', 'site1', 'Active')
        self.device = Device(netbox_device.name, {'netbox_object': netbox_device}, {}, {})
        self.netbox_data = NetboxDeviceData(self.netbox_api, self.device)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxDeviceData)
        assert isinstance(self.netbox_data, UserDict)

    def test_cached_key(self):
        """If a key has been already populated it should not call the method again."""

    def test_get_virtual_chassis_members_no_members(self):
        """If a device is not part of a virtual chassis it should return None."""
        assert self.netbox_data['virtual_chassis_members'] is None

    def test_get_virtual_chassis_members_with_members(self):
        """If a device is part of a virtual chassis it should return its members."""
        netbox_devices = []
        devices = []
        names = ('device1.example.com', 'device2.example.com')
        for name in names:
            netbox_device = mock_netbox_device(name, 'role1', 'site1', 'Active', virtual_chassis=True)
            netbox_devices.append(netbox_device)
            devices.append(Device(netbox_device.name, {'netbox_object': netbox_device}, {}, {}))

        self.netbox_api.dcim.devices.filter.return_value = netbox_devices

        netbox_data = NetboxDeviceData(self.netbox_api, devices[0])
        for _ in range(2):
            assert [d['name'] for d in netbox_data['virtual_chassis_members']] == list(names)

        # Ensure the data was cached and the API was called only once.
        assert self.netbox_api.dcim.devices.filter.call_count == 1


class TestNetboxInventory:
    """NetboxInventory class tests."""

    def setup_method(self):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        selected_devices = [
            mock_netbox_device('device1', 'roleA', 'siteA', 'Active', ip4=True),
            mock_netbox_device('device2', 'roleA', 'siteA', 'Staged', ip6=True),
        ]
        selected_vcs = [
            mock_netbox_device('device1-vc1', 'roleA', 'siteA', 'Active'),
        ]
        filtered_devices = [
            mock_netbox_device('device3', 'roleB', 'siteB', 'Active'),
            mock_netbox_device('device4', 'roleA', 'siteA', 'Active'),
            mock_netbox_device('device2', 'roleA', 'siteA', 'Staged', platform=False),
        ]
        filtered_vcs = [
            mock_netbox_device('device1-vc2', 'roleB', 'siteA', 'Active'),
            mock_netbox_device('device1-vc3', 'roleA', 'siteA', 'Decommissioning'),
            mock_netbox_device('', 'roleA', 'siteA', 'Active'),
        ]
        self.selected_devices = selected_devices + selected_vcs
        virtual_chassis = [mock_netbox_virtual_chassis(device, device.name) for device in selected_vcs + filtered_vcs]
        self.mocked_api = mock.MagicMock()
        self.mocked_api.dcim.virtual_chassis.all.return_value = virtual_chassis
        self.mocked_api.dcim.devices.filter.return_value = selected_devices + filtered_devices
        self.inventory = NetboxInventory(self.mocked_api, ['roleA'], ['Active', 'Staged'])

    def test_get_devices(self):
        """It should get the devices without inspecting virtual chassis."""
        devices = self.inventory.get_devices()
        expected = {}
        for device in self.selected_devices:
            expected_device = {'site': device.site.slug, 'role': device.device_role.slug, 'type': 'typeA',
                               'netbox_object': device}
            if device.primary_ip4 is not None:
                expected_device['ip4'] = '127.0.0.1'
            if device.primary_ip6 is not None:
                expected_device['ip6'] = '::1'

            expected[device.name] = expected_device

        assert devices == expected
