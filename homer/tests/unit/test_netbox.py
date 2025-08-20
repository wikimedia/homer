"""Netbox module tests."""
# pylint: disable=attribute-defined-outside-init
import json

from collections import UserDict
from pathlib import Path
from unittest import mock

import pytest
import requests

from homer import netbox
from homer.devices import Device
from homer.exceptions import HomerError
from homer.tests import get_fixture_path
from homer.tests.unit.test_init import setup_tmp_path


class NetboxObject:  # pylint: disable=too-many-instance-attributes
    """Helper class to mimic pynetbox objects."""

    def __iter__(self):
        """Allow to convert the object to dict."""
        return iter(vars(self).items())


class NetboxDataGql(netbox.NetboxData):
    """Extends the NetboxData class to add a GQL query."""

    def gql(self, query, variables):
        """It returns data from executing a gql query."""
        return self._gql_execute(query, variables)


class NetboxDeviceDataGql(netbox.NetboxDeviceData):
    """Extends the NetboxDeviceData class to add a GQL query."""

    def gql(self, query, variables):
        """It returns data from executing a gql query."""
        return self._gql_execute(query, variables)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def mock_netbox_device(name, role, site, status, ip4=False, ip6=False, virtual_chassis=False, platform=True):
    """Returns a mocked Netbox device object."""
    device = NetboxObject()
    device.id = 123  # pylint: disable=invalid-name
    device.name = name
    device.role = NetboxObject()
    device.role.slug = role
    device.site = NetboxObject()
    device.site.slug = site
    device.status = NetboxObject()
    device.status.value = status.lower()
    device.device_type = NetboxObject()
    device.device_type.slug = 'typeA'
    device.device_type.manufacturer = NetboxObject()
    device.device_type.manufacturer.slug = 'manufacturerA'

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

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.output, self.config = setup_tmp_path('config-netbox.yaml', tmp_path)
        self.netbox_data = netbox.BaseNetboxData(self.netbox_api, self.config['base_paths'])

        def key_raise():
            raise RuntimeError('key raise')

        self.netbox_data._get_key_raise = key_raise  # pylint: disable=protected-access

    def test_init(self):
        """An instance of BaseNetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, netbox.BaseNetboxData)
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

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path, requests_mock):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.netbox_api.base_url = 'http://localhost/api'
        self.netbox_api.http_session = requests.Session()
        self.output, self.config = setup_tmp_path('config-netbox.yaml', tmp_path)
        self.netbox_data = NetboxDataGql(self.netbox_api, self.config['base_paths'])
        self.requests_mock = requests_mock

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, netbox.NetboxData)
        assert isinstance(self.netbox_data, UserDict)

    def test_vlans(self):
        """It should return the defined vlans."""
        vlan = NetboxObject()
        vlan.id = 1
        self.netbox_api.ipam.vlans.all.return_value = [vlan]
        assert self.netbox_data['vlans'] == [{'id': 1}]

    @pytest.mark.parametrize('variables', (None, {}))
    def test_gql(self, variables):
        """It should load the graphql query from the file and execute it."""
        adapter = self.requests_mock.post('http://localhost/graphql/', json={'data': {'key': 'value'}})
        assert self.netbox_data.gql('query', variables) == {'key': 'value'}

        assert adapter.call_count == 1
        request = adapter.last_request.json()
        assert request['query'] == 'query () {\n    device_list() {\n        name\n    }\n}\n'
        if variables is not None:
            assert request['variables'] == variables
        else:
            assert 'variables' not in request


class TestNetboxDeviceData:
    """NetboxDeviceData class tests."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path, requests_mock):
        """Initialize the test instances."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.netbox_api.base_url = 'http://localhost/api'
        self.netbox_api.http_session = requests.Session()
        netbox_device = mock_netbox_device('device1.example.com', 'role1', 'site1', 'Active')
        self.netbox_api.dcim.devices.get.return_value = netbox_device
        self.device = Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {})
        self.output, self.config = setup_tmp_path('config-netbox.yaml', tmp_path)
        self.netbox_data = NetboxDeviceDataGql(self.netbox_api, self.config['base_paths'], self.device)
        self.requests_mock = requests_mock
        self.iface_1 = {'name': 'int1', 'link_peers':
                        [{'__typename': 'CircuitTerminationType', 'circuit': {'id': '1'}}]}
        self.iface_2 = {'name': 'int2', 'link_peers': [{'__typename': 'FrontPortType', 'rear_port': {
            'name': 'int1', 'link_peers': [{'__typename': 'CircuitTerminationType', 'circuit': {'id': '1'}}]}}]}
        self.iface_3 = {'name': 'int1', 'link_peers': [{'__typename': 'InterfaceType'}]}

    def test_init(self):
        """An instance of NetboxData should be also an instance of UserDict."""
        assert isinstance(self.netbox_data, netbox.NetboxDeviceData)
        assert isinstance(self.netbox_data, UserDict)

    @pytest.mark.parametrize('variables', (None, {}, {'key1': 'value1'}))
    @pytest.mark.parametrize('virtual_chassis', (False, True))
    def test_gql(self, virtual_chassis, variables):
        """It should run a gql query with the given variables in addition to the default ones."""
        adapter = self.requests_mock.post('http://localhost/graphql/', json={'data': {'key': 'value'}})

        expected_variables = {'device_id': '123'}
        if virtual_chassis:
            netbox_device = mock_netbox_device('device1.example.com', 'role1', 'site1', 'Active', virtual_chassis=True)
            self.netbox_api.dcim.devices.get.return_value = netbox_device
            device = Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {})
            netbox_data = NetboxDeviceDataGql(self.netbox_api, self.config['base_paths'], device)
            expected_variables['virtual_chassis_id'] = '1'
        else:
            netbox_data = self.netbox_data

        if variables:
            expected_variables.update(variables)

        assert netbox_data.gql('query', variables) == {'key': 'value'}

        assert adapter.call_count == 1
        request = adapter.last_request.json()
        assert request['query'] == 'query () {\n    device_list() {\n        name\n    }\n}\n'
        assert request['variables'] == expected_variables

    @pytest.mark.parametrize('virtual_chassis', (False, True))
    def test_fetch_device_interfaces_uncached(self, virtual_chassis):
        """It should gather the interfaces and return them."""
        netbox_device = mock_netbox_device(
            'device1.example.com', 'role1', 'site1', 'Active', virtual_chassis=virtual_chassis)
        self.netbox_api.dcim.devices.get.return_value = netbox_device
        device = Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {})
        netbox_data = NetboxDeviceDataGql(self.netbox_api, self.config['base_paths'], device)
        gql_data = {'data': {'interface_list': [self.iface_1, self.iface_2, self.iface_3]}}
        self.requests_mock.register_uri('post', 'http://localhost/graphql/', json=gql_data)

        assert netbox_data.fetch_device_interfaces() == [self.iface_1, self.iface_2, self.iface_3]

    def test_fetch_device_interfaces_cached(self):
        """It should gather the interfaces and return them."""
        gql_data = {'data': {'interface_list': [self.iface_1, self.iface_2, self.iface_3]}}
        self.requests_mock.register_uri('post', 'http://localhost/graphql/', json=gql_data)
        assert self.netbox_data.fetch_device_interfaces() == [self.iface_1, self.iface_2, self.iface_3]
        assert self.requests_mock.called
        self.requests_mock.reset_mock()
        assert self.netbox_data.fetch_device_interfaces() == [self.iface_1, self.iface_2, self.iface_3]
        assert not self.requests_mock.called

    def test_get_virtual_chassis_members_no_virtual_chassis(self):
        """If a device is not part of a virtual chassis it should return None."""
        assert self.netbox_data['virtual_chassis_members'] is None

    def test_get_virtual_chassis_members_no_members(self):
        """If a device is part of a virtual chassis without members it should return empty list."""
        netbox_device = mock_netbox_device('device1.example.com', 'role1', 'site1', 'Active', virtual_chassis=True)
        device = Device(netbox_device.name, {'netbox_object': netbox_device, 'id': 123}, {}, {})
        self.netbox_api.dcim.devices.get.return_value = netbox_device
        netbox_data = netbox.NetboxDeviceData(self.netbox_api, self.config['base_paths'], device)
        assert netbox_data['virtual_chassis_members'] == []

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
        self.netbox_api.dcim.devices.get.return_value = netbox_devices[0]

        netbox_data = netbox.NetboxDeviceData(self.netbox_api, self.config['base_paths'], devices[0])
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
        gql_data = {'data': {'interface_list': [self.iface_1, self.iface_2, self.iface_3]}}
        self.requests_mock.register_uri('post', 'http://localhost/graphql/', json=gql_data)
        self.netbox_api.circuits.circuits.get.return_value = {}

        assert self.netbox_data['circuits'] == {'int1': {}, 'int2': {}}
        calls = [mock.call(1), mock.call(1)]
        self.netbox_api.circuits.circuits.get.assert_has_calls(calls)

    def test_get_vlans(self):
        """It should return the vlans defined on a device's interfaces."""
        interface_list = json.loads(
            Path(get_fixture_path('netbox', 'interface_list.json')).read_text(encoding='UTF-8')
        )
        self.requests_mock.register_uri('post', 'http://localhost/graphql/', json=interface_list)

        irb_vlan = NetboxObject()
        irb_vlan.vid = 2004
        irb_vlan.name = "public1-d-codfw"
        self.netbox_api.ipam.vlans.get.return_value = irb_vlan

        # We want the function with the fake inbound data to match the one untagged and tagged vlans
        assert self.netbox_data['vlans'] == {2020: {'name': 'private1-d-codfw', 'vid': 2020},
                                             2004: {'name': 'public1-d-codfw', 'vid': 2004},
                                             401: {'name': 'XLink1', 'vid': 401},
                                             1201: {'name': 'public1-ulsfo', 'vid': 1201}
                                             }

    def test_get_vlans_missing_irb(self):
        """It should return the vlans defined on a device's interfaces."""
        interface_list = json.loads(
            Path(get_fixture_path('netbox', 'interface_list.json')).read_text(encoding='UTF-8')
        )
        self.requests_mock.register_uri('post', 'http://localhost/graphql/', json=interface_list)

        with pytest.raises(HomerError, match='Failed to get key vlans') as excinfo:
            self.netbox_data['vlans']  # pylint: disable=pointless-statement

        original_exception = excinfo.value.__cause__
        assert isinstance(original_exception, HomerError)
        assert str(original_exception) == "IRB interface irb.2004 does not match any Vlan in Netbox"


