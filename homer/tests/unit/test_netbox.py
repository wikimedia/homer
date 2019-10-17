"""Netbox module tests."""
from collections import UserDict
from unittest import mock

import pytest

from pynetbox import api

from homer.devices import Device
from homer.netbox import NetboxData, NetboxInventory


def mock_netbox_device(name, role, site, status, ip4=False, ip6=False):
    """Returns a mocked Netbox device object."""
    device = mock.MagicMock()
    device.name = name
    device.device_role.slug = role
    device.site.slug = site
    device.status.value = status

    if ip4:
        device.primary_ip4.dns_name = name
    else:
        device.primary_ip4 = None

    if ip6:
        device.primary_ip6.dns_name = name
    else:
        device.primary_ip6 = None

    return device


def mock_netbox_virtual_chassis(master, domain):
    """Returns a mocked Netbox virtual chassis object."""
    vc = mock.MagicMock()
    vc.master = master
    vc.domain = domain
    return vc


class TestNetboxData:
    """NetboxData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
        self.netbox_api = mock.MagicMock(specset=api)
        self.device = Device('device1.example.com', 'role1', 'site1', {}, {})
        self.netbox_data = NetboxData(self.netbox_api, self.device)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxData)
        assert isinstance(self.netbox_data, UserDict)

    def test_getitem_fail(self):
        """Should raise KeyError if there is no method for that key."""
        with pytest.raises(KeyError, match='key1'):
            self.netbox_data['key1']  # pylint: disable=pointless-statement


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
        assert devices == {d.name: {'site': d.site.slug, 'role': d.device_role.slug} for d in self.selected_devices}
