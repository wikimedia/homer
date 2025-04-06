"""interactive module tests."""
from unittest import mock

import pytest

from homer import interactive
from homer.exceptions import HomerAbortError, HomerError


class TestAskApproval:
    """ask_approval() module tests."""

    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_not_tty(self, mocked_isatty):
        """It should raise HomerError if not in a TTY."""
        mocked_isatty.return_value = False
        with pytest.raises(HomerError, match='Not in a TTY, unable to ask for confirmation'):
            interactive.ask_approval()

    @pytest.mark.parametrize('input_values', (
        ('yes',),
        ('invalid', 'yes'),
    ))
    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_ok(self, mocked_isatty, mocked_input, input_values):
        """It should ask for approval and not raise an exception."""
        mocked_isatty.return_value = True
        mocked_input.side_effect = input_values
        assert interactive.ask_approval() is None

    @pytest.mark.parametrize('input_values', (
        ('no',),
        ('invalid', 'no'),
    ))
    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_no(self, mocked_isatty, mocked_input, input_values):
        """It should raise HomerAbortError if the answer is no."""
        mocked_isatty.return_value = True
        mocked_input.side_effect = input_values
        with pytest.raises(HomerAbortError, match='Commit aborted'):
            interactive.ask_approval()

    @mock.patch('builtins.input')
    @mock.patch('homer.interactive.sys.stdout.isatty')
    def test_ask_approval_invalid(self, mocked_isatty, mocked_input):
        """It should raise HomerAbortError if too many invalid answers are provided."""
        mocked_isatty.return_value = True
        mocked_input.side_effect = ('many', 'wrong', 'answers')
        with pytest.raises(HomerAbortError, match='Too many invalid answers, commit aborted'):
            interactive.ask_approval()
