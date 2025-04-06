"""Interactive module."""
import sys

from homer.exceptions import HomerAbortError, HomerError


def ask_approval() -> None:
    """Ask the user for the approval of the given device configuration diff.

    Raises:
        homer.exceptions.HomerError: if not in a TTY.
        homer.exceptions.HomerAbortError: if the approval is rejected or too many invalid answers.

    """
    if not sys.stdout.isatty():
        raise HomerError('Not in a TTY, unable to ask for confirmation')

    print('Type "yes" to commit, "no" to abort.')

    for _ in range(2):
        resp = input('> ')
        if resp == 'yes':
            break
        if resp == 'no':
            raise HomerAbortError('Commit aborted')

        print(('Invalid response, please type "yes" to commit or "no" to abort. After 2 wrong answers the '
               'commit will be aborted.'))
    else:
        raise HomerAbortError('Too many invalid answers, commit aborted')
