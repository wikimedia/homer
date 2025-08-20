"""Interactive module."""
import sys

from enum import Enum

from homer.exceptions import HomerError


class ApprovalStatus(Enum):  # TODO: use StrEnum with Python 3.11+
    """Represent the different approval statuses."""

    APPROVE_SINGLE = 'yes'
    """Approve the configuration diff for the current device only."""
    REJECT_SINGLE = 'no'
    """Reject the configuration diff for the current device only."""
    APPROVE_ALL = 'all'
    """Approve the configuration diff for the current device and all next devices with the same diff."""
    REJECT_ALL = 'none'
    """Reject the configuration diff for the current device and all next devices with the same diff."""


def ask_approval() -> ApprovalStatus:
    """Ask the user for the approval level for the given device configuration diff.

    Returns:
        the approval status, one of the values of the :py:class:`homer.interactive.ApprovalStatus` enum.

    Raises:
        homer.exceptions.HomerError: if not in a TTY or too many invalid answers were provided.

    """
    if not sys.stdout.isatty():
        raise HomerError('Not in a TTY, unable to ask for confirmation')

    message = (
        f'Type "{ApprovalStatus.APPROVE_SINGLE.value}" or "{ApprovalStatus.REJECT_SINGLE.value}" to commit or abort '
        f'the commit for this device, "{ApprovalStatus.APPROVE_ALL.value}" or "{ApprovalStatus.REJECT_ALL.value}" to '
        'commit or abort the commit for this device and all next devices with the same diff.'
    )
    print(message)
    valid_answers = {status.value: status for status in ApprovalStatus}

    for _ in range(2):
        answer = input('> ')
        if answer in valid_answers.keys():
            return valid_answers[answer]

        print('Invalid response, After 2 wrong answers the commit will be aborted.')

    raise HomerError('Too many invalid answers, commit aborted')
