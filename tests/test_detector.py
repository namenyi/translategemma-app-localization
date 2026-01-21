"""Tests for the git diff detector."""

import pytest

from translator.diff import DiffDetector, StringChange, ChangeType
from translator.strings import StringEntry


class TestDiffDetector:
    """Tests for DiffDetector."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return DiffDetector()

    def test_compare_entries_no_changes(self, detector):
        """Test comparing identical entries."""
        entries = {
            "key1": StringEntry("key1", "value1"),
            "key2": StringEntry("key2", "value2"),
        }

        changes = detector._compare_entries(entries, entries)
        assert len(changes) == 0

    def test_compare_entries_added(self, detector):
        """Test detecting added entries."""
        base = {"key1": StringEntry("key1", "value1")}
        head = {
            "key1": StringEntry("key1", "value1"),
            "key2": StringEntry("key2", "value2"),
        }

        changes = detector._compare_entries(base, head)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.ADDED
        assert changes[0].key == "key2"
        assert changes[0].new_value == "value2"

    def test_compare_entries_removed(self, detector):
        """Test detecting removed entries."""
        base = {
            "key1": StringEntry("key1", "value1"),
            "key2": StringEntry("key2", "value2"),
        }
        head = {"key1": StringEntry("key1", "value1")}

        changes = detector._compare_entries(base, head)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.REMOVED
        assert changes[0].key == "key2"
        assert changes[0].old_value == "value2"

    def test_compare_entries_modified(self, detector):
        """Test detecting modified entries."""
        base = {"key1": StringEntry("key1", "old_value")}
        head = {"key1": StringEntry("key1", "new_value")}

        changes = detector._compare_entries(base, head)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert changes[0].key == "key1"
        assert changes[0].old_value == "old_value"
        assert changes[0].new_value == "new_value"

    def test_compare_entries_mixed_changes(self, detector):
        """Test detecting multiple types of changes."""
        base = {
            "keep": StringEntry("keep", "same"),
            "modify": StringEntry("modify", "old"),
            "remove": StringEntry("remove", "gone"),
        }
        head = {
            "keep": StringEntry("keep", "same"),
            "modify": StringEntry("modify", "new"),
            "add": StringEntry("add", "fresh"),
        }

        changes = detector._compare_entries(base, head)

        added = [c for c in changes if c.change_type == ChangeType.ADDED]
        modified = [c for c in changes if c.change_type == ChangeType.MODIFIED]
        removed = [c for c in changes if c.change_type == ChangeType.REMOVED]

        assert len(added) == 1
        assert added[0].key == "add"

        assert len(modified) == 1
        assert modified[0].key == "modify"

        assert len(removed) == 1
        assert removed[0].key == "remove"


class TestStringChange:
    """Tests for StringChange dataclass."""

    def test_added_change(self):
        """Test creating an added change."""
        change = StringChange(
            key="new_key",
            change_type=ChangeType.ADDED,
            new_value="New Value"
        )
        assert change.key == "new_key"
        assert change.change_type == ChangeType.ADDED
        assert change.old_value is None
        assert change.new_value == "New Value"

    def test_modified_change(self):
        """Test creating a modified change."""
        change = StringChange(
            key="mod_key",
            change_type=ChangeType.MODIFIED,
            old_value="Old",
            new_value="New"
        )
        assert change.change_type == ChangeType.MODIFIED
        assert change.old_value == "Old"
        assert change.new_value == "New"

    def test_removed_change(self):
        """Test creating a removed change."""
        change = StringChange(
            key="del_key",
            change_type=ChangeType.REMOVED,
            old_value="Gone"
        )
        assert change.change_type == ChangeType.REMOVED
        assert change.old_value == "Gone"
        assert change.new_value is None
