"""Parser for Apple .strings files."""

import re
from pathlib import Path
from typing import Optional

from .models import StringEntry


class StringsParser:
    """Parser for Apple .strings files.

    Handles both UTF-8 and UTF-16 encoded files, preserves comments,
    and properly handles escape sequences.
    """

    # Pattern to match string entries: "key" = "value";
    ENTRY_PATTERN = re.compile(
        r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;',
        re.DOTALL
    )

    # Pattern to match comments: /* ... */
    COMMENT_PATTERN = re.compile(r'/\*\s*(.*?)\s*\*/', re.DOTALL)

    def parse(self, content: str) -> list[StringEntry]:
        """Parse .strings content into StringEntry objects.

        Args:
            content: The content of a .strings file.

        Returns:
            List of StringEntry objects.
        """
        entries = []
        current_comment: Optional[str] = None

        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Check for comment
            comment_match = self.COMMENT_PATTERN.match(line)
            if comment_match:
                current_comment = comment_match.group(1).strip()
                i += 1
                continue

            # Check for string entry
            entry_match = self.ENTRY_PATTERN.match(line)
            if entry_match:
                key = StringEntry._unescape(entry_match.group(1))
                value = StringEntry._unescape(entry_match.group(2))
                entries.append(StringEntry(
                    key=key,
                    value=value,
                    comment=current_comment
                ))
                current_comment = None
            else:
                # Handle multi-line entries by joining lines until we find a match
                combined = line
                j = i + 1
                while j < len(lines) and not self.ENTRY_PATTERN.match(combined):
                    combined += '\n' + lines[j]
                    entry_match = self.ENTRY_PATTERN.match(combined)
                    if entry_match:
                        break
                    j += 1

                if entry_match:
                    key = StringEntry._unescape(entry_match.group(1))
                    value = StringEntry._unescape(entry_match.group(2))
                    entries.append(StringEntry(
                        key=key,
                        value=value,
                        comment=current_comment
                    ))
                    current_comment = None
                    i = j

            i += 1

        return entries

    def parse_file(self, path: Path) -> list[StringEntry]:
        """Parse a .strings file.

        Automatically detects UTF-16 vs UTF-8 encoding.

        Args:
            path: Path to the .strings file.

        Returns:
            List of StringEntry objects.
        """
        content = self._read_file(path)
        return self.parse(content)

    def parse_to_dict(self, content: str) -> dict[str, StringEntry]:
        """Parse .strings content into a dictionary keyed by string key.

        Args:
            content: The content of a .strings file.

        Returns:
            Dictionary mapping keys to StringEntry objects.
        """
        entries = self.parse(content)
        return {entry.key: entry for entry in entries}

    def _read_file(self, path: Path) -> str:
        """Read a .strings file with automatic encoding detection.

        Args:
            path: Path to the file.

        Returns:
            File content as string.
        """
        raw = path.read_bytes()

        # Check for UTF-16 BOM
        if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
            return raw.decode('utf-16')

        # Try UTF-8 first (more common in modern iOS)
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to UTF-16
            return raw.decode('utf-16')

    def write(self, entries: list[StringEntry], path: Path, encoding: str = 'utf-8') -> None:
        """Write StringEntry objects to a .strings file.

        Args:
            entries: List of StringEntry objects to write.
            path: Path to the output file.
            encoding: File encoding ('utf-8' or 'utf-16').
        """
        content = self.format(entries)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        if encoding == 'utf-16':
            path.write_bytes(content.encode('utf-16'))
        else:
            path.write_text(content, encoding='utf-8')

    def format(self, entries: list[StringEntry]) -> str:
        """Format StringEntry objects as .strings content.

        Args:
            entries: List of StringEntry objects.

        Returns:
            Formatted .strings content.
        """
        lines = []
        for entry in entries:
            lines.append(entry.to_strings_format())
            lines.append('')  # Empty line between entries

        return '\n'.join(lines).rstrip() + '\n'

    def update_entries(
        self,
        existing: list[StringEntry],
        updates: dict[str, str],
        removals: Optional[set[str]] = None
    ) -> list[StringEntry]:
        """Update existing entries with new values.

        Args:
            existing: List of existing StringEntry objects.
            updates: Dictionary of key -> new value updates.
            removals: Set of keys to remove.

        Returns:
            Updated list of StringEntry objects.
        """
        removals = removals or set()
        result = []
        existing_keys = set()

        # Update existing entries
        for entry in existing:
            if entry.key in removals:
                continue
            existing_keys.add(entry.key)
            if entry.key in updates:
                result.append(StringEntry(
                    key=entry.key,
                    value=updates[entry.key],
                    comment=entry.comment
                ))
            else:
                result.append(entry)

        # Add new entries (keys that weren't in existing)
        for key, value in updates.items():
            if key not in existing_keys:
                result.append(StringEntry(key=key, value=value))

        return result
