"""Tests for the .strings file parser."""

import tempfile
from pathlib import Path

import pytest

from translator.strings import StringEntry, StringsParser


class TestStringEntry:
    """Tests for StringEntry dataclass."""

    def test_basic_entry(self):
        """Test basic entry creation."""
        entry = StringEntry(key="test", value="Test Value")
        assert entry.key == "test"
        assert entry.value == "Test Value"
        assert entry.comment is None

    def test_entry_with_comment(self):
        """Test entry with comment."""
        entry = StringEntry(key="test", value="Test", comment="A test comment")
        assert entry.comment == "A test comment"

    def test_to_strings_format_basic(self):
        """Test basic formatting."""
        entry = StringEntry(key="hello", value="Hello")
        assert entry.to_strings_format() == '"hello" = "Hello";'

    def test_to_strings_format_with_comment(self):
        """Test formatting with comment."""
        entry = StringEntry(key="hello", value="Hello", comment="Greeting")
        expected = '/* Greeting */\n"hello" = "Hello";'
        assert entry.to_strings_format() == expected

    def test_escape_sequences(self):
        """Test escape sequence handling."""
        entry = StringEntry(key="test", value='Line1\nLine2\t"quoted"\\back')
        formatted = entry.to_strings_format()
        assert '\\n' in formatted
        assert '\\t' in formatted
        assert '\\"' in formatted
        assert '\\\\' in formatted

    def test_unescape_sequences(self):
        """Test unescaping."""
        unescaped = StringEntry._unescape('Hello\\nWorld\\t\\"test\\"\\\\')
        assert unescaped == 'Hello\nWorld\t"test"\\'


class TestStringsParser:
    """Tests for StringsParser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return StringsParser()

    def test_parse_basic(self, parser):
        """Test basic parsing."""
        content = '"key" = "value";'
        entries = parser.parse(content)
        assert len(entries) == 1
        assert entries[0].key == "key"
        assert entries[0].value == "value"

    def test_parse_with_comment(self, parser):
        """Test parsing with comments."""
        content = '''/* A comment */
"key" = "value";'''
        entries = parser.parse(content)
        assert len(entries) == 1
        assert entries[0].comment == "A comment"

    def test_parse_multiple_entries(self, parser):
        """Test parsing multiple entries."""
        content = '''
"key1" = "value1";
"key2" = "value2";
"key3" = "value3";
'''
        entries = parser.parse(content)
        assert len(entries) == 3
        assert entries[0].key == "key1"
        assert entries[1].key == "key2"
        assert entries[2].key == "key3"

    def test_parse_escaped_values(self, parser):
        """Test parsing escaped values."""
        content = r'"test" = "Line1\nLine2";'
        entries = parser.parse(content)
        assert entries[0].value == "Line1\nLine2"

    def test_parse_quoted_values(self, parser):
        """Test parsing values with escaped quotes."""
        content = r'"test" = "She said \"Hello\"";'
        entries = parser.parse(content)
        assert entries[0].value == 'She said "Hello"'

    def test_parse_to_dict(self, parser):
        """Test parsing to dictionary."""
        content = '''
"key1" = "value1";
"key2" = "value2";
'''
        result = parser.parse_to_dict(content)
        assert "key1" in result
        assert "key2" in result
        assert result["key1"].value == "value1"

    def test_roundtrip(self, parser):
        """Test that parsing and formatting produces equivalent content."""
        original = [
            StringEntry("key1", "value1", "Comment 1"),
            StringEntry("key2", "Line\nBreak"),
            StringEntry("key3", 'Quote "test"'),
        ]

        formatted = parser.format(original)
        parsed = parser.parse(formatted)

        assert len(parsed) == len(original)
        for orig, pars in zip(original, parsed):
            assert orig.key == pars.key
            assert orig.value == pars.value

    def test_update_entries_add(self, parser):
        """Test adding new entries."""
        existing = [StringEntry("key1", "value1")]
        updates = {"key2": "value2"}

        result = parser.update_entries(existing, updates)
        assert len(result) == 2
        assert any(e.key == "key2" for e in result)

    def test_update_entries_modify(self, parser):
        """Test modifying existing entries."""
        existing = [StringEntry("key1", "old_value")]
        updates = {"key1": "new_value"}

        result = parser.update_entries(existing, updates)
        assert len(result) == 1
        assert result[0].value == "new_value"

    def test_update_entries_remove(self, parser):
        """Test removing entries."""
        existing = [
            StringEntry("key1", "value1"),
            StringEntry("key2", "value2"),
        ]
        removals = {"key2"}

        result = parser.update_entries(existing, {}, removals)
        assert len(result) == 1
        assert result[0].key == "key1"

    def test_file_io(self, parser):
        """Test reading and writing files."""
        entries = [
            StringEntry("app_name", "Test App", "Application name"),
            StringEntry("greeting", "Hello!"),
        ]

        with tempfile.NamedTemporaryFile(suffix='.strings', delete=False) as f:
            path = Path(f.name)

        try:
            parser.write(entries, path)
            assert path.exists()

            loaded = parser.parse_file(path)
            assert len(loaded) == 2
            assert loaded[0].key == "app_name"
            assert loaded[0].comment == "Application name"
        finally:
            path.unlink()
