"""Composition root: the only place that knows the concrete classes."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.automation.run_log import setup_run_logging
from imagetocash.cli.config import Settings
from imagetocash.extraction.extractors import (
    GeminiVisionOrderExtractor,
    OrderExtractor,
    SavedJsonOrderExtractor,
    gemini_client,
)
from imagetocash.workflow.protocols import FakturamaUi
from imagetocash.workflow.runner import ImageToCashRunner


def build_extractor(settings: Settings, from_json: Path | None, model: str | None) -> OrderExtractor:
    if from_json is not None:
        return SavedJsonOrderExtractor(from_json)
    import os

    from dotenv import load_dotenv

    load_dotenv()
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("Set GEMINI_API_KEY in .env (Google AI Studio key), or pass --from-json")
    return GeminiVisionOrderExtractor(
        gemini_client(), model=model or settings.model, fallback_models=settings.fallback_models
    )


def new_run_dir(settings: Settings) -> Path:
    return settings.runs_dir / datetime.now().strftime("%Y%m%d-%H%M%S")


def screenshot_main_window(path: Path) -> None:
    """Screen capture as compressed PNG (local runs/ only; contains order data, git-ignored)."""
    from PIL import ImageGrab

    ImageGrab.grab(all_screens=True).save(path, optimize=False, compress_level=1)


def build_runner(settings: Settings, from_json: Path | None, model: str | None) -> tuple[ImageToCashRunner, Path]:
    run_dir = new_run_dir(settings)
    setup_run_logging(run_dir)
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
