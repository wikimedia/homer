"""Templates module."""
import abc
import importlib
import logging

from pathlib import Path
from typing import Mapping

import jinja2

from homer.exceptions import HomerError


logger = logging.getLogger(__name__)


class DeviceConfigurationBase(abc.ABC):
    """A base class for all the device configurations."""

    def __init__(self, config: dict):
        """Initialize the instance.

        Arguments:
            config (dict): the generated configuration.

        """
        self._config = config

    @abc.abstractmethod
    def __str__(self) -> str:
        """How to render the configuration as a string."""

    @property
    def config(self) -> dict:
        """Return the configuration in a format defined by the renderer called."""
        return self._config


class JinjaDeviceConfiguration(DeviceConfigurationBase):
    """The device configuration returned as a string combining the ACLs and other config."""

    def __str__(self) -> str:
        """Return the string representation of the configuration.

        Returns:
            str: the YAML representation of the configuration.

        """
        return '\n'.join(self._config['acls'] + [self._config['config']])


class RendererBase(abc.ABC):
    """Base class for the configuration renderers."""

    subdir: str
    """The base path sub-directory where the configuration bits are."""

    def __init__(self, base_path: str, base_private_path: str = ''):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path where the configuration data is.
            base_private_path (str, optional): a secondary private base path where the configuration data is.
                If things are not found in base_path they will be looked up in this secondary private location.

        """
        if not self.subdir:
            raise NotImplementedError('Derived class must implement the subdir property.')

        self._paths = [Path(base_path) / self.subdir]
        if base_private_path:
            self._paths.append(Path(base_private_path) / self.subdir)

    @abc.abstractmethod
    def render(self, template_name: str, data: Mapping, acls: list) -> DeviceConfigurationBase:
        """Render a template with the given data.

        Arguments:
            template_name (str): the name of the template to load without the file extension.
            data (dict): the dictionary of variables available for the configuration.
            acls (list): a list of ACLs to configure on the device, in a vendor specific format.

        Raises:
            homer.exceptions.HomerError: on error.

        Returns:
            str: the rendered template on success.
            None: on failure.

        """


class PythonRenderer(RendererBase):
    """Generate the configuration using Python modules."""

    subdir = 'modules'

    def render(self, template_name: str, data: Mapping, acls: list) -> DeviceConfigurationBase:
        """Render a template with the given data.

        Arguments:
            template_name (str): the name of the template to load without the file extension.
            data (dict): the dictionary of variables to pass to the JSON-RPC modules.
            acls (list): a list of ACLs to configure on the device, in a Nokia SRL specific format.

        Raises:
            homer.exceptions.HomerError: on error.

        Returns:
            dict: the rendered template on success.

        """
        try:
            module = importlib.import_module(f"{data['metadata']['manufacturer']}_{template_name}")
            instance = module.python_renderer(data)
            config = instance.render()
            if acls:
                for acl_filter in acls:
                    # Note: this won't delete filters, only modify or add new
                    # It's not possible to issue a delete on `/acl/acl-filter`, only /acl/ or specific filters.
                    config.append({'action': 'replace',
                                   'path': f'/acl/acl-filter[name={acl_filter["name"]}][type={acl_filter["type"]}]',
                                   'value': acl_filter})
            return config
        except Exception as e:
            raise HomerError(f'Error while trying to render JSON-RPC configuration: {e}') from e


class JinjaRenderer(RendererBase):
    """Load and render templates using Jinja."""

    subdir = 'templates'

    def __init__(self, base_path: str, base_private_path: str = ''):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path to initialize the Jinja2 environment with. All templates path must be
                relative to this base path.
            base_private_path (str, optional): a secondary base path to initialize the Jinja2 environment with.
                Templates that are not found in base_path will be looked up in this secondary private location.

        """
        super().__init__(base_path, base_private_path)

        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self._paths),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            cache_size=0)

    def render(self, template_name: str, data: Mapping, acls: list) -> DeviceConfigurationBase:
        """Render a template with the given data.

        Arguments:
            template_name (str): the name of the template to load without the file extension.
            data (dict): the dictionary of variables to pass to Jinja2 for replacement.
            acls (list): a list of ACLs to configure on the device, in a Junos specific format.

        Raises:
            homer.exceptions.HomerError: on error.

        Returns:
            str: the rendered template on success.
            None: on failure.

        """
        template_file = f'{template_name}.conf'
        try:
            template = self._env.get_template(template_file)
            return JinjaDeviceConfiguration({'acls': acls, 'config': template.render(data)})
        except jinja2.exceptions.TemplateSyntaxError as e:
            raise HomerError(f'Syntax error on template {template_file}') from e
        except jinja2.exceptions.TemplateError as e:
            raise HomerError(f'Could not render template {template_file}') from e
