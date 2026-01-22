# Apple Strings Translation Service

Automatically translate your iOS/macOS `.strings` files using AI. This service detects changes in your English strings and translates them to multiple languages using TranslateGemma 12B.

## What It Does

- Monitors your English `.strings` files for changes via git
- Automatically translates new or modified strings to target languages
- Detects missing translations when you add new languages
- Preserves comments and formatting in your localization files

## Supported Languages

German, French, Spanish, Italian, Japanese, Korean, Brazilian Portuguese, Russian, Simplified Chinese, and Traditional Chinese.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with the TranslateGemma model

## Quick Start

1. **Install Ollama and pull the translation model:**
   ```bash
   ollama pull translategemma:12b
   ollama serve
   ```

2. **Install the translation service:**
   ```bash
   pip install -e .
   ```

3. **Preview what will be translated:**
   ```bash
   python -m translator translate path/to/en.lproj/Localizable.strings --dry-run
   ```

4. **Run the translation:**
   ```bash
   python -m translator translate path/to/en.lproj/Localizable.strings
   ```

## How It Works

1. You make changes to your English `.strings` file and commit them
2. The service compares your current commit to the previous one
3. It identifies which strings were added or modified
4. It also checks if any target language files are missing translations
5. All identified strings are translated and written to the appropriate language files

## CLI Options

```bash
python -m translator translate <file> [options]

Options:
  --base TEXT        Git ref to compare against (default: HEAD~1)
  --dry-run          Preview changes without modifying files
  -l, --languages    Target languages (default: de,fr,es,it,ja,ko,pt-BR,ru,zh-Hans,zh-Hant)
  -v, --verbose      Show detailed output
```

## Other Commands

```bash
# Check if translation backend is ready
python -m translator check

# View parsed entries from a strings file
python -m translator parse path/to/Localizable.strings

# Show what changed since last commit
python -m translator diff path/to/en.lproj/Localizable.strings
```

## File Structure

The service expects the standard Apple localization structure:

```
Localizations/
├── en.lproj/
│   └── Localizable.strings    # Source (English)
├── de.lproj/
│   └── Localizable.strings    # German translations
├── fr.lproj/
│   └── Localizable.strings    # French translations
└── ...
```

## Adding a New Language

1. Create the language directory: `mkdir ja.lproj`
2. Create an empty strings file: `touch ja.lproj/Localizable.strings`
3. Run the translator - it will detect all keys as missing and translate them

## License

MIT
