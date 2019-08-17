"""__init__ module tests."""
import homer


def test_version():
    """Check that the __version__ package variable is set."""
    assert hasattr(homer, '__version__')
