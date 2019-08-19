"""Devices module tests."""
from collections import UserDict

from homer.config import load_yaml_config
from homer.devices import Device, Devices
from homer.tests import get_fixture_path


class TestDevices:
    """Devices class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
        self.devices = Devices(load_yaml_config(get_fixture_path('public', 'config', 'devices.yaml')))

    def test_init(self):
        """An instance of Devices should be also an instance of UserDict."""
        assert isinstance(self.devices, Devices)
        assert isinstance(self.devices, UserDict)

    def test_role_existent(self):
        """Should return all devices with a given role."""
        devices = self.devices.role('roleA')
        assert len(devices) == 1
        assert isinstance(devices[0], Device)
        assert devices[0].fqdn == 'device1.example.com'

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
