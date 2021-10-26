"""Templates module."""
import logging
import os

from typing import Mapping

import jinja2

from homer.exceptions import HomerError


logger = logging.getLogger(__name__)


class Renderer:
    """Load and render templates."""

    def __init__(self, base_path: str, base_private_path: str = ''):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path to initialize the Jinja2 environment with. All templates path must be
                relative to this base path.
            base_private_path (str, optional): a secondary base path to initialize the Jinja2 environment with.
                Templates that are not found in base_path will be looked up in this secondary private location.

        """
        paths = [os.path.join(base_path, 'templates')]
        if base_private_path:
            paths.append(os.path.join(base_private_path, 'templates'))

        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(paths),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            cache_size=0)

    def render(self, template_name: str, data: Mapping) -> str:
        """Render a template with the given data.

        Arguments:
            template_name (str): the name of the template to load without the file extension.
            data (dict): the dictionary of variables to pass to Jinja2 for replacement.

        Raises:
            HomerError: on error.

        Returns:
            str: the rendered template on success.
            None: on failure.

        """
        template_file = f'{template_name}.conf'
        try:
            template = self._env.get_template(template_file)
            return template.render(data)
        except jinja2.exceptions.TemplateSyntaxError as e:
            raise HomerError(f'Syntax error on template {template_file}') from e
        except jinja2.exceptions.TemplateError as e:
            raise HomerError(f'Could not render template {template_file}') from e