class TestNetboxInventory:
    """NetboxInventory class tests."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.netbox_api.base_url = 'http://localhost/api'
        self.netbox_api.http_session = requests.Session()

        # pylint: disable=attribute-defined-outside-init
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
        self.inventory = netbox.NetboxInventory(self.netbox_api, ['roleA'], ['Active', 'Staged'])

    def test_get_devices_ok(self):
        """It should get the devices without inspecting virtual chassis."""
        device_list = json.loads(
            Path(get_fixture_path('netbox', 'device_list.json')).read_text(encoding='UTF-8')
        )
        adapter = self.requests_mock.post('http://localhost/graphql/', json=device_list)
        devices = self.inventory.get_devices()
        expected = {}
        for device in self.selected_devices:
            fqdn = ""
            expected_device = {'site': device.site.slug, 'role': device.role.slug,
                               'type': device.device_type.slug, 'status': device.status.value,
                               'manufacturer': device.device_type.manufacturer.slug, 'id': device.id}
            if device.primary_ip4 is not None:
                expected_device['ip4'] = '192.0.2.42'
                fqdn = device.primary_ip4.dns_name
            if device.primary_ip6 is not None:
                expected_device['ip6'] = '2001:db8::42'
                fqdn = device.primary_ip6.dns_name

            expected[fqdn] = expected_device

        assert devices == expected
        assert adapter.call_count == 1


class TestGQLExecute:
    """Test class for the gql_execute function."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        self.netbox_api = mock.MagicMock()  # Can't use spec_set because of pynetbox lazy creation
        self.netbox_api.base_url = 'http://localhost/api'
        self.netbox_api.http_session = requests.Session()
        self.requests_mock = requests_mock

    def test_gql_execute_requests_raise(self):
        """In case the request fails it should raise a HomerError."""
        adapter = self.requests_mock.post('http://localhost/graphql/', exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(HomerError, match='failed to fetch netbox data'):
            netbox.gql_execute(self.netbox_api, 'query')

        assert adapter.call_count == 1

    def test_gql_execute_no_data(self):
        """In case the request returns no data it should raise a HomerError."""
        adapter = self.requests_mock.post('http://localhost/graphql/', json={})
        with pytest.raises(HomerError, match='No data found in GraphQL response'):
            netbox.gql_execute(self.netbox_api, 'query')

        assert adapter.call_count == 1
