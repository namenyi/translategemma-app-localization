"""Git diff detection for .strings files."""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from ..strings.parser import StringsParser


class ChangeType(Enum):
    """Type of change detected in a .strings file."""
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"


@dataclass
class StringChange:
    """Represents a change to a string entry.

    Attributes:
        key: The string key that changed.
        change_type: Type of change (added, modified, removed).
        old_value: Previous value (None for added entries).
        new_value: New value (None for removed entries).
    """
    key: str
    change_type: ChangeType
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class DiffDetector:
    """Detects changes between versions of .strings files using git."""

    def __init__(self, repo_path: Optional[Path] = None):
        """Initialize the detector.

        Args:
            repo_path: Path to the git repository. Defaults to current directory.
        """
        self.repo_path = repo_path or Path.cwd()
        self.parser = StringsParser()

    def detect_changes(
        self,
        file_path: Path,
        base_ref: str = "HEAD~1",
        head_ref: str = "HEAD"
    ) -> list[StringChange]:
        """Detect changes to a .strings file between two git refs.

        Args:
            file_path: Path to the .strings file (relative to repo root).
            base_ref: Base git reference (commit, branch, tag). Default: HEAD~1.
            head_ref: Head git reference. Default: HEAD.

        Returns:
            List of StringChange objects describing the changes.
        """
        # Get file content at base ref
        base_content = self._get_file_at_ref(file_path, base_ref)
        base_entries = self.parser.parse_to_dict(base_content) if base_content else {}

        # Get file content at head ref
        head_content = self._get_file_at_ref(file_path, head_ref)
        head_entries = self.parser.parse_to_dict(head_content) if head_content else {}

        return self._compare_entries(base_entries, head_entries)

    def detect_changes_from_working_tree(
        self,
        file_path: Path,
        base_ref: str = "HEAD"
    ) -> list[StringChange]:
        """Detect changes between a git ref and the current working tree.

        Args:
            file_path: Path to the .strings file.
            base_ref: Base git reference to compare against.

        Returns:
            List of StringChange objects describing the changes.
        """
        # Get file content at base ref
        base_content = self._get_file_at_ref(file_path, base_ref)
        base_entries = self.parser.parse_to_dict(base_content) if base_content else {}

        # Get current file content from working tree
        abs_path = self.repo_path / file_path if not file_path.is_absolute() else file_path
        if abs_path.exists():
            current_entries = {
                e.key: e for e in self.parser.parse_file(abs_path)
            }
        else:
            current_entries = {}

        return self._compare_entries(base_entries, current_entries)

    def _get_file_at_ref(self, file_path: Path, ref: str) -> Optional[str]:
        """Get file content at a specific git reference.

        Args:
            file_path: Path to the file (relative to repo root).
            ref: Git reference.

        Returns:
            File content as string, or None if file doesn't exist at that ref.
        """
        # Normalize path to be relative to repo root
        try:
            if file_path.is_absolute():
                file_path = file_path.relative_to(self.repo_path)
        except ValueError:
            pass

        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{file_path}"],
                capture_output=True,
                cwd=self.repo_path,
                check=True
            )
            # Try to decode as UTF-8 first, then UTF-16
            try:
                return result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                return result.stdout.decode('utf-16')
        except subprocess.CalledProcessError:
            # File doesn't exist at this ref
            return None

    def _compare_entries(
        self,
        base: dict,
        head: dict
    ) -> list[StringChange]:
        """Compare two sets of entries and return changes.

        Args:
            base: Dictionary of entries at base ref.
            head: Dictionary of entries at head ref.

        Returns:
            List of StringChange objects.
        """
        changes = []
        base_keys = set(base.keys())
        head_keys = set(head.keys())

        # Added keys
        for key in head_keys - base_keys:
            changes.append(StringChange(
                key=key,
                change_type=ChangeType.ADDED,
                new_value=head[key].value
            ))

        # Removed keys
        for key in base_keys - head_keys:
            changes.append(StringChange(
                key=key,
                change_type=ChangeType.REMOVED,
                old_value=base[key].value
            ))

        # Modified keys
        for key in base_keys & head_keys:
            if base[key].value != head[key].value:
                changes.append(StringChange(
                    key=key,
                    change_type=ChangeType.MODIFIED,
                    old_value=base[key].value,
                    new_value=head[key].value
                ))

        return changes

    def get_translatable_changes(
        self,
        file_path: Path,
        base_ref: str = "HEAD~1",
        head_ref: str = "HEAD"
    ) -> list[StringChange]:
        """Get only the changes that need translation (added and modified).

        Args:
            file_path: Path to the .strings file.
            base_ref: Base git reference.
            head_ref: Head git reference.

        Returns:
            List of StringChange objects for added and modified entries.
        """
        all_changes = self.detect_changes(file_path, base_ref, head_ref)
        return [
            c for c in all_changes
            if c.change_type in (ChangeType.ADDED, ChangeType.MODIFIED)
        ]
