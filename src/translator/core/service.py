"""Main translation service orchestration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..config import TranslationConfig
from ..diff import DiffDetector, StringChange, ChangeType
from ..strings import StringsParser
from ..translation import TranslationEngine, BatchTranslator
from ..translation.batch import BatchResult, TranslationResult


@dataclass
class TranslationReport:
    """Report of a translation run.

    Attributes:
        source_file: Path to the source file.
        changes_detected: List of changes detected.
        batch_result: Result of batch translation (None if dry_run).
        files_updated: List of files that were updated.
        dry_run: Whether this was a dry run.
    """
    source_file: Path
    changes_detected: list[StringChange]
    batch_result: Optional[BatchResult]
    files_updated: list[Path]
    dry_run: bool


ProgressCallback = Callable[[int, int, str], None]


class TranslationService:
    """Main service that orchestrates the translation workflow."""

    def __init__(
        self,
        config: Optional[TranslationConfig] = None,
        repo_path: Optional[Path] = None
    ):
        """Initialize the translation service.

        Args:
            config: Translation configuration.
            repo_path: Path to the git repository.
        """
        self.config = config or TranslationConfig()
        self.repo_path = repo_path or Path.cwd()
        self.parser = StringsParser()
        self.detector = DiffDetector(self.repo_path)
        self.engine = TranslationEngine(self.config)
        self.batch_translator = BatchTranslator(self.engine)

    def translate_file(
        self,
        source_file: Path,
        base_ref: str = "HEAD~1",
        progress_callback: Optional[ProgressCallback] = None
    ) -> TranslationReport:
        """Translate changes in a source file to all target languages.

        Args:
            source_file: Path to the source .strings file.
            base_ref: Git reference to compare against.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranslationReport with results.
        """
        # Detect git changes
        git_changes = self.detector.get_translatable_changes(
            source_file,
            base_ref=base_ref,
            head_ref="HEAD"
        )

        # Detect missing translations in target languages
        missing_changes = self._detect_missing_translations(source_file)

        # Merge changes, avoiding duplicates (git changes take precedence)
        git_keys = {c.key for c in git_changes}
        unique_missing = [c for c in missing_changes if c.key not in git_keys]
        changes = git_changes + unique_missing

        if not changes:
            return TranslationReport(
                source_file=source_file,
                changes_detected=[],
                batch_result=None,
                files_updated=[],
                dry_run=self.config.dry_run
            )

        if self.config.dry_run:
            return TranslationReport(
                source_file=source_file,
                changes_detected=changes,
                batch_result=None,
                files_updated=[],
                dry_run=True
            )

        # Translate changes
        batch_result = self.batch_translator.translate_changes(
            changes,
            progress_callback=progress_callback
        )

        # Get removals
        all_changes = self.detector.detect_changes(
            source_file,
            base_ref=base_ref,
            head_ref="HEAD"
        )
        removed_keys = {
            c.key for c in all_changes
            if c.change_type == ChangeType.REMOVED
        }

        # Update target files
        files_updated = self._update_target_files(
            source_file,
            batch_result.results,
            removed_keys
        )

        return TranslationReport(
            source_file=source_file,
            changes_detected=changes,
            batch_result=batch_result,
            files_updated=files_updated,
            dry_run=False
        )

    def translate_from_working_tree(
        self,
        source_file: Path,
        base_ref: str = "HEAD",
        progress_callback: Optional[ProgressCallback] = None
    ) -> TranslationReport:
        """Translate changes between a ref and the current working tree.

        Args:
            source_file: Path to the source .strings file.
            base_ref: Git reference to compare against.
            progress_callback: Optional callback for progress updates.

        Returns:
            TranslationReport with results.
        """
        # Detect changes from working tree
        all_changes = self.detector.detect_changes_from_working_tree(
            source_file,
            base_ref=base_ref
        )

        # Filter to translatable changes
        git_translatable = [
            c for c in all_changes
            if c.change_type in (ChangeType.ADDED, ChangeType.MODIFIED)
        ]

        # Detect missing translations in target languages
        missing_changes = self._detect_missing_translations(source_file)

        # Merge changes, avoiding duplicates
        git_keys = {c.key for c in git_translatable}
        unique_missing = [c for c in missing_changes if c.key not in git_keys]
        translatable = git_translatable + unique_missing

        if not translatable:
            return TranslationReport(
                source_file=source_file,
                changes_detected=[],
                batch_result=None,
                files_updated=[],
                dry_run=self.config.dry_run
            )

        if self.config.dry_run:
            return TranslationReport(
                source_file=source_file,
                changes_detected=translatable,
                batch_result=None,
                files_updated=[],
                dry_run=True
            )

        # Translate changes
        batch_result = self.batch_translator.translate_changes(
            translatable,
            progress_callback=progress_callback
        )

        # Get removals
        removed_keys = {
            c.key for c in all_changes
            if c.change_type == ChangeType.REMOVED
        }

        # Update target files
        files_updated = self._update_target_files(
            source_file,
            batch_result.results,
            removed_keys
        )

        return TranslationReport(
            source_file=source_file,
            changes_detected=translatable,
            batch_result=batch_result,
            files_updated=files_updated,
            dry_run=False
        )

    def _detect_missing_translations(
        self,
        source_file: Path
    ) -> list[StringChange]:
        """Detect keys that exist in source but are missing in any target language.

        Args:
            source_file: Path to the source .strings file.

        Returns:
            List of StringChange objects for missing entries (as ADDED).
        """
        # Parse source file to get all keys
        source_entries = self.parser.parse_file(source_file)
        source_dict = {e.key: e for e in source_entries}
        source_keys = set(source_dict.keys())

        if not source_keys:
            return []

        # Determine target file paths
        source_path = Path(source_file)
        lproj_dir = source_path.parent
        base_dir = lproj_dir.parent
        file_name = source_path.name

        # Find all keys missing in any target language
        missing_keys: set[str] = set()

        for target_lang in self.config.target_languages:
            target_path = base_dir / f"{target_lang}.lproj" / file_name

            if target_path.exists():
                target_entries = self.parser.parse_file(target_path)
                target_keys = {e.key for e in target_entries}
            else:
                target_keys = set()

            # Keys in source but not in target
            lang_missing = source_keys - target_keys
            missing_keys.update(lang_missing)

        # Create StringChange objects for missing keys
        changes = []
        for key in missing_keys:
            entry = source_dict[key]
            changes.append(StringChange(
                key=key,
                change_type=ChangeType.ADDED,
                new_value=entry.value
            ))

        return changes

    def _update_target_files(
        self,
        source_file: Path,
        results: list[TranslationResult],
        removed_keys: set[str]
    ) -> list[Path]:
        """Update target language files with translations.

        Args:
            source_file: Path to the source file (to determine target paths).
            results: List of translation results.
            removed_keys: Set of keys to remove.

        Returns:
            List of paths that were updated.
        """
        updated_files = []

        # Determine base directory (parent of xx.lproj)
        source_path = Path(source_file)
        lproj_dir = source_path.parent  # e.g., en.lproj
        base_dir = lproj_dir.parent  # e.g., Localizations
        file_name = source_path.name  # e.g., Localizable.strings

        for target_lang in self.config.target_languages:
            target_dir = base_dir / f"{target_lang}.lproj"
            target_path = target_dir / file_name

            # Collect updates for this language
            updates = {}
            for result in results:
                if result.error:
                    continue
                translation = result.translations.get(target_lang)
                if translation:
                    updates[result.key] = translation

            if not updates and not removed_keys:
                continue

            # Load existing entries or create empty list
            if target_path.exists():
                existing = self.parser.parse_file(target_path)
            else:
                existing = []

            # Update entries
            updated = self.parser.update_entries(
                existing,
                updates,
                removed_keys
            )

            # Write back
            self.parser.write(updated, target_path)
            updated_files.append(target_path)

        return updated_files

    def is_ready(self) -> tuple[bool, str]:
        """Check if the service is ready to translate.

        Returns:
            Tuple of (is_ready, message).
        """
        if not self.engine.is_available():
            return False, (
                f"Translation backend not available. "
                f"Make sure Ollama is running with {self.config.ollama_model}"
            )
        return True, "Ready"
