"""interactive module tests."""
from unittest import mock

import pytest

from homer import interactive
from homer.exceptions import HomerError


class TestAskApproval:
    """ask_approval() module tests."""

    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_not_tty(self, mocked_isatty):
        """It should raise HomerError if not in a TTY."""
        mocked_isatty.return_value = False
        with pytest.raises(HomerError, match='Not in a TTY, unable to ask for confirmation'):
            interactive.ask_approval()

    @pytest.mark.parametrize('last_value', tuple(interactive.ApprovalStatus))
    @pytest.mark.parametrize('input_values', ((), ('invalid',)))
    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_ok(self, mocked_isatty, mocked_input, input_values, last_value):
        """It should ask for approval and not raise an exception."""
        mocked_isatty.return_value = True
        mocked_input.side_effect = input_values + (last_value.value,)
        ret = interactive.ask_approval()
        assert ret is last_value

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_invalid(self, mocked_isatty, mocked_input):
        """It should raise HomerAbortError if too many invalid answers are provided."""
        mocked_isatty.return_value = True
        mocked_input.side_effect = ('many', 'wrong', 'answers')
        with pytest.raises(HomerError, match='Too many invalid answers, commit aborted'):
            interactive.ask_approval()
