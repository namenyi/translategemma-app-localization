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
        └── fr.lproj/Localizable.strings
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
- Critical prompt format (must include 2 blank lines before text):
  ```
  You are a professional English (en) to German (de) translator...


  {text}
  ```

**HuggingFace backend** (alternative):
- Model: `google/translategemma-12b-it`
- Uses transformers chat template

### Main Service (`src/translator/core/service.py`)

Orchestration flow:
1. Detect changed keys (added/modified) via git diff
2. Translate each changed key to all target languages
3. Update target .strings files (add new keys, update modified, remove deleted)

### CLI (`src/translator/cli.py`)

Commands:
- `translate <file> [--base HEAD~1] [--dry-run] [--languages de,fr]`
- `diff <file> [--base HEAD~1]` - show changed keys
- `parse <file>` - display parsed entries
- `check` - verify translation backend is available

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
2. Run `translate --dry-run` (should show no changes)
3. Add/modify some English keys, commit
4. Run `translate --dry-run` (should list changed keys)
5. Run `translate` (should update de.lproj and fr.lproj files)
6. Verify translated content is reasonable
