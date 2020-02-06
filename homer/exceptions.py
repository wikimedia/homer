"""Exceptions module."""


class HomerError(Exception):
    """Parent exception class for all Homer exceptions."""


class HomerAbortError(HomerError):
    """Exception class for aborted actions."""
