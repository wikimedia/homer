"""Exceptions module."""


class HomerError(Exception):
    """Parent exception class for all Homer exceptions."""


class HomerAbortError(HomerError):
    """Exception class for aborted actions."""


class HomerTimeoutError(HomerError):
    """Exception class for actions that timeout."""


class HomerConnectError(HomerError):
    """Exception class raised when unable to connect to a device."""
