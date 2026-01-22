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
from translator.translation.engine import estimate_tokens


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


class TestTokenEstimation:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self):
        """Test basic token estimation."""
        # ~4 chars per token
        assert estimate_tokens("Hello") == 1  # 5 chars
        assert estimate_tokens("Hello World") == 2  # 11 chars
        assert estimate_tokens("A" * 100) == 25  # 100 chars

    def test_estimate_tokens_empty(self):
        """Test empty string returns minimum 1 token."""
        assert estimate_tokens("") == 1


class TestBatchGrouping:
    """Tests for batch grouping logic."""

    def test_create_batches_single_item(self):
        """Test single item creates single batch."""
        config = TranslationConfig(target_languages=["de"], max_tokens_per_batch=1000)
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        items = [("key1", "Hello World")]
        batches = batch._create_batches(items)

        assert len(batches) == 1
        assert batches[0] == items

    def test_create_batches_fits_in_one(self):
        """Test multiple small items fit in one batch."""
        config = TranslationConfig(target_languages=["de"], max_tokens_per_batch=1000)
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        items = [("key1", "Hello"), ("key2", "World"), ("key3", "Test")]
        batches = batch._create_batches(items)

        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_create_batches_splits_on_limit(self):
        """Test batches are split when token limit is reached."""
        # Very small limit to force splitting
        config = TranslationConfig(target_languages=["de"], max_tokens_per_batch=150)
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        # Each item is ~25 tokens, overhead is 100, so we can fit ~2 items per batch
        items = [
            ("key1", "A" * 100),
            ("key2", "B" * 100),
            ("key3", "C" * 100),
            ("key4", "D" * 100),
        ]
        batches = batch._create_batches(items)

        assert len(batches) > 1

    def test_create_batches_oversized_item(self):
        """Test oversized item gets its own batch."""
        config = TranslationConfig(target_languages=["de"], max_tokens_per_batch=200)
        engine = TranslationEngine(config)
        batch = BatchTranslator(engine)

        # One item much larger than limit
        items = [
            ("key1", "Hello"),
            ("key2", "A" * 1000),  # Very large
            ("key3", "World"),
        ]
        batches = batch._create_batches(items)

        # Should be at least 2 batches - oversized item separate
        assert len(batches) >= 2
        # Find the batch with the oversized item
        oversized_batch = [b for b in batches if any(k == "key2" for k, _ in b)]
        assert len(oversized_batch) == 1
        assert len(oversized_batch[0]) == 1  # Oversized item alone


class TestBatchTranslation:
    """Tests for batch translation methods."""

    def test_translate_batch_method(self):
        """Test engine.translate_batch method."""
        config = TranslationConfig(target_languages=["de", "fr"])
        engine = TranslationEngine(config)

        with patch.object(engine.backend, 'translate_batch') as mock_batch:
            mock_batch.return_value = ["Hallo", "Welt"]

            result = engine.translate_batch(["Hello", "World"], "de")

            assert result == ["Hallo", "Welt"]
            mock_batch.assert_called_once()

    def test_translate_batch_to_all(self):
        """Test engine.translate_batch_to_all method."""
        config = TranslationConfig(target_languages=["de", "fr"])
        engine = TranslationEngine(config)

        def mock_batch(texts, source, target):
            if target == "de":
                return ["Hallo", "Welt"]
            elif target == "fr":
                return ["Bonjour", "Monde"]
            return texts

        with patch.object(engine.backend, 'translate_batch', side_effect=mock_batch):
            results = engine.translate_batch_to_all(["Hello", "World"])

            assert len(results) == 2
            assert results[0] == {"de": "Hallo", "fr": "Bonjour"}
            assert results[1] == {"de": "Welt", "fr": "Monde"}

    def test_translate_batch_to_all_parallel(self):
        """Test parallel translation across languages."""
        config = TranslationConfig(
            target_languages=["de", "fr"],
            parallel_languages=2
        )
        engine = TranslationEngine(config)

        call_count = {"count": 0}

        def mock_batch(texts, source, target):
            call_count["count"] += 1
            if target == "de":
                return ["Hallo"]
            return ["Bonjour"]

        with patch.object(engine.backend, 'translate_batch', side_effect=mock_batch):
            results = engine.translate_batch_to_all(["Hello"])

            assert len(results) == 1
            assert results[0] == {"de": "Hallo", "fr": "Bonjour"}
            assert call_count["count"] == 2  # Both languages translated


class TestOllamaBatchTranslation:
    """Tests for OllamaBackend batch translation."""

    def test_parse_numbered_output(self):
        """Test parsing numbered translation output."""
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)
        backend = engine.backend

        output = "1. Hallo\n2. Welt\n3. Test"
        result = backend._parse_numbered_output(output, 3)

        assert result == ["Hallo", "Welt", "Test"]

    def test_parse_numbered_output_with_colons(self):
        """Test parsing output with colon format."""
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)
        backend = engine.backend

        output = "1: Hallo\n2: Welt"
        result = backend._parse_numbered_output(output, 2)

        assert result == ["Hallo", "Welt"]

    def test_parse_numbered_output_wrong_count(self):
        """Test parsing fails with wrong count."""
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)
        backend = engine.backend

        output = "1. Hallo\n2. Welt"
        result = backend._parse_numbered_output(output, 3)  # Expecting 3

        assert result is None

    def test_translate_batch_fallback(self):
        """Test batch translation falls back to individual on failure."""
        import requests as req
        config = TranslationConfig(target_languages=["de"])
        engine = TranslationEngine(config)

        call_count = {"single": 0}

        def mock_translate(text, source, target):
            call_count["single"] += 1
            return f"translated_{text}"

        # Mock requests.post to fail for batch with RequestException
        def mock_post(*args, **kwargs):
            raise req.RequestException("Network error")

        with patch('translator.translation.engine.requests.post', mock_post):
            with patch.object(engine.backend, 'translate', mock_translate):
                result = engine.backend.translate_batch(["Hello", "World"], "en", "de")

        # Should fall back to individual translations
        assert result == ["translated_Hello", "translated_World"]
        assert call_count["single"] == 2
