# Translation Service for Apple .strings Files

## Overview

Python-based translation service that uses TranslateGemma 12B to automatically translate modified English strings to target languages, with git diff-based change detection.

## Project Structure

```
translation-service/
├── pyproject.toml
├── requirements.txt
├── src/translator/
│   ├── __init__.py
│   ├── cli.py                    # CLI entry point (Click)
│   ├── config.py                 # Configuration dataclass
│   ├── strings/
│   │   ├── parser.py             # .strings file parsing/writing
│   │   └── models.py             # StringEntry dataclass
│   ├── diff/
│   │   └── detector.py           # Git diff detection
│   ├── translation/
│   │   ├── engine.py             # TranslateGemma wrapper (Ollama + HF backends)
│   │   └── batch.py              # Batch translation with progress
│   └── core/
│       └── service.py            # Main orchestration
├── tests/
│   ├── test_parser.py
│   ├── test_detector.py
│   └── fixtures/
└── demo_app/                     # Dummy SwiftUI structure for testing
    └── DemoApp/Resources/Localizations/
        ├── en.lproj/Localizable.strings
        ├── de.lproj/Localizable.strings
        ├── fr.lproj/Localizable.strings
        ├── es.lproj/Localizable.strings
        ├── it.lproj/Localizable.strings
        ├── ja.lproj/Localizable.strings
        ├── ko.lproj/Localizable.strings
        ├── pt-BR.lproj/Localizable.strings
        ├── ru.lproj/Localizable.strings
        ├── zh-Hans.lproj/Localizable.strings
        └── zh-Hant.lproj/Localizable.strings
```

## Implementation Details

### Strings Parser (`src/translator/strings/parser.py`)

- Parse Apple .strings format: `"key" = "value";`
- Handle UTF-16 (standard iOS) and UTF-8 encoding
- Handle escape sequences: `\n`, `\r`, `\"`, `\\`
- Preserve comments (`/* ... */`)
- Write back to .strings format

### Git Diff Detector (`src/translator/diff/detector.py`)

- Compare .strings files between two commits using `git show`
- Parse both versions into dictionaries
- Return list of changes: added, modified, removed keys

### Translation Engine (`src/translator/translation/engine.py`)

**Ollama backend** (for local PoC):
- Model: `translategemma:12b` via `http://localhost:11434/api/generate`
- Single-string prompt format (2 blank lines before text):
  ```
  You are a professional English (en) to German (de) translator...


  {text}
  ```
- Batch prompt format (multiple strings in one request):
  ```
  You are a professional English (en) to German (de) translator. Translate each numbered line...


  1. {text1}
  2. {text2}
  ```

**Token-aware batching:**
- TranslateGemma has 2K token context window
- Strings grouped into batches respecting `max_tokens_per_batch` (default: 1000)
- Token estimation: ~4 characters per token
- Oversized strings automatically get their own batch
- Fallback to single-string mode if batch response parsing fails

**Parallel translation:**
- `parallel_languages` config controls concurrent language translations
- Uses `ThreadPoolExecutor` for parallel HTTP requests to Ollama

**HuggingFace backend** (alternative):
- Model: `google/translategemma-12b-it`
- Uses transformers chat template

### Batch Translator (`src/translator/translation/batch.py`)

- Groups strings into token-limited batches via `_create_batches()`
- Calls `TranslationEngine.translate_batch_to_all()` for each batch
- Progress callback reports per-string progress within batches
- Failed batches mark all contained strings as errors

### Main Service (`src/translator/core/service.py`)

Orchestration flow:
1. Detect changed keys (added/modified) via git diff
2. Detect missing translations (keys in source but absent from any target language)
3. Merge changes (git changes + missing translations, avoiding duplicates)
4. Group strings into batches and translate to all target languages
5. Update target .strings files (add new keys, update modified, remove deleted)

### CLI (`src/translator/cli.py`)

Commands:
- `translate <file> [options]` - translate changed/missing strings
  - `--base HEAD~1` - git ref to compare against
  - `--dry-run` - preview without modifying files
  - `--languages de,fr,...` - target language codes
  - `--batch-tokens 1000` - max tokens per batch (for context window limits)
  - `--parallel 0` - languages to translate in parallel (0=sequential)
  - `-v, --verbose` - detailed output
- `diff <file> [--base HEAD~1]` - show changed keys
- `parse <file>` - display parsed entries
- `check` - verify translation backend is available

Default target languages: de, fr, es, it, ja, ko, pt-BR, ru, zh-Hans, zh-Hant

## Dependencies

```
click>=8.1.0
requests>=2.31.0
unidiff>=0.7.5
pytest>=7.4.0
```

## Usage

```bash
# Prerequisites: Ollama running with translategemma:12b
ollama pull translategemma:12b

# Dry run - see what would be translated
python -m translator translate demo_app/.../en.lproj/Localizable.strings --dry-run

# Translate changes since last commit
python -m translator translate demo_app/.../en.lproj/Localizable.strings

# Translate changes between specific commits
python -m translator translate demo_app/.../en.lproj/Localizable.strings --base abc123
```

## Verification Plan

1. Create initial English strings, commit
2. Run `translate --dry-run` (should show no changes if all target files are in sync)
3. Add/modify some English keys, commit
4. Run `translate --dry-run` (should list changed keys)
5. Run `translate` (should update all target language .lproj files)
6. Verify translated content is reasonable
7. Add a new target language (empty .lproj file) and run `translate` - should detect all keys as missing and translate them
