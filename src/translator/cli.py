"""CLI entry point for the translation service."""

from pathlib import Path

import click

from .config import TranslationConfig
from .core import TranslationService
from .diff import DiffDetector, ChangeType
from .strings import StringsParser


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Translation service for Apple .strings files using TranslateGemma."""
    pass


@cli.command()
@click.argument('file', type=click.Path(exists=True, path_type=Path))
@click.option('--base', default='HEAD~1', help='Base git reference to compare against')
@click.option('--dry-run', is_flag=True, help='Show what would be translated without making changes')
@click.option('--languages', '-l', default='de,fr,es,it,ja,ko,pt-BR,ru,zh-Hans,zh-Hant', help='Comma-separated target language codes')
@click.option('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
@click.option('--model', default='translategemma:12b', help='Ollama model name')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def translate(
    file: Path,
    base: str,
    dry_run: bool,
    languages: str,
    ollama_url: str,
    model: str,
    verbose: bool
):
    """Translate changes in a .strings file to target languages.

    FILE is the path to the source .strings file (e.g., en.lproj/Localizable.strings).
    """
    target_langs = [lang.strip() for lang in languages.split(',')]

    config = TranslationConfig(
        target_languages=target_langs,
        ollama_url=ollama_url,
        ollama_model=model,
        dry_run=dry_run,
        verbose=verbose
    )

    service = TranslationService(config=config)

    # Check if service is ready
    if not dry_run:
        ready, message = service.is_ready()
        if not ready:
            click.secho(f"Error: {message}", fg='red', err=True)
            raise SystemExit(1)

    def progress_callback(current: int, total: int, key: str):
        if verbose:
            click.echo(f"  [{current}/{total}] Translating: {key}")

    click.echo(f"Analyzing changes in {file}...")
    click.echo(f"Comparing against: {base}")
    click.echo(f"Target languages: {', '.join(target_langs)}")
    click.echo()

    report = service.translate_file(
        file,
        base_ref=base,
        progress_callback=progress_callback
    )

    # Display results
    if not report.changes_detected:
        click.secho("No changes detected.", fg='yellow')
        return

    click.echo(f"Changes detected: {len(report.changes_detected)}")
    for change in report.changes_detected:
        if change.change_type == ChangeType.ADDED:
            click.secho(f"  + {change.key}", fg='green')
        elif change.change_type == ChangeType.MODIFIED:
            click.secho(f"  ~ {change.key}", fg='yellow')
        elif change.change_type == ChangeType.REMOVED:
            click.secho(f"  - {change.key}", fg='red')

    click.echo()

    if dry_run:
        click.secho("Dry run - no files modified.", fg='cyan')
        return

    if report.batch_result:
        click.echo(
            f"Translation complete: "
            f"{report.batch_result.successful} succeeded, "
            f"{report.batch_result.failed} failed"
        )

        if report.batch_result.failed > 0:
            click.echo("\nFailed translations:")
            for result in report.batch_result.results:
                if result.error:
                    click.secho(f"  {result.key}: {result.error}", fg='red')

        if verbose and report.batch_result.results:
            click.echo("\nTranslations:")
            for result in report.batch_result.results:
                if not result.error:
                    click.echo(f"\n  {result.key}:")
                    click.echo(f"    Source: {result.source_text}")
                    for lang, translation in result.translations.items():
                        click.echo(f"    {lang}: {translation}")

    if report.files_updated:
        click.echo("\nFiles updated:")
        for path in report.files_updated:
            click.secho(f"  {path}", fg='green')


@cli.command()
@click.argument('file', type=click.Path(exists=True, path_type=Path))
@click.option('--base', default='HEAD~1', help='Base git reference to compare against')
def diff(file: Path, base: str):
    """Show changes in a .strings file compared to a git reference.

    FILE is the path to the .strings file to analyze.
    """
    detector = DiffDetector()
    changes = detector.detect_changes(file, base_ref=base, head_ref="HEAD")

    if not changes:
        click.secho("No changes detected.", fg='yellow')
        return

    click.echo(f"Changes detected ({len(changes)} total):\n")

    added = [c for c in changes if c.change_type == ChangeType.ADDED]
    modified = [c for c in changes if c.change_type == ChangeType.MODIFIED]
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]

    if added:
        click.secho(f"Added ({len(added)}):", fg='green', bold=True)
        for change in added:
            click.echo(f"  + {change.key}")
            click.echo(f"    \"{change.new_value}\"")
        click.echo()

    if modified:
        click.secho(f"Modified ({len(modified)}):", fg='yellow', bold=True)
        for change in modified:
            click.echo(f"  ~ {change.key}")
            click.echo(f"    - \"{change.old_value}\"")
            click.echo(f"    + \"{change.new_value}\"")
        click.echo()

    if removed:
        click.secho(f"Removed ({len(removed)}):", fg='red', bold=True)
        for change in removed:
            click.echo(f"  - {change.key}")
            click.echo(f"    \"{change.old_value}\"")


@cli.command()
@click.argument('file', type=click.Path(exists=True, path_type=Path))
def parse(file: Path):
    """Parse and display entries from a .strings file.

    FILE is the path to the .strings file to parse.
    """
    parser = StringsParser()
    entries = parser.parse_file(file)

    if not entries:
        click.secho("No entries found.", fg='yellow')
        return

    click.echo(f"Entries ({len(entries)} total):\n")

    for entry in entries:
        if entry.comment:
            click.secho(f"/* {entry.comment} */", fg='cyan')
        click.echo(f'"{entry.key}" = "{entry.value}";')
        click.echo()


@cli.command()
def check():
    """Check if the translation backend is available."""
    config = TranslationConfig()
    service = TranslationService(config=config)

    ready, message = service.is_ready()

    if ready:
        click.secho("Translation backend is ready!", fg='green')
        click.echo(f"  Ollama URL: {config.ollama_url}")
        click.echo(f"  Model: {config.ollama_model}")
    else:
        click.secho(f"Error: {message}", fg='red')
        click.echo("\nTo fix this:")
        click.echo("  1. Make sure Ollama is running: ollama serve")
        click.echo(f"  2. Pull the model: ollama pull {config.ollama_model}")
        raise SystemExit(1)


if __name__ == '__main__':
    cli()
