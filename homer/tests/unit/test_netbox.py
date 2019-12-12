"""Netbox module tests."""
from collections import UserDict
from unittest import mock

import pytest

from pynetbox import api

from homer.devices import Device
from homer.netbox import BaseNetboxData, NetboxData, NetboxDeviceData, NetboxInventory


def mock_netbox_device(name, role, site, status, ip4=False, ip6=False):
    """Returns a mocked Netbox device object."""
    device = mock.MagicMock()
    device.name = name
    device.device_role.slug = role
    device.site.slug = site
    device.status.value = status
    device.device_type.slug = 'typeA'

    if ip4:
        device.primary_ip4.address = '127.0.0.1/32'
        device.primary_ip4.dns_name = name
    else:
        device.primary_ip4 = None

    if ip6:
        device.primary_ip6.address = '::1/128'
        device.primary_ip6.dns_name = name
    else:
        device.primary_ip6 = None

    def _deepcopy(_):
        raise TypeError('Mocked device does not support deepcopy')

    device.__deepcopy__ = _deepcopy

    return device


def mock_netbox_virtual_chassis(master, domain):
    """Returns a mocked Netbox virtual chassis object."""
    vc = mock.MagicMock()
    vc.master = master
    vc.domain = domain
    return vc


class TestBaseNetboxData:
    """BaseNetboxData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
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
        # pylint: disable=attribute-defined-outside-init
        self.netbox_api = mock.MagicMock(specset=api)
        self.netbox_data = NetboxData(self.netbox_api)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxData)
        assert isinstance(self.netbox_data, UserDict)


class TestNetboxDeviceData:
    """NetboxDeviceData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
        self.netbox_api = mock.MagicMock(specset=api)
        self.device = Device('device1.example.com', {'role': 'role1', 'site': 'site1'}, {}, {})
        self.netbox_data = NetboxDeviceData(self.netbox_api, self.device)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxDeviceData)
        assert isinstance(self.netbox_data, UserDict)


class TestNetboxInventory:
    """NetboxInventory class tests."""

    def setup_method(self):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        selected_devices = [
            mock_netbox_device('device1', 'roleA', 'siteA', 1, ip4=True),
            mock_netbox_device('device2', 'roleA', 'siteA', 3, ip6=True),
        ]
        selected_vcs = [
            mock_netbox_device('device1-vc1', 'roleA', 'siteA', 1),
        ]
        filtered_devices = [
            mock_netbox_device('device3', 'roleB', 'siteB', 1),
            mock_netbox_device('device4', 'roleA', 'siteA', 1),
        ]
        filtered_vcs = [
            mock_netbox_device('device1-vc2', 'roleB', 'siteA', 1),
            mock_netbox_device('device1-vc3', 'roleA', 'siteA', 9),
        ]
        self.selected_devices = selected_devices + selected_vcs
        virtual_chassis = [mock_netbox_virtual_chassis(device, device.name) for device in selected_vcs + filtered_vcs]
        self.mocked_api = mock.MagicMock()
        self.mocked_api.dcim.virtual_chassis.all.return_value = virtual_chassis
        self.mocked_api.dcim.devices.filter.return_value = selected_devices + filtered_devices
        self.mocked_api.dcim.choices.return_value = {'device:status': [
            {'label': 'Active', 'value': 1}, {'label': 'Staged', 'value': 3}]}
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
