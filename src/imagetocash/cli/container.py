"""Composition root: the only place that knows the concrete classes."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.cli.config import Settings
from imagetocash.extraction.extractors import (
    ClaudeVisionOrderExtractor,
    OrderExtractor,
    SavedJsonOrderExtractor,
)
from imagetocash.workflow.protocols import FakturamaUi
from imagetocash.workflow.runner import ImageToCashRunner


def build_extractor(settings: Settings, from_json: Path | None, model: str | None) -> OrderExtractor:
    if from_json is not None:
        return SavedJsonOrderExtractor(from_json)
    import anthropic
    from dotenv import load_dotenv

    load_dotenv()
    return ClaudeVisionOrderExtractor(
        anthropic.Anthropic(),
        model=model or settings.model,
        effort=settings.effort,
        use_refusal_fallbacks=settings.refusal_fallbacks,
    )


def new_run_dir(settings: Settings) -> Path:
    return settings.runs_dir / datetime.now().strftime("%Y%m%d-%H%M%S")


def screenshot_main_window(path: Path) -> None:
    from PIL import ImageGrab

    ImageGrab.grab(all_screens=True).save(path)


def build_runner(settings: Settings, from_json: Path | None, model: str | None) -> tuple[ImageToCashRunner, Path]:
    run_dir = new_run_dir(settings)
    evidence = EvidenceRecorder(run_dir, screenshotter=screenshot_main_window)

    def connect_ui() -> FakturamaUi:
        from imagetocash.fakturama.app import FakturamaApp

        return FakturamaApp.connect(settings)

    def start_app_early() -> None:
        """Boot the JVM (non-blocking) so it starts while the LLM reads the image."""
        if not _fakturama_running(settings.fakturama_exe):
            subprocess.Popen([str(settings.fakturama_exe)], cwd=str(settings.fakturama_exe.parent))

    runner = ImageToCashRunner(build_extractor(settings, from_json, model), connect_ui, evidence, start_app_early)
    return runner, run_dir


def _fakturama_running(exe: Path) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe.name}", "/NH"], capture_output=True, text=True, check=False
    ).stdout
    return exe.name.lower() in out.lower()
