"""Translation engine with multiple backend support."""

import json
import re
from abc import ABC, abstractmethod
from typing import Optional

import requests

from ..config import TranslationConfig, LANGUAGE_NAMES


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text.

    Uses a conservative estimate of ~4 characters per token for English.
    This is a rough approximation; actual tokenization varies by model.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4)


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

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str
    ) -> list[str]:
        """Translate multiple texts in a single request.

        Uses a numbered format to batch multiple strings together:
        Input: "1. text1\n2. text2\n..."
        Output: "1. translation1\n2. translation2\n..."

        If batch translation fails or returns wrong count, falls back to
        single-string translation for each text.

        Args:
            texts: List of texts to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            List of translated texts in the same order.
        """
        if len(texts) == 0:
            return []

        if len(texts) == 1:
            return [self.translate(texts[0], source_lang, target_lang)]

        source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

        # Build numbered input
        numbered_input = "\n".join(
            f"{i+1}. {text}" for i, text in enumerate(texts)
        )

        # Batch translation prompt with numbered format
        prompt = (
            f"You are a professional {source_name} ({source_lang}) to "
            f"{target_name} ({target_lang}) translator. Translate each numbered "
            f"line below accurately while preserving the meaning and tone. "
            f"Output ONLY the translations in the same numbered format.\n\n\n"
            f"{numbered_input}"
        )

        try:
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                    }
                },
                timeout=180  # Longer timeout for batch
            )
            response.raise_for_status()

            result = response.json()
            output = result.get("response", "").strip()

            # Parse numbered output
            translations = self._parse_numbered_output(output, len(texts))

            if translations is not None:
                return translations

        except (requests.RequestException, json.JSONDecodeError):
            pass

        # Fallback: translate individually if batch failed
        return [
            self.translate(text, source_lang, target_lang)
            for text in texts
        ]

    def _parse_numbered_output(
        self,
        output: str,
        expected_count: int
    ) -> Optional[list[str]]:
        """Parse numbered translation output.

        Args:
            output: The model's response text.
            expected_count: Expected number of translations.

        Returns:
            List of translations if parsing succeeded, None otherwise.
        """
        # Match lines starting with "N. " or "N: " or just "N."
        pattern = r'^(\d+)[.\s:]+\s*(.+?)$'
        translations = {}

        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if match:
                idx = int(match.group(1))
                text = match.group(2).strip()
                if 1 <= idx <= expected_count:
                    translations[idx] = text

        # Check if we got all expected translations
        if len(translations) == expected_count:
            return [translations[i+1] for i in range(expected_count)]

        return None

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

    def translate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> list[str]:
        """Translate multiple texts to a single target language.

        Args:
            texts: List of texts to translate.
            target_lang: Target language code.
            source_lang: Source language code.

        Returns:
            List of translated texts in the same order.
        """
        source = source_lang or self.config.source_language

        if hasattr(self.backend, 'translate_batch'):
            return self.backend.translate_batch(texts, source, target_lang)

        # Fallback for backends without batch support
        return [
            self.backend.translate(text, source, target_lang)
            for text in texts
        ]

    def translate_batch_to_all(
        self,
        texts: list[str],
        source_lang: Optional[str] = None
    ) -> list[dict[str, str]]:
        """Translate multiple texts to all configured target languages.

        Args:
            texts: List of texts to translate.
            source_lang: Source language code.

        Returns:
            List of dictionaries, each mapping language codes to translations.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        source = source_lang or self.config.source_language
        target_languages = self.config.target_languages
        parallel = self.config.parallel_languages

        # Initialize result structure
        results = [{} for _ in texts]

        if parallel > 0:
            # Parallel translation across languages
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(
                        self.translate_batch, texts, lang, source
                    ): lang
                    for lang in target_languages
                }

                for future in as_completed(futures):
                    lang = futures[future]
                    translations = future.result()
                    for i, trans in enumerate(translations):
                        results[i][lang] = trans
        else:
            # Sequential translation
            for lang in target_languages:
                translations = self.translate_batch(texts, lang, source)
                for i, trans in enumerate(translations):
                    results[i][lang] = trans

        return results

    def is_available(self) -> bool:
        """Check if the translation backend is available."""
        return self.backend.is_available()
