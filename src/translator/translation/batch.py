"""Batch translation with progress tracking."""

from dataclasses import dataclass
from typing import Callable, Optional

from ..diff import StringChange
from .engine import TranslationEngine


@dataclass
class TranslationResult:
    """Result of translating a single string.

    Attributes:
        key: The string key.
        source_text: Original source text.
        translations: Dictionary mapping language codes to translated text.
        error: Error message if translation failed.
    """
    key: str
    source_text: str
    translations: dict[str, str]
    error: Optional[str] = None


@dataclass
class BatchResult:
    """Result of batch translation.

    Attributes:
        results: List of individual translation results.
        total: Total number of strings to translate.
        successful: Number of successful translations.
        failed: Number of failed translations.
    """
    results: list[TranslationResult]
    total: int
    successful: int
    failed: int


ProgressCallback = Callable[[int, int, str], None]


class BatchTranslator:
    """Handles batch translation of multiple strings."""

    def __init__(self, engine: TranslationEngine):
        """Initialize the batch translator.

        Args:
            engine: Translation engine to use.
        """
        self.engine = engine

    def translate_changes(
        self,
        changes: list[StringChange],
        progress_callback: Optional[ProgressCallback] = None
    ) -> BatchResult:
        """Translate a list of string changes.

        Args:
            changes: List of StringChange objects to translate.
            progress_callback: Optional callback for progress updates.
                Called with (current_index, total_count, current_key).

        Returns:
            BatchResult with all translation results.
        """
        results = []
        successful = 0
        failed = 0
        total = len(changes)

        for i, change in enumerate(changes):
            if progress_callback:
                progress_callback(i + 1, total, change.key)

            # Get the text to translate (new_value for added/modified)
            source_text = change.new_value
            if source_text is None:
                continue

            try:
                translations = self.engine.translate_to_all(source_text)
                results.append(TranslationResult(
                    key=change.key,
                    source_text=source_text,
                    translations=translations
                ))
                successful += 1
            except Exception as e:
                results.append(TranslationResult(
                    key=change.key,
                    source_text=source_text,
                    translations={},
                    error=str(e)
                ))
                failed += 1

        return BatchResult(
            results=results,
            total=total,
            successful=successful,
            failed=failed
        )

    def translate_dict(
        self,
        strings: dict[str, str],
        progress_callback: Optional[ProgressCallback] = None
    ) -> BatchResult:
        """Translate a dictionary of strings.

        Args:
            strings: Dictionary mapping keys to source text.
            progress_callback: Optional callback for progress updates.

        Returns:
            BatchResult with all translation results.
        """
        results = []
        successful = 0
        failed = 0
        total = len(strings)

        for i, (key, source_text) in enumerate(strings.items()):
            if progress_callback:
                progress_callback(i + 1, total, key)

            try:
                translations = self.engine.translate_to_all(source_text)
                results.append(TranslationResult(
                    key=key,
                    source_text=source_text,
                    translations=translations
                ))
                successful += 1
            except Exception as e:
                results.append(TranslationResult(
                    key=key,
                    source_text=source_text,
                    translations={},
                    error=str(e)
                ))
                failed += 1

        return BatchResult(
            results=results,
            total=total,
            successful=successful,
            failed=failed
        )
