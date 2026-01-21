"""Translation engine with multiple backend support."""

import json
from abc import ABC, abstractmethod
from typing import Optional

import requests

from ..config import TranslationConfig, LANGUAGE_NAMES


class TranslationBackend(ABC):
    """Abstract base class for translation backends."""

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """Translate text from source to target language.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated text.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available and ready."""
        pass


class OllamaBackend(TranslationBackend):
    """Ollama-based translation backend using TranslateGemma."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "translategemma:12b"):
        """Initialize the Ollama backend.

        Args:
            url: Ollama API URL.
            model: Model name to use.
        """
        self.url = url.rstrip('/')
        self.model = model

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """Translate text using Ollama.

        Uses the critical prompt format for TranslateGemma which requires
        2 blank lines before the text to translate.
        """
        source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

        # Critical: TranslateGemma requires 2 blank lines before text
        prompt = (
            f"You are a professional {source_name} ({source_lang}) to "
            f"{target_name} ({target_lang}) translator. Translate the "
            f"following text accurately while preserving the meaning and tone. "
            f"Only output the translation, nothing else.\n\n\n{text}"
        )

        response = requests.post(
            f"{self.url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent translations
                }
            },
            timeout=120
        )
        response.raise_for_status()

        result = response.json()
        return result.get("response", "").strip()

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            # Check if Ollama is running
            response = requests.get(f"{self.url}/api/tags", timeout=5)
            response.raise_for_status()

            # Check if our model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Check for exact match or base name match
            base_model = self.model.split(":")[0]
            return any(
                self.model in name or base_model in name
                for name in model_names
            )
        except (requests.RequestException, json.JSONDecodeError):
            return False


class HuggingFaceBackend(TranslationBackend):
    """HuggingFace Transformers-based translation backend."""

    def __init__(self, model_name: str = "google/translategemma-12b-it"):
        """Initialize the HuggingFace backend.

        Args:
            model_name: HuggingFace model identifier.
        """
        self.model_name = model_name
        self._pipeline = None

    def _get_pipeline(self):
        """Lazy load the translation pipeline."""
        if self._pipeline is None:
            try:
                from transformers import pipeline
                self._pipeline = pipeline(
                    "text-generation",
                    model=self.model_name,
                    device_map="auto"
                )
            except ImportError:
                raise RuntimeError(
                    "HuggingFace transformers not installed. "
                    "Install with: pip install transformers torch"
                )
        return self._pipeline

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> str:
        """Translate text using HuggingFace Transformers."""
        source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

        pipe = self._get_pipeline()

        messages = [
            {
                "role": "user",
                "content": (
                    f"Translate the following {source_name} text to {target_name}. "
                    f"Only output the translation:\n\n{text}"
                )
            }
        ]

        result = pipe(
            messages,
            max_new_tokens=512,
            temperature=0.1,
            do_sample=True
        )

        # Extract generated text from result
        generated = result[0]["generated_text"]
        if isinstance(generated, list):
            # Chat format returns list of messages
            return generated[-1]["content"].strip()
        return generated.strip()

    def is_available(self) -> bool:
        """Check if transformers library is available."""
        try:
            import transformers
            return True
        except ImportError:
            return False


class TranslationEngine:
    """Main translation engine that manages backends."""

    def __init__(self, config: Optional[TranslationConfig] = None):
        """Initialize the translation engine.

        Args:
            config: Translation configuration. Uses defaults if not provided.
        """
        self.config = config or TranslationConfig()
        self._backend: Optional[TranslationBackend] = None

    @property
    def backend(self) -> TranslationBackend:
        """Get or create the translation backend."""
        if self._backend is None:
            if self.config.use_huggingface:
                self._backend = HuggingFaceBackend(self.config.hf_model)
            else:
                self._backend = OllamaBackend(
                    self.config.ollama_url,
                    self.config.ollama_model
                )
        return self._backend

    def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> str:
        """Translate text to the target language.

        Args:
            text: Text to translate.
            target_lang: Target language code.
            source_lang: Source language code. Uses config default if not provided.

        Returns:
            Translated text.
        """
        source = source_lang or self.config.source_language
        return self.backend.translate(text, source, target_lang)

    def translate_to_all(
        self,
        text: str,
        source_lang: Optional[str] = None
    ) -> dict[str, str]:
        """Translate text to all configured target languages.

        Args:
            text: Text to translate.
            source_lang: Source language code.

        Returns:
            Dictionary mapping language codes to translations.
        """
        source = source_lang or self.config.source_language
        translations = {}

        for target_lang in self.config.target_languages:
            translations[target_lang] = self.backend.translate(
                text, source, target_lang
            )

        return translations

    def is_available(self) -> bool:
        """Check if the translation backend is available."""
        return self.backend.is_available()
