"""Custom plugin module."""
from homer.netbox import BaseNetboxDeviceData


class NetboxDeviceDataPlugin(BaseNetboxDeviceData):  # pylint: disable=too-many-ancestors
    """Custom class to mangle device-specific Netbox data."""

    def _get_netbox_device_plugin(self) -> str:
        """Example custom method that returns a string.

        Returns:
            str: True for testing purposes.

        """
        if self._device.metadata:
            return 'netbox_device_plugin'

        return ''
