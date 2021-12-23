"""Capirca module."""

import logging

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Mapping

import pynetbox

from capirca.lib import juniper, junipersrx, naming, policy

from homer.exceptions import HomerError

logger = logging.getLogger(__name__)


class CapircaGenerate():
    """Class to generate ACLs with Capirca."""

    def __init__(self, config: Mapping, device_policies: List[str], netbox: pynetbox.api):
        """Initialize the instance.

        Arguments:
            config (dict): the Homer config.
            device_policies (list): List of Capirca policies to generate.
            netbox (pynetbox.api): the Netbox API instance.

        """
        self._config = config
        self._device_policies = device_policies
        self._public_policies_dir = Path(self._config['base_paths']['public'], 'policies')
        self._private_base_path = self._config['base_paths'].get('private', None)
        definitions_path = Path(self._config['base_paths']['public'], 'definitions')
        self.definitions = naming.Naming(str(definitions_path))
        # If we want to use Netbox as network definition source
        if self._config.get('capirca', {}).get('netbox_definitons', True) and netbox:
            try:
                script_result = netbox.extras.scripts.get('capirca.GetHosts').result
                if str(script_result.status) != 'Completed':
                    raise HomerError(f'Netbox capirca.GetHosts script status is: {script_result.status}.')
                runtime = datetime.fromisoformat(script_result.completed[:-1])  # To remove the final Z
                now = datetime.utcnow()
                # Warn the user if the Netbox data is 3 day old or more
                if runtime < now - timedelta(days=3):
                    logger.warning('Netbox capirca.GetHosts script is > 3 days old.')
                netbox_definitons = script_result.data.output
            except pynetbox.RequestError as e:
                raise HomerError('Make sure homer can reach the capirca.GetHosts script on Netbox.') from e
            # ParseNetworkList expects an array of lines, while Netbox API returns a string with \n
            self.definitions.ParseNetworkList(netbox_definitons.splitlines())

    def generate_acls(self) -> List[str]:  # noqa, mccabe: MC0001 too complex
        """Generate the ACLs using Capirca lib.

        Returns:
            list: a list of policies as strings in the proper format.

        """
        generated_acls = []
        if self._private_base_path:
            private_policies_dir = Path(self._private_base_path, 'policies')

        # Store failures if any
        failures = []
        # Iterate over all policies defined for a given device
        for policy_name in self._device_policies:
            # We don't know yet if the files below exist
            public_policy_file = Path(self._public_policies_dir, policy_name + '.pol')
            private_policy_file = Path()
            if self._private_base_path:
                private_policy_file = Path(private_policies_dir, policy_name + '.pol')
            # If same file in both private and public, prefer private
            if private_policy_file.is_file():
                policy_file = private_policy_file
                policies_dir = private_policies_dir
            elif public_policy_file.is_file():
                policy_file = public_policy_file
                policies_dir = self._public_policies_dir
            else:
                failures.append(f"Can't find Capirca policy file {policy_name}.")
                continue
            policy_text = policy_file.read_text(encoding='utf-8')
            try:
                policy_object = policy.ParsePolicy(policy_text, self.definitions,
                                                   optimize=True,
                                                   shade_check=False,
                                                   base_dir=policies_dir)
            except policy.ShadingError as e:
                # Term "hiding" another term
                failures.append(f"Shading errors for {policy_name}: {e}.")
                continue
            except (policy.Error, naming.Error) as e:
                failures.append(f"Error parsing {policy_name}: {e}.")
                continue

            # https://github.com/google/capirca/blob/master/capirca/aclgen.py#L222
            platforms = set()
            for header in policy_object.headers:
                platforms.update(header.platforms)
            try:
                found_platform = False
                if 'juniper' in platforms:
                    found_platform = True
                    generated_acls.append(str(juniper.Juniper(policy_object, exp_info=2)))
                if 'srx' in platforms:
                    found_platform = True
                    generated_acls.append(str(junipersrx.JuniperSRX(policy_object, exp_info=2)))
                if not found_platform:
                    failures.append(f"Unknown platform: {platforms}.")

            except (juniper.Error) as e:
                failures.append(f"Error generating {policy_name}: {e}.")
                continue
        if failures:
            raise HomerError("Capirca error(s)\n" + '\n'.join(failures))

        return generated_acls
