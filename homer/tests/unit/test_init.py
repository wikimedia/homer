"""Tests for homer's __init__ module."""
import homer


def test_version():
    """Check that the __version__ package variable is set."""
    assert hasattr(homer, '__version__')
