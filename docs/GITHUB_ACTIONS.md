# GitHub Actions Integration (Phase 2)

## Overview

Automated translation workflow that triggers when English .strings files are modified, translates changes using a self-hosted GPU runner, and commits the results.

## Workflow Configuration

```yaml
name: Auto-translate strings

on:
  push:
    paths:
      - '**/en.lproj/*.strings'

jobs:
  translate:
    runs-on: [self-hosted, gpu]
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Need previous commit for diff

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .

      - name: Pull translation model
        run: ollama pull translategemma:12b

      - name: Translate changed strings
        run: |
          python -m translator translate \
            path/to/en.lproj/Localizable.strings \
            --base ${{ github.event.before }}

      - name: Commit translations
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "Auto-translate strings"
          git push
```

## Requirements

### Self-hosted Runner Setup

1. **GPU Requirements**: NVIDIA GPU with sufficient VRAM for TranslateGemma 12B (~24GB recommended)

2. **Software Prerequisites**:
   - Docker or Ollama installed
   - NVIDIA drivers and CUDA toolkit
   - Python 3.10+

3. **Runner Labels**: Configure runner with labels `self-hosted` and `gpu`

### Repository Configuration

1. **Branch Protection**: Consider allowing the bot to push to protected branches or use a separate translation branch

2. **Secrets**: No secrets required for local Ollama; add HuggingFace token if using that backend

## Alternative: PR-based Workflow

For more control, create translations as a PR instead of direct commits:

```yaml
- name: Create Pull Request
  uses: peter-evans/create-pull-request@v5
  with:
    title: "Auto-translate strings"
    body: "Automated translation of changed English strings"
    branch: auto-translate/${{ github.sha }}
    commit-message: "Auto-translate strings"
```

## Monitoring

- Check workflow runs in the Actions tab
- Failed translations will show in the workflow logs
- Consider adding Slack/email notifications for failures
