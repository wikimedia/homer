"""Netbox module tests."""
from collections import UserDict
from unittest import mock

import pytest

from pynetbox import api

from homer.devices import Device
from homer.netbox import NetboxData


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
