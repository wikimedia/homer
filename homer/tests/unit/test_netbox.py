"""Netbox module tests."""
# pylint: disable=attribute-defined-outside-init
import json

from collections import UserDict
from pathlib import Path
from unittest import mock

import pytest

from homer.config import load_yaml_config
from homer.devices import Device
from homer.exceptions import HomerError
from homer.netbox import BaseNetboxData, NetboxData, NetboxDeviceData, NetboxInventory
from homer.tests import get_fixture_path


class NetboxObject:  # pylint: disable=too-many-instance-attributes
    """Helper class to mimic pynetbox objects."""

    def __iter__(self):
        """Allow to convert the object to dict."""
        return iter(vars(self).items())


# Disablint pylint useless-suppression because it would fire for the too-many-branches check, if removing that one too
# it will fire because of too-many-branches. Unable to reproduce in isolation quickly.
def mock_netbox_device(name, role, site,  # pylint: disable=too-many-arguments,too-many-branches,useless-suppression
                       status, ip4=False, ip6=False, virtual_chassis=False, platform=True):
    """Returns a mocked Netbox device object."""
    device = NetboxObject()
    device.id = 123  # pylint: disable=invalid-name
    device.name = name
    device.device_role = NetboxObject()
    device.device_role.slug = role
    device.site = NetboxObject()
    device.site.slug = site
    device.status = NetboxObject()
    device.status.value = status.lower()
    device.device_type = NetboxObject()
    device.device_type.slug = 'typeA'

    if ip4:
        device.primary_ip4 = NetboxObject()
        device.primary_ip4.dns_name = f"{name}.example.com"
    else:
        device.primary_ip4 = None

    if ip6:
        device.primary_ip6 = NetboxObject()
        device.primary_ip6.dns_name = f"{name}.example.com"
    else:
        device.primary_ip6 = None

    if virtual_chassis:
        device.virtual_chassis = NetboxObject()
        device.virtual_chassis.id = 1
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
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.netbox_data = BaseNetboxData(self.netbox_api)

        def key_raise():
            raise RuntimeError('key raise')

        self.netbox_data._get_key_raise = key_raise  # pylint: disable=protected-access

    def test_init(self):
        """An instance of BaseNetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, BaseNetboxData)
        assert isinstance(self.netbox_data, UserDict)

    def test_getitem_fail(self):
        """Should raise KeyError if there is no method for that key."""
        with pytest.raises(KeyError, match='key1'):
            self.netbox_data['key1']  # pylint: disable=pointless-statement

    def test_getitem_raise(self):
        """Should raise HomerError if the call to the key raise any exception."""
        with pytest.raises(HomerError, match='Failed to get key key_raise'):
            self.netbox_data['key_raise']  # pylint: disable=pointless-statement


class TestNetboxData:
    """NetboxData class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
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
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        netbox_device = mock_netbox_device('device1.example.com', 'role1', 'site1', 'Active')
        self.device = Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {})
        self.netbox_data = NetboxDeviceData(self.netbox_api, self.device)

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, NetboxDeviceData)
        assert isinstance(self.netbox_data, UserDict)

    def test_cached_key(self):
        """If a key has been already populated it should not call the method again."""

    def test_get_virtual_chassis_members_no_members(self):
        """If a device is not part of a virtual chassis it should return None."""
        assert len(self.netbox_data['virtual_chassis_members']) == 0

    def test_get_virtual_chassis_members_with_members(self):
        """If a device is part of a virtual chassis it should return its members."""
        netbox_devices = []
        devices = []
        names = ('device1.example.com', 'device2.example.com')
        for name in names:
            netbox_device = mock_netbox_device(name, 'role1', 'site1', 'Active', virtual_chassis=True)
            netbox_devices.append(netbox_device)
            devices.append(Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {}))

        self.netbox_api.dcim.devices.filter.return_value = netbox_devices

        netbox_data = NetboxDeviceData(self.netbox_api, devices[0])
        # Call multiple times so that we can check the results are cached
        for _ in range(2):
            assert [d['name'] for d in netbox_data['virtual_chassis_members']] == list(names)

        # Ensure the data was cached and the API was called only once.
        assert self.netbox_api.dcim.devices.filter.call_count == 1

    def test_get_inventory(self):
        """It should return all the inventory items of a device."""
        netbox_object = NetboxObject()
        netbox_object.item = 'inventory item'
        self.netbox_api.dcim.inventory_items.filter.return_value = [netbox_object]

        assert self.netbox_data['inventory'] == [{'item': netbox_object.item}]
        self.netbox_api.dcim.inventory_items.filter.assert_called_once()

    def test_get_circuits(self):
        """It should return all the circuits connected to a device."""
        interface_1 = NetboxObject()
        interface_1.link_peer_type = 'circuits.circuittermination'
        interface_1.name = 'int1'
        interface_1.link_peer = NetboxObject()
        interface_1.link_peer.circuit = NetboxObject()
        interface_1.link_peer.circuit.id = 1

        interface_2 = NetboxObject()
        interface_2.name = 'int2'
        interface_2.link_peer_type = 'dcim.frontport'
        interface_2.link_peer = NetboxObject()
        interface_2.link_peer.rear_port = interface_1

        interface_3 = NetboxObject()
        interface_3.link_peer_type = 'dcim.interface'

        self.netbox_api.circuits.circuits.get.return_value = {}
        self.netbox_api.dcim.interfaces.filter.return_value = [interface_1, interface_2, interface_3]

        assert self.netbox_data['circuits'] == {'int1': {}, 'int2': {}}
        self.netbox_api.dcim.interfaces.filter.assert_called_once()
        calls = [mock.call(1), mock.call(1)]
        self.netbox_api.circuits.circuits.get.assert_has_calls(calls)

    def test_get_vlans(self):
        """It should return the vlans defined on a device's interfaces."""
        interface1 = NetboxObject()  # This is a fake interface object
        interface1.untagged_vlan = NetboxObject()  # That interface have fake tagged and untagged vlans
        interface1.untagged_vlan.vid = 666
        interface1.tagged_vlans = [NetboxObject(), NetboxObject()]
        interface1.tagged_vlans[0].vid = 667
        interface1.tagged_vlans[1].vid = 667
        interface2 = NetboxObject()  # This is a fake interface object
        interface2.untagged_vlan = NetboxObject()  # That interface have fake tagged and untagged vlans
        interface2.untagged_vlan.vid = 666
        interface2.tagged_vlans = None
        self.netbox_api.dcim.interfaces.filter.return_value = [interface1, interface2]
        # We want the function with the fake inbound data to match the one untagged and tagged vlans
        assert self.netbox_data['vlans'] == {666: interface1.untagged_vlan, 667: interface1.tagged_vlans[0]}

        # And we want the fake API to be called only once
        self.netbox_api.dcim.interfaces.filter.assert_called_once()


