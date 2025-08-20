"""Netbox module."""
import ipaddress
import logging

from collections import UserDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pynetbox

from requests.exceptions import RequestException

from homer.devices import Device
from homer.exceptions import HomerError


logger = logging.getLogger(__name__)


class BaseNetboxData(UserDict):
    """Base class to gather data dynamically from Netbox."""

    def __init__(self, api: pynetbox.api, base_paths: dict[str, str]):
        """Initialize the dictionary.

        Arguments:
            api: the Netbox API instance.
            base_paths: The path to the public and private directories.

        """
        super().__init__()
        self._api = api
        self._base_paths = base_paths

    def __getitem__(self, key: Any) -> Any:
        """Dynamically call the related method, if exists, to return the requested data.

        Parameters according to Python's datamodel, see:
        https://docs.python.org/3/reference/datamodel.html#object.__getitem__

        Returns:
            The dynamically gathered data.

        """
        method_name = f'_get_{key}'
        if not hasattr(self, method_name):
            raise KeyError(key)

        if key not in self.data:
            try:
                self.data[key] = getattr(self, method_name)()
            except Exception as e:
                raise HomerError(f'Failed to get key {key}') from e

        return self.data[key]

    def _gql_execute(self, query_name: str, variables: Optional[dict] = None) -> dict[str, Any]:
        """Exposes gql_execute to BaseNetboxData.

        Arguments:
            query_name: the name of the file in the ``graphql`` directory without the ``.gql`` extension.
            variables: the variables to pass to the GraphQL query.

        Returns:
            The result of the queried data.

        """
        gql_query_path = Path(self._base_paths['public']) / 'graphql' / f'{query_name}.gql'
        return gql_execute(self._api, gql_query_path.read_text(), variables)


class BaseNetboxDeviceData(BaseNetboxData):
    """Base class to gather device-specific data dynamically from Netbox."""

    def __init__(self, api: pynetbox.api, base_paths: dict[str, str], device: Device):
        """Initialize the dictionary.

        Arguments:
            api: the Netbox API instance.
            base_paths: The path to the public and private directories.
            device: the device for which to gather the data.

        """
        super().__init__(api, base_paths)
        self._device = device
        self._device_interfaces: dict = {}
        self._device.metadata['netbox_object'] = api.dcim.devices.get(id=device.metadata['id'])

    @property
    def _gql_variables(self) -> dict[str, Any]:
        """Returns the default GraphQL variables to inject into all queries.

        Returns:
            The variables dictionary

        """
        # Inject device_id
        variables = {'device_id': str(self._device.metadata['id'])}

        # Inject virtual_chassis_id if defined:
        if self._device.metadata['netbox_object'].virtual_chassis:
            variables['virtual_chassis_id'] = str(self._device.metadata['netbox_object'].virtual_chassis.id)

        return variables

    def _gql_execute(self, query_name: str, variables: Optional[dict] = None) -> dict[str, Any]:
        """Exposes gql_execute to BaseNetboxDeviceData while injecting device variables.

        Arguments:
            query_name: the name of the file in the ``graphql`` directory without the ``.gql`` extension.
            variables: the variables to pass to the GraphQL query.

        Returns:
            The result of the queried data.

        """
        default_variables = self._gql_variables
        # Variables passed as parameter take priority if any conflict
        if variables:
            default_variables.update(variables)

        return super()._gql_execute(query_name, default_variables)

    def fetch_device_interfaces(self) -> dict:
        """Fetch interfaces from Netbox.

        Returns:
            the interfaces dictionary.

        """
        if not self._device_interfaces:
            if self._device.metadata['netbox_object'].virtual_chassis:
                query_name = 'interface_list_virtual_chassis'
            else:
                query_name = 'interface_list'
            self._device_interfaces = gql_execute(
                self._api, get_gql_query(query_name), self._gql_variables)['interface_list']

        return self._device_interfaces


class NetboxData(BaseNetboxData):
    """Dynamic dictionary to gather the required generic data from Netbox."""

    def _get_vlans(self) -> List[Dict[str, Any]]:
        """Returns all the vlans defined in Netbox.

        Returns:
            A list of vlans.

        """
        return [dict(i) for i in self._api.ipam.vlans.all()]


