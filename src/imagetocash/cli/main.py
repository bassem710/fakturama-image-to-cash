"""Command line: `imagetocash run | extract | inspect`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from imagetocash.cli.config import load_settings
from imagetocash.cli.container import build_extractor, build_runner
from imagetocash.domain.review import ManualReviewRequired
from imagetocash.domain.validation import ensure_order_is_consistent
from imagetocash.extraction.mapper import to_order_document

app = typer.Typer(add_completion=False, help="Fakturama Image-to-Cash automation.")

ConfigOption = Annotated[Path, typer.Option("--config", help="settings.yaml")]
DEFAULT_CONFIG = Path("config/settings.yaml")


@app.command()
def run(
    image: Path,
    from_json: Annotated[Path | None, typer.Option(help="Replay a saved extracted.json (no LLM call)")] = None,
    model: Annotated[str | None, typer.Option(help="Gemini model id")] = None,
    config: ConfigOption = DEFAULT_CONFIG,
) -> None:
    """Spec 1.1 -> 5.7: image to a saved, verified Order and linked Invoice."""
    settings = load_settings(config)
    runner, run_dir = build_runner(settings, from_json, model)
    outcome = runner.run(image)
    typer.echo(f"{outcome.exit_code.name}: {outcome.message}")
    typer.echo(f"Evidence: {run_dir}  Report: {outcome.report}")
    raise typer.Exit(int(outcome.exit_code))


@app.command()
def extract(
    image: Path,
    model: Annotated[str | None, typer.Option(help="Gemini model id")] = None,
    out: Annotated[Path | None, typer.Option(help="Write the extraction JSON here")] = None,
    config: ConfigOption = DEFAULT_CONFIG,
) -> None:
    """Spec 1.1-1.2 only: print the normalized order and whether it is internally consistent."""
    settings = load_settings(config)
    extracted = build_extractor(settings, None, model).extract(image)
    payload = extracted.model_dump_json(indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
    typer.echo(payload)
    try:
        ensure_order_is_consistent(to_order_document(extracted, settings.source_date_formats))
    except ManualReviewRequired as stop:
        typer.echo(f"MANUAL REVIEW: {stop}")
        raise typer.Exit(2) from stop
    typer.echo("VALID")


@app.command()
def inspect(
    depth: Annotated[int, typer.Option(help="Max tree depth")] = 25,
    out: Annotated[Path | None, typer.Option(help="Write the dump to this file")] = None,
    config: ConfigOption = DEFAULT_CONFIG,
) -> None:
    """Dump Fakturama's UI Automation tree (main window + open dialogs) for control mapping."""
    from imagetocash.automation.session import DesktopSession
    from imagetocash.automation.tree_dump import dump_tree

    settings = load_settings(config)
    session = DesktopSession.attach_or_launch(settings.fakturama_exe, timeout=settings.timeouts.app_start)
    session.bring_to_front()
    parts = [dump_tree(session.main_wrapper(), depth)]
    parts += [f"=== DIALOG {d.element_info.name!r}\n{dump_tree(d, depth)}" for d in session.dialogs()]
    text = "\n".join(parts)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
