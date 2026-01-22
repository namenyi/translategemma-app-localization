# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python translation service for Apple `.strings` files using TranslateGemma 12B. Detects changes in English strings via git diff and automatically translates them to target languages.

**Default target languages**: de, fr, es, it, ja, ko, pt-BR, ru, zh-Hans, zh-Hant

**Translation triggers**:
1. Git diff changes (added/modified keys since last commit)
2. Missing translations (keys in English source that don't exist in any target language file)

## Commands

```bash
# Install dependencies
pip install -e .                    # Install package in dev mode
pip install -e ".[dev]"            # Include dev dependencies (pytest)

# Run tests
pytest                              # Run all tests
pytest tests/test_parser.py        # Run specific test file
pytest -v tests/test_parser.py::TestStringEntry::test_escape_sequences  # Single test

# CLI commands (requires Ollama with translategemma:12b)
python -m translator check                          # Verify translation backend
python -m translator parse <file.strings>           # Parse and display entries
python -m translator diff <file.strings>            # Show changes since HEAD~1
python -m translator translate <file.strings> --dry-run  # Preview translations
python -m translator translate <file.strings>       # Execute translations
```

## Architecture

**Core Flow**: `cli.py` → `TranslationService` → `DiffDetector` + `BatchTranslator` → target `.strings` files

Key modules:
- `src/translator/strings/` - Parse/write Apple `.strings` format (UTF-8/UTF-16, escape sequences)
- `src/translator/diff/` - Git-based change detection comparing refs
- `src/translator/translation/` - Translation engine with Ollama and HuggingFace backends
- `src/translator/core/service.py` - Orchestrates diff detection → translation → file updates

**File conventions**: Source files are in `en.lproj/`, targets in `{lang}.lproj/` (e.g., `de.lproj/`, `ja.lproj/`, `zh-Hans.lproj/`)

## TranslateGemma Prompt Format

The Ollama backend uses a specific prompt format required by TranslateGemma - note the **2 blank lines** before the text to translate:

```
You are a professional {source} to {target} translator...

{text}
```

## Testing Notes

- Parser tests use `tempfile` for file I/O tests
- Detector tests require git operations on the repo
- Integration tests are in `tests/test_integration.py`
