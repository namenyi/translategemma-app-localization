"""Integration tests for the translation service."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from translator.config import TranslationConfig
from translator.core import TranslationService
from translator.diff import StringChange, ChangeType
from translator.strings import StringsParser, StringEntry
from translator.translation import TranslationEngine, BatchTranslator
from translator.translation.batch import TranslationResult, BatchResult


class TestTranslationEngine:
    """Tests for TranslationEngine with mocked backend."""

    def test_translate_with_mocked_ollama(self):
        """Test translation with mocked Ollama backend."""
        config = TranslationConfig(target_languages=["de", "fr"])
        engine = TranslationEngine(config)

        with patch.object(engine.backend, 'translate') as mock_translate:
            mock_translate.return_value = "Hallo Welt"

            result = engine.translate("Hello World", "de")

            assert result == "Hallo Welt"
            mock_translate.assert_called_once_with("Hello World", "en", "de")

    def test_translate_to_all(self):
        """Test translating to all target languages."""
        config = TranslationConfig(target_languages=["de", "fr"])
        engine = TranslationEngine(config)

        translations = {
            ("Hello", "en", "de"): "Hallo",
            ("Hello", "en", "fr"): "Bonjour",
        }

        def mock_translate(text, source, target):
            return translations.get((text, source, target), text)

        with patch.object(engine.backend, 'translate', side_effect=mock_translate):
            result = engine.translate_to_all("Hello")

            assert result == {"de": "Hallo", "fr": "Bonjour"}


class TestBatchTranslator:
    """Tests for BatchTranslator."""

    def test_translate_changes(self):
        """Test batch translation of changes."""
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        changes = [
            StringChange("key1", ChangeType.ADDED, new_value="Hello"),
            StringChange("key2", ChangeType.MODIFIED, old_value="Old", new_value="New"),
        ]

        with patch.object(engine.backend, 'translate', return_value="Translated"):
            result = batch.translate_changes(changes)

            assert result.total == 2
            assert result.successful == 2
            assert result.failed == 0
            assert len(result.results) == 2

    def test_translate_with_progress_callback(self):
        """Test progress callback is called."""
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        changes = [
            StringChange("key1", ChangeType.ADDED, new_value="Hello"),
        ]

        progress_calls = []

        def progress_callback(current, total, key):
            progress_calls.append((current, total, key))

        with patch.object(engine.backend, 'translate', return_value="Translated"):
            batch.translate_changes(changes, progress_callback=progress_callback)

        assert len(progress_calls) == 1
        assert progress_calls[0] == (1, 1, "key1")


class TestTranslationServiceIntegration:
    """Integration tests for TranslationService."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory with .strings structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "Localizations"

            # Create language directories
            for lang in ["en", "de", "fr"]:
                (base / f"{lang}.lproj").mkdir(parents=True)

            yield base

    def test_update_target_files(self, temp_dir):
        """Test updating target language files."""
        # Create source file
        parser = StringsParser()
        source_file = temp_dir / "en.lproj" / "Localizable.strings"
        parser.write([
            StringEntry("hello", "Hello"),
            StringEntry("goodbye", "Goodbye"),
        ], source_file)

        # Create initial target files
        for lang in ["de", "fr"]:
            parser.write([
                StringEntry("hello", f"Old {lang}"),
            ], temp_dir / f"{lang}.lproj" / "Localizable.strings")

        config = TranslationConfig(target_languages=["de", "fr"])
        service = TranslationService(config=config, repo_path=temp_dir.parent)

        # Create mock translation results
        results = [
            TranslationResult(
                key="hello",
                source_text="Hello",
                translations={"de": "Hallo", "fr": "Bonjour"}
            ),
            TranslationResult(
                key="goodbye",
                source_text="Goodbye",
                translations={"de": "Auf Wiedersehen", "fr": "Au revoir"}
            ),
        ]

        updated = service._update_target_files(source_file, results, set())

        # Check files were updated
        assert len(updated) == 2

        # Check German file
        de_entries = parser.parse_file(temp_dir / "de.lproj" / "Localizable.strings")
        de_dict = {e.key: e.value for e in de_entries}
        assert de_dict["hello"] == "Hallo"
        assert de_dict["goodbye"] == "Auf Wiedersehen"

        # Check French file
        fr_entries = parser.parse_file(temp_dir / "fr.lproj" / "Localizable.strings")
        fr_dict = {e.key: e.value for e in fr_entries}
        assert fr_dict["hello"] == "Bonjour"
        assert fr_dict["goodbye"] == "Au revoir"

    def test_full_workflow_dry_run(self, temp_dir):
        """Test dry run doesn't modify files."""
        parser = StringsParser()
        source_file = temp_dir / "en.lproj" / "Localizable.strings"
        de_file = temp_dir / "de.lproj" / "Localizable.strings"

        # Create files
        parser.write([StringEntry("test", "Test")], source_file)
        parser.write([StringEntry("test", "Original DE")], de_file)

        original_content = de_file.read_text()

        config = TranslationConfig(target_languages=["de"], dry_run=True)
        service = TranslationService(config=config, repo_path=temp_dir.parent)

        # Mock the detector to return changes
        mock_changes = [StringChange("test", ChangeType.MODIFIED, "Old", "New")]

        with patch.object(service.detector, 'get_translatable_changes', return_value=mock_changes):
            report = service.translate_file(source_file)

        # Verify dry run behavior
        assert report.dry_run is True
        assert len(report.changes_detected) == 1
        assert report.batch_result is None
        assert len(report.files_updated) == 0

        # Verify file wasn't modified
        assert de_file.read_text() == original_content
