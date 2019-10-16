"""Templates module."""
import logging
import os

from typing import Mapping

import jinja2

from homer.exceptions import HomerError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Renderer:
    """Load and render templates."""

    def __init__(self, base_path: str):
        """Initialize the instance.

        Arguments:
            base_path (str): the base path to initialize the Jinja2 environment with. All templates path must be
                relative to this base path.

        """
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.join(base_path, 'templates')),
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
        template_file = '{name}.conf'.format(name=template_name)
        try:
            template = self._env.get_template(template_file)
            return template.render(data)
        except jinja2.exceptions.TemplateSyntaxError as e:
            raise HomerError('Syntax error on template {file}'.format(file=template_file)) from e
        except jinja2.exceptions.TemplateError as e:
            raise HomerError('Could not render template {file}'.format(file=template_file)) from e
