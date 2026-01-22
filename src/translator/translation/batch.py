"""Batch translation with progress tracking."""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..diff import StringChange
from .engine import TranslationEngine, estimate_tokens

# Overhead tokens for the batch prompt template
BATCH_PROMPT_OVERHEAD = 100


@dataclass
class BatchProgress:
    """Progress information for batch translation.

    Attributes:
        current_batch: Current batch number (1-indexed).
        total_batches: Total number of batches.
        strings_completed: Number of strings completed so far.
        total_strings: Total number of strings to translate.
        elapsed_seconds: Time elapsed since start.
        current_key: Key currently being processed.
    """
    current_batch: int
    total_batches: int
    strings_completed: int
    total_strings: int
    elapsed_seconds: float
    current_key: str

    @property
    def percent_complete(self) -> float:
        """Calculate percentage complete."""
        if self.total_strings == 0:
            return 100.0
        return (self.strings_completed / self.total_strings) * 100

    @property
    def elapsed_formatted(self) -> str:
        """Format elapsed time as mm:ss or hh:mm:ss."""
        total_secs = int(self.elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


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
BatchProgressCallback = Callable[[BatchProgress], None]
BatchCompleteCallback = Callable[[list[TranslationResult]], None]


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
        progress_callback: Optional[ProgressCallback] = None,
        batch_progress_callback: Optional[BatchProgressCallback] = None,
        on_batch_complete: Optional[BatchCompleteCallback] = None
    ) -> BatchResult:
        """Translate a list of string changes using token-aware batching.

        Strings are grouped into batches that respect the configured token
        limit (max_tokens_per_batch). Each batch is translated in a single
        request to the backend, reducing total API calls.

        Args:
            changes: List of StringChange objects to translate.
            progress_callback: Optional callback for progress updates.
                Called with (current_index, total_count, current_key).
            batch_progress_callback: Optional callback for batch-level progress.
                Called with BatchProgress containing timing and batch info.
            on_batch_complete: Optional callback called after each batch completes.
                Receives list of TranslationResult for that batch. Use for
                incremental file writes.

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
        start_time = time.time()

        # Create token-aware batches
        batches = self._create_batches(items)
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            keys = [key for key, _ in batch]
            texts = [text for _, text in batch]
            batch_results = []

            # Report batch-level progress
            if batch_progress_callback:
                elapsed = time.time() - start_time
                batch_progress_callback(BatchProgress(
                    current_batch=batch_num,
                    total_batches=total_batches,
                    strings_completed=processed,
                    total_strings=total,
                    elapsed_seconds=elapsed,
                    current_key=keys[0]
                ))

            # Report per-string progress for first item in batch
            if progress_callback:
                progress_callback(processed + 1, total, keys[0])

            try:
                # Translate the entire batch at once
                batch_translations = self.engine.translate_batch_to_all(texts)

                # Process results
                for i, (key, text) in enumerate(batch):
                    result = TranslationResult(
                        key=key,
                        source_text=text,
                        translations=batch_translations[i]
                    )
                    results.append(result)
                    batch_results.append(result)
                    successful += 1
                    processed += 1

                    # Report progress for subsequent items
                    if progress_callback and i > 0:
                        progress_callback(processed, total, key)

            except Exception as e:
                # If batch fails, mark all items in batch as failed
                for key, text in batch:
                    result = TranslationResult(
                        key=key,
                        source_text=text,
                        translations={},
                        error=str(e)
                    )
                    results.append(result)
                    batch_results.append(result)
                    failed += 1
                    processed += 1

            # Call batch complete callback for incremental writes
            if on_batch_complete and batch_results:
                on_batch_complete(batch_results)

        return BatchResult(
            results=results,
            total=total,
            successful=successful,
            failed=failed
        )

    def translate_dict(
        self,
        strings: dict[str, str],
        progress_callback: Optional[ProgressCallback] = None,
        batch_progress_callback: Optional[BatchProgressCallback] = None,
        on_batch_complete: Optional[BatchCompleteCallback] = None
    ) -> BatchResult:
        """Translate a dictionary of strings using token-aware batching.

        Args:
            strings: Dictionary mapping keys to source text.
            progress_callback: Optional callback for progress updates.
            batch_progress_callback: Optional callback for batch-level progress.
            on_batch_complete: Optional callback for incremental file writes.

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
        start_time = time.time()

        # Create token-aware batches
        batches = self._create_batches(items)
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            keys = [key for key, _ in batch]
            texts = [text for _, text in batch]
            batch_results = []

            if batch_progress_callback:
                elapsed = time.time() - start_time
                batch_progress_callback(BatchProgress(
                    current_batch=batch_num,
                    total_batches=total_batches,
                    strings_completed=processed,
                    total_strings=total,
                    elapsed_seconds=elapsed,
                    current_key=keys[0]
                ))

            if progress_callback:
                progress_callback(processed + 1, total, keys[0])

            try:
                batch_translations = self.engine.translate_batch_to_all(texts)

                for i, (key, text) in enumerate(batch):
                    result = TranslationResult(
                        key=key,
                        source_text=text,
                        translations=batch_translations[i]
                    )
                    results.append(result)
                    batch_results.append(result)
                    successful += 1
                    processed += 1

                    if progress_callback and i > 0:
                        progress_callback(processed, total, key)

            except Exception as e:
                for key, text in batch:
                    result = TranslationResult(
                        key=key,
                        source_text=text,
                        translations={},
                        error=str(e)
                    )
                    results.append(result)
                    batch_results.append(result)
                    failed += 1
                    processed += 1

            if on_batch_complete and batch_results:
                on_batch_complete(batch_results)

        return BatchResult(
            results=results,
            total=total,
            successful=successful,
            failed=failed
        )