class TestNetboxInventory:
    """NetboxInventory class tests."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        config = load_yaml_config(get_fixture_path('cli', 'config-netbox.yaml'))
        selected_devices = [
            mock_netbox_device('device1', 'roleA', 'siteA', 'Active', ip4=True),
            mock_netbox_device('device2', 'roleA', 'siteA', 'Staged', ip6=True),
        ]
        selected_vcs = [
            mock_netbox_device('device1-vc1', 'roleA', 'siteA', 'Active', ip4=True),
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
        self.requests_mock = requests_mock
        self.inventory = NetboxInventory(config['netbox'], ['roleA'], ['Active', 'Staged'])

    def test_get_devices(self):
        """It should get the devices without inspecting virtual chassis."""
        device_list = json.loads(
            Path(get_fixture_path('netbox', 'device_list.json')).read_text(encoding="UTF-8")
        )
        self.requests_mock.post('/graphql/', json=device_list)  # nosec
        devices = self.inventory.get_devices()
        expected = {}
        for device in self.selected_devices:
            expected_device = {'site': device.site.slug, 'role': device.device_role.slug,
                               'type': device.device_type.slug, 'status': device.status.value, 'id': device.id}
            if device.primary_ip4 is not None:
                expected_device['ip4'] = '192.0.2.42'
                fqdn = device.primary_ip4.dns_name
            if device.primary_ip6 is not None:
                expected_device['ip6'] = '2001:db8::42'
                fqdn = device.primary_ip6.dns_name

            expected[fqdn] = expected_device

        assert devices == expected
