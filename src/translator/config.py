"""Configuration for the translation service."""

from dataclasses import dataclass, field
from typing import Optional


# Language code mappings for TranslateGemma
LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
}


@dataclass
class TranslationConfig:
    """Configuration for the translation service.

    Attributes:
        source_language: Source language code (default: "en").
        target_languages: List of target language codes.
        ollama_url: URL for Ollama API.
        ollama_model: Model name for Ollama.
        use_huggingface: Whether to use HuggingFace backend instead of Ollama.
        hf_model: HuggingFace model name.
        dry_run: If True, don't actually modify files.
        verbose: If True, print detailed output.
    """
    source_language: str = "en"
    target_languages: list[str] = field(default_factory=lambda: ["de", "fr"])
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "translategemma:12b"
    use_huggingface: bool = False
    hf_model: str = "google/translategemma-12b-it"
    dry_run: bool = False
    verbose: bool = False

    def get_language_name(self, code: str) -> str:
        """Get the full language name for a language code.

        Args:
            code: Language code (e.g., "de").

        Returns:
            Full language name (e.g., "German").
        """
        return LANGUAGE_NAMES.get(code, code)


@dataclass
class LocalizationPaths:
    """Paths configuration for localization files.

    Attributes:
        base_dir: Base directory containing .lproj folders.
        source_file: Name of the source strings file.
    """
    base_dir: str
    source_file: str = "Localizable.strings"

    def get_source_path(self, source_lang: str = "en") -> str:
        """Get path to the source language file."""
        return f"{self.base_dir}/{source_lang}.lproj/{self.source_file}"

    def get_target_path(self, target_lang: str) -> str:
        """Get path to a target language file."""
        return f"{self.base_dir}/{target_lang}.lproj/{self.source_file}"
