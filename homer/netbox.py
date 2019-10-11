"""Netbox module."""
from collections import UserDict
from typing import Any

from pynetbox.api import Api

from homer.devices import Device


class NetboxData(UserDict):  # pylint: disable=too-many-ancestors
    """Dynamic dictionary to gather the required data from Netbox."""

    def __init__(self, api: Api, device: Device):
        """Initialize the dictionary.

        Parameters:
            api (pynetbox.api.Api): the Netbox API instance.
            device (homer.devices.Device): the device for which to gather the data.

        """
        super().__init__()
        self._api = api
        self._device = device

    def __getitem__(self, key: Any) -> Any:
        """Dynamically call the related method, if exists, to return the requested data.

        Parameters:
            According to Python's datamodel, see:
            https://docs.python.org/3/reference/datamodel.html#object.__getitem__

        Returns:
            mixed: the dynamically gathered data.

        """
        method_name = '_get_{key}'.format(key=key)
        if not hasattr(self, method_name):
            raise KeyError(key)

        return getattr(self, method_name)()
