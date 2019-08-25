"""Devices module tests."""
from collections import UserDict

import pytest

from homer.config import load_yaml_config
from homer.devices import Device, Devices
from homer.exceptions import HomerError
from homer.tests import get_fixture_path


class TestDevices:
    """Devices class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
        self.devices = Devices(load_yaml_config(get_fixture_path('public', 'config', 'devices.yaml')), {})
        self.devices_with_private = Devices(
            load_yaml_config(get_fixture_path('public', 'config', 'devices.yaml')),
            load_yaml_config(get_fixture_path('private', 'config', 'devices.yaml')))

    def test_init(self):
        """An instance of Devices should be also an instance of UserDict."""
        assert isinstance(self.devices, Devices)
        assert isinstance(self.devices, UserDict)

    def test_role_existent(self):
        """Should return all devices with a given role."""
        devices = self.devices.role('roleA')
        assert len(devices) == 2
        for device in devices:
            assert isinstance(device, Device)
        assert sorted([device.fqdn for device in devices]) == ['another.example.com', 'device1.example.com']

    def test_role_non_existent(self):
        """Should return an empty list if no device has that role."""
        assert self.devices.role('non_existent') == []

    def test_site_existent(self):
        """Should return all devices in a given site."""
        devices = self.devices.site('siteA')
        assert len(devices) == 1
        assert isinstance(devices[0], Device)
        assert devices[0].fqdn == 'device1.example.com'

    def test_site_non_existent(self):
        """Should return an empty list if no device belong to that site."""
        assert self.devices.site('non_existent') == []

    def test_dict_access(self):
        """Should return the device with the given FQDN."""
        device = self.devices['device1.example.com']
        assert isinstance(device, Device)

    def test_private_config(self):
        """Should include the device-specific private config only when set."""
        assert self.devices['device1.example.com'].private == {}
        assert self.devices_with_private['device1.example.com'].private['device_private_key'] == 'device_private_value'

    def test_query_role(self):
        """Should return all the devices with a given role."""
        devices = self.devices.query('role:roleA')
        assert len(devices) == 2
        for device in devices:
            assert isinstance(device, Device)
        assert sorted([device.fqdn for device in devices]) == ['another.example.com', 'device1.example.com']

    def test_query_role_single(self):
        """Should return all the devices with a given role, testing one device match."""
        devices = self.devices.query('role:roleB')
        assert len(devices) == 1
        assert isinstance(devices[0], Device)
        assert devices[0].fqdn == 'device2.example.com'

    def test_query_role_no_match(self):
        """Should return an empty list if no device has that role."""
        devices = self.devices.query('role:non-existent')
        assert devices == []

    def test_query_site(self):
        """Should return all the devices in a given site."""
        devices = self.devices.query('site:siteB')
        assert len(devices) == 2
        for device in devices:
            assert isinstance(device, Device)
        assert sorted([device.fqdn for device in devices]) == ['another.example.com', 'device2.example.com']

    def test_query_site_no_match(self):
        """Should return an empty list if no device is in that site."""
        devices = self.devices.query('site:non-existent')
        assert devices == []

    def test_query_fqdn(self):
        """Should return the matching device."""
        devices = self.devices.query('device1.example.com')
        assert len(devices) == 1
        assert isinstance(devices[0], Device)
        assert devices[0].fqdn == 'device1.example.com'

    def test_query_fqdn_no_match(self):
        """Should return an empty list if not match."""
        devices = self.devices.query('non-existent.example.com')
        assert devices == []

    def test_query_fqdn_globbing(self):
        """Should return the matching devices."""
        devices = self.devices.query('device*.*.com')
        assert len(devices) == 2
        assert sorted([device.fqdn for device in devices]) == ['device1.example.com', 'device2.example.com']

    def test_query_invalid(self):
        """Should raise HomerError if the query syntax is invalid."""
        with pytest.raises(HomerError, match='Unknown query prefix: invalid'):
            self.devices.query('invalid:foo')
