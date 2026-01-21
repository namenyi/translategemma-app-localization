"""Data models for .strings file entries."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StringEntry:
    """Represents a single entry in a .strings file.

    Attributes:
        key: The string key/identifier.
        value: The localized string value.
        comment: Optional comment associated with the entry.
    """
    key: str
    value: str
    comment: Optional[str] = None

    def to_strings_format(self) -> str:
        """Convert entry to .strings file format.

        Returns:
            Formatted string entry with optional comment.
        """
        lines = []
        if self.comment:
            lines.append(f"/* {self.comment} */")

        escaped_key = self._escape(self.key)
        escaped_value = self._escape(self.value)
        lines.append(f'"{escaped_key}" = "{escaped_value}";')

        return "\n".join(lines)

    @staticmethod
    def _escape(s: str) -> str:
        """Escape special characters for .strings format."""
        return (s
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t"))

    @staticmethod
    def _unescape(s: str) -> str:
        """Unescape special characters from .strings format."""
        result = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                next_char = s[i + 1]
                if next_char == 'n':
                    result.append('\n')
                elif next_char == 'r':
                    result.append('\r')
                elif next_char == 't':
                    result.append('\t')
                elif next_char == '"':
                    result.append('"')
                elif next_char == '\\':
                    result.append('\\')
                else:
                    result.append(s[i])
                    result.append(next_char)
                i += 2
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)
