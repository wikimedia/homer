"""Diff module tests."""
import pytest

from homer import diff
from homer.exceptions import HomerDiffError


class TestDiffStore:
    """DiffStore class tests."""

    def setup_method(self):
        """Initialize the test."""
        # pylint: disable=attribute-defined-outside-init
        self.diff_store = diff.DiffStore()

    def teardown_method(self):
        """Cleanup."""
        diff.DiffStore.reset()

    def test_init(self):
        """It should initialize a DiffStore instance and that it's always the same."""
        for _ in range(3):
            new = diff.DiffStore()
            assert new is self.diff_store

    def test_reset(self):
        """It should re-create a new instance after reset is called."""
        diff.DiffStore.reset()
        assert self.diff_store is not diff.DiffStore()

    def test_status_not_present(self):
        """It should return None if the diff is not present."""
        assert self.diff_store.status('diff') is None

    def test_approve_ok(self):
        """It should approve the diff."""
        assert self.diff_store.status('diff') is None
        self.diff_store.approve('diff')
        assert self.diff_store.status('diff') is True
        # Approving again is a noop
        self.diff_store.approve('diff')
        assert self.diff_store.status('diff') is True

    def test_approve_already_rejected(self):
        """It should raise a HomerDiffError if the approved diff was already rejected."""
        self.diff_store.reject('diff')
        with pytest.raises(
            HomerDiffError, match='Diff already rejected for all devices, hence it cannot be approved.'
        ):
            self.diff_store.approve('diff')

    def test_reject_ok(self):
        """It should reject the diff."""
        assert self.diff_store.status('diff') is None
        self.diff_store.reject('diff')
        assert self.diff_store.status('diff') is False
        # Rejecting again is a noop
        self.diff_store.reject('diff')
        assert self.diff_store.status('diff') is False

    def test_reject_already_approved(self):
        """It should raise a HomerDiffError if the rejected diff was already approved."""
        self.diff_store.approve('diff')
        with pytest.raises(
            HomerDiffError, match='Diff already approved for all devices, hence it cannot be rejected.'
        ):
            self.diff_store.reject('diff')
