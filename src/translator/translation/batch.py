"""Batch translation with progress tracking."""

from dataclasses import dataclass
from typing import Callable, Optional

from ..diff import StringChange
from .engine import TranslationEngine, estimate_tokens

# Overhead tokens for the batch prompt template
BATCH_PROMPT_OVERHEAD = 100


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
        self.max_tokens = engine.config.max_tokens_per_batch

    def _create_batches(
        self,
        items: list[tuple[str, str]]
    ) -> list[list[tuple[str, str]]]:
        """Group items into batches respecting token limits.

        Args:
            items: List of (key, text) tuples to batch.

        Returns:
            List of batches, each batch is a list of (key, text) tuples.
        """
        batches = []
        current_batch = []
        current_tokens = BATCH_PROMPT_OVERHEAD

        for key, text in items:
            # Estimate tokens for this text (add ~5 for "N. " prefix)
            text_tokens = estimate_tokens(text) + 5

            # If single text exceeds limit, it gets its own batch
            if text_tokens > self.max_tokens - BATCH_PROMPT_OVERHEAD:
                # Finish current batch first
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_tokens = BATCH_PROMPT_OVERHEAD
                # Add oversized item as its own batch
                batches.append([(key, text)])
                continue

            # Check if adding this text would exceed the limit
            if current_tokens + text_tokens > self.max_tokens:
                # Start a new batch
                batches.append(current_batch)
                current_batch = [(key, text)]
                current_tokens = BATCH_PROMPT_OVERHEAD + text_tokens
            else:
                # Add to current batch
                current_batch.append((key, text))
                current_tokens += text_tokens

        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)

        return batches

    def translate_changes(
        self,
        changes: list[StringChange],
        progress_callback: Optional[ProgressCallback] = None
    ) -> BatchResult:
        """Translate a list of string changes using token-aware batching.

        Strings are grouped into batches that respect the configured token
        limit (max_tokens_per_batch). Each batch is translated in a single
        request to the backend, reducing total API calls.

        Args:
            changes: List of StringChange objects to translate.
            progress_callback: Optional callback for progress updates.
                Called with (current_index, total_count, current_key).

        Returns:
            BatchResult with all translation results.
        """
        # Filter out changes without new_value and prepare items
        items = [
            (change.key, change.new_value)
            for change in changes
            if change.new_value is not None
        ]

        if not items:
            return BatchResult(results=[], total=0, successful=0, failed=0)

        total = len(items)
        results = []
        successful = 0
        failed = 0
        processed = 0

        # Create token-aware batches
        batches = self._create_batches(items)

        for batch in batches:
            keys = [key for key, _ in batch]
            texts = [text for _, text in batch]

            # Report progress for first item in batch
            if progress_callback:
                progress_callback(processed + 1, total, keys[0])

            try:
                # Translate the entire batch at once
                batch_translations = self.engine.translate_batch_to_all(texts)

                # Process results
                for i, (key, text) in enumerate(batch):
                    results.append(TranslationResult(
                        key=key,
                        source_text=text,
                        translations=batch_translations[i]
                    ))
                    successful += 1
                    processed += 1

                    # Report progress for subsequent items
                    if progress_callback and i > 0:
                        progress_callback(processed, total, key)

            except Exception as e:
                # If batch fails, mark all items in batch as failed
                for key, text in batch:
                    results.append(TranslationResult(
                        key=key,
                        source_text=text,
                        translations={},
                        error=str(e)
                    ))
                    failed += 1
                    processed += 1

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
        """Translate a dictionary of strings using token-aware batching.

        Args:
            strings: Dictionary mapping keys to source text.
            progress_callback: Optional callback for progress updates.

        Returns:
            BatchResult with all translation results.
        """
        items = list(strings.items())

        if not items:
            return BatchResult(results=[], total=0, successful=0, failed=0)

        total = len(items)
        results = []
        successful = 0
        failed = 0
        processed = 0

        # Create token-aware batches
        batches = self._create_batches(items)

        for batch in batches:
            keys = [key for key, _ in batch]
            texts = [text for _, text in batch]

            if progress_callback:
                progress_callback(processed + 1, total, keys[0])

            try:
                batch_translations = self.engine.translate_batch_to_all(texts)

                for i, (key, text) in enumerate(batch):
                    results.append(TranslationResult(
                        key=key,
                        source_text=text,
                        translations=batch_translations[i]
                    ))
                    successful += 1
                    processed += 1

                    if progress_callback and i > 0:
                        progress_callback(processed, total, key)

            except Exception as e:
                for key, text in batch:
                    results.append(TranslationResult(
                        key=key,
                        source_text=text,
                        translations={},
                        error=str(e)
                    ))
                    failed += 1
                    processed += 1

        return BatchResult(
            results=results,
            total=total,
            successful=successful,
            failed=failed
        )
