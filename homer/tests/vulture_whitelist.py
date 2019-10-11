"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist_tests = Whitelist()
whitelist_tests.unit.test_devices.TestDevices.setup_method
whitelist_tests.unit.test_devices.TestDevices.setup_method_fixture

whitelist_cli = Whitelist()
whitelist_cli.argument_parser.subparsers.required

# TODO: remove once the first concrete implementation uses self._api
whitelist_netbox = Whitelist()
whitelist_netbox.NetboxData._api

# Needed for vulture < 0.27
whitelist_mock = Whitelist()
whitelist_mock.return_value
whitelist_mock.side_effect