class NetboxDeviceData(BaseNetboxDeviceData):
    """Dynamic dictionary to gather the required device-specific data from Netbox."""

    def _get_virtual_chassis_members(self) -> Optional[List[Dict[str, Any]]]:
        """Returns a list of devices part of the same virtual chassis or None.

        Returns:
            A list of devices or :py:data:`None` if the device is not part of a virtual chassis.

        """
        if not self._device.metadata['netbox_object'].virtual_chassis:
            return None

        vc_id = self._device.metadata['netbox_object'].virtual_chassis.id
        return [dict(i) for i in self._api.dcim.devices.filter(virtual_chassis_id=vc_id)]

    def _get_circuits(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Returns a list of circuits connected to the device.

        Returns:
            A list of circuits.

        """
        circuits = {}
        for a_int in self.fetch_device_interfaces():
            # b_int is either the patch panel interface facing out or the initial interface
            # if no patch panel
            # Using link_peers[0] to mimic pre-Netbox 3.3 behavior, when a cable only had one termination
            # per side. To be revisited if we start using the multi-termination feature
            if (a_int['link_peers'] and a_int['link_peers'][0]['__typename'] == 'FrontPortType'
                    and a_int['link_peers'][0]['rear_port']):
                b_int = a_int['link_peers'][0]['rear_port']
            else:
                # If the patch panel isn't patched through
                b_int = a_int

            if b_int['link_peers'] and b_int['link_peers'][0]['__typename'] == 'CircuitTerminationType':
                circuits[a_int['name']] = dict(
                    self._api.circuits.circuits.get(int(b_int['link_peers'][0]['circuit']['id'])))

        return circuits

    def _get_inventory(self) -> Optional[List[Dict[Any, Any]]]:
        """Returns the list of inventory items on the device.

        Returns:
            A list of inventory items.

        """
        device_id = self._device.metadata['netbox_object'].id
        return [dict(i) for i in self._api.dcim.inventory_items.filter(device_id=device_id)]

    def _get_vlans(self) -> Dict[int, Any]:
        """Returns all the vlans defined on a device.

        Returns:
            A dict of vlans keyed by VLAN ID.

        """
        vlans = {}

        for interface in self.fetch_device_interfaces():
            if interface['untagged_vlan'] and interface['untagged_vlan']['vid'] not in vlans:
                vlans[int(interface['untagged_vlan']['vid'])] = interface['untagged_vlan']
            for tagged_vlan in interface['tagged_vlans']:
                vid = int(tagged_vlan['vid'])
                if vid not in vlans:
                    vlans[vid] = tagged_vlan

            if interface['name'].startswith('irb'):
                vid = int(interface['name'].split('.')[1])
                if vid not in vlans:
                    vlan = dict(self._api.ipam.vlans.get(vid=vid))
                    try:
                        vlans[vlan['vid']] = vlan
                    except KeyError as e:
                        raise HomerError(f'IRB interface {interface["name"]} does not match any Vlan in Netbox') from e

        return vlans


class NetboxInventory:
    """Use Netbox as inventory to gather the list of devices to manage."""

    def __init__(self, api: pynetbox.api, device_roles: Sequence[str], device_statuses: Sequence[str]):
        """Initialize the instance.

        Arguments:
            api: the Netbox API instance.
            config: Homer's configuration section about Netbox
            device_roles: a sequence of Netbox device role slug strings to filter the devices.
            device_statuses: a sequence of Netbox device status label or value strings to filter the devices.

        """
        self._api = api
        self._device_roles = device_roles
        self._device_statuses = [status.lower() for status in device_statuses]

    def get_devices(self) -> Dict[str, Dict[str, str]]:
        """Get the devices based on role, status and virtual chassis membership.

        Returns:
            A dictionary with the device FQDN as keys and a metadata dictionary as value.

        """
        devices: Dict[str, Dict[str, str]] = {}

        device_list_gql = get_gql_query('device_list')
        variables = {'role': self._device_roles, 'status': self._device_statuses}
        devices_gql = gql_execute(self._api, device_list_gql, variables)['device_list']

        for device in devices_gql:
            if (device.get('primary_ip4') and device['primary_ip4'].get('dns_name')):
                fqdn = device['primary_ip4']['dns_name']
            elif (device.get('primary_ip6') and device['primary_ip6'].get('dns_name')):
                fqdn = device['primary_ip6']['dns_name']
            else:
                logger.debug('Unable to determine FQDN for device %s, skipping.', device['name'])
                continue

            metadata = {
                'id': device['id'],
                'role': device['role']['slug'],
                'site': device['site']['slug'],
                'type': device['device_type']['slug'],
                'status': device['status'].lower(),
                'manufacturer': device['device_type']['manufacturer']['slug']
            }

            # Convert Netbox interfaces into IPs
            if device.get('primary_ip4') is not None:
                metadata['ip4'] = ipaddress.ip_interface(device['primary_ip4']['address']).ip.compressed
            if device.get('primary_ip6') is not None:
                metadata['ip6'] = ipaddress.ip_interface(device['primary_ip6']['address']).ip.compressed

            devices[fqdn] = metadata

        return devices


def get_gql_query(name: str) -> str:
    """Get one of the GraphQL query provided by Homer.

    Arguments:
        name: the name of the query file without extension.

    Returns:
        the query as string.

    """
    query_path = Path(__file__).resolve().parent / 'graphql' / f'{name}.gql'
    return query_path.read_text()


def gql_execute(api: pynetbox.api, query: str, variables: Optional[dict] = None) -> dict[str, Any]:
    """Parse the query into a gql query, execute and return the results.

    Arguments:
        api: the Netbox API instance.
        query: a string representing the gql query.
        variables: A list of variables to send.

    Raises:
        homer.exceptions.HomerError: if failed to query Netbox or no data was returned.

    Results:
        The results of the query.

    """
    data: dict[str, Union[str, dict]] = {'query': query}

    if variables is not None:
        data['variables'] = variables

    session = api.http_session
    session.headers.update({'Authorization': f'Token {api.token}'})
    session.headers.update({'Content-Type': 'application/json'})

    response = None
    try:
        response = session.post(api.base_url.replace('/api', '/graphql/'), json=data, timeout=15)
        response.raise_for_status()
        return response.json()['data']
    except RequestException as error:
        response_text = f'\n{response.text}' if response is not None else ''
        raise HomerError(f'failed to fetch netbox data: {error}{response_text}') from error
    except KeyError as error:
        raise HomerError(f'No data found in GraphQL response: {error}') from error
