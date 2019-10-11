"""Templates module tests."""
import pytest

from homer.exceptions import HomerError
from homer.templates import Renderer
from homer.tests import get_fixture_path


class TestRenderer:
    """Render class tests."""

    def setup_method(self):
        """Initialize the test instances."""
        # pylint: disable=attribute-defined-outside-init
        self.renderer = Renderer(get_fixture_path('templates'))

    def test_render_ok(self):
        """Should return the rendered template."""
        assert self.renderer.render('valid', {'test_key': 'test_value'}) == 'test_value;'

    def test_render_syntax_error(self):
        """Should raise HomerError if the template has a syntax error."""
        with pytest.raises(HomerError, match='Syntax error on template syntax_error.conf'):
            self.renderer.render('syntax_error', {})

    def test_render_parse_error(self):
        """Should raise HomerError if the template cannot be parsed."""
        with pytest.raises(HomerError, match='Could not render template non_existent.conf'):
            self.renderer.render('non_existent', {})
        with pytest.raises(HomerError, match='Could not render template key_error.conf'):
            self.renderer.render('key_error', {})
