"""Transports module."""
DEFAULT_TIMEOUT = 30
"""Default timeout in seconds to use when interacting with the devices."""
DEFAULT_PORT = 22
"""Default port to use when interacting with the devices."""
DEFAULT_JSONRPC_PORT = 443
"""The default TCP port that will be passed to the JSON RPC transport."""

DIFF_ADDED_CODE = 32
DIFF_REMOVED_CODE = 31
DIFF_MOVED_CODE = 33


def color_diff(diff: str) -> str:
    """Color the diff."""
    lines = []
    for line in diff.splitlines():
        if line.startswith('+'):
            code = DIFF_ADDED_CODE
        elif line.startswith('-'):
            code = DIFF_REMOVED_CODE
        elif line.startswith('!'):
            code = DIFF_MOVED_CODE
        else:
            code = 0

        if code:
            line = f'\x1b[{code}m{line}\x1b[39m'

        lines.append(line)

    colored_diff = '\n'.join(lines)
    if diff and diff[-1] == '\n':  # Re-add the last trailing newline if present
        colored_diff += '\n'

    return colored_diff
