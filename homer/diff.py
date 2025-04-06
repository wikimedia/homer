"""Diff module."""
from typing import Optional

from homer.exceptions import HomerDiffError


class DiffStore:
    """Singleton class to store the device configuration diffs approved or rejected for all devices."""

    _instance: Optional["DiffStore"] = None
    """Store the only allowed instance for this class."""
    # Types of instance properties must be defined here as they are defined in __new__
    _approved_diffs: set[str]
    """Store the diffs approved for all."""
    _rejected_diffs: set[str]
    """Store the diffs rejected for all."""

    def __new__(cls) -> 'DiffStore':
        """Class creator method, ensure that only one instance is instantiated.

        Returns:
            the diff store instance.

        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._approved_diffs = set()
            cls._instance._rejected_diffs = set()

        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the DiffStore to its original state erasing all the data."""
        cls._instance = None

    def approve(self, diff: str) -> None:
        """Approve a diff for all devices having the same diff.

        Arguments:
            diff: the approved diff.

        Raises:
            homer.exceptions.HomerDiffError: if the diff is already in the store with a different status.

        """
        if diff in self._approved_diffs:
            return

        if diff in self._rejected_diffs:
            raise HomerDiffError('Diff already rejected for all devices, hence it cannot be approved.')

        self._approved_diffs.add(diff)

    def reject(self, diff: str) -> None:
        """Reject a diff for all devices having the same diff.

        Arguments:
            diff: the rejected diff.

        Raises:
            homer.exceptions.HomerDiffError: if the diff is already in the store with a different status.

        """
        if diff in self._rejected_diffs:
            return

        if diff in self._approved_diffs:
            raise HomerDiffError('Diff already approved for all devices, hence it cannot be rejected.')

        self._rejected_diffs.add(diff)

    def status(self, diff: str) -> Optional[bool]:
        """Get the diff status, if present in the store.

        Returns:
            :py:data:`None`: if the diff is not present at all in the store, not approved nor rejected.
            :py:data:`True`: if the diff is approved.
            :py:data:`False`: if the diff is rejected.

        """
        if diff in self._rejected_diffs:
            return False

        if diff in self._approved_diffs:
            return True

        return None
