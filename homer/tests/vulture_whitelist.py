"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist_tests = Whitelist()
whitelist_tests.unit.test_devices.TestDevices.setup_method
whitelist_tests.unit.test_devices.TestDevices.setup_method_fixture
whitelist_tests.unit.test_config.test_uncopiable_object.Uncopiable.__deepcopy__
whitelist_tests.fixtures.plugins.plugin.NetboxDeviceDataPlugin._get_netbox_device_plugin

whitelist_cli = Whitelist()
whitelist_cli.argument_parser.subparsers.required

whitelist_netbox = Whitelist()
whitelist_netbox.NetboxData._get_vlans
whitelist_netbox.NetboxDeviceData._get_virtual_chassis_members

# Needed for vulture < 0.27
whitelist_mock = Whitelist()
whitelist_mock.return_value
whitelist_mock.side_effect
