"""Load config/settings.yaml into typed settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Timeouts:
    element: float = 10
    dialog: float = 15
    list_stable: float = 10
    app_start: float = 120


@dataclass(frozen=True)
class Settings:
    fakturama_exe: Path
    runs_dir: Path
    model: str
    fallback_models: tuple[str, ...]
    source_date_formats: tuple[str, ...]
    ui_date_format: str
    ocr_language: str
    timeouts: Timeouts
    selectors_path: Path


def load_settings(path: Path) -> Settings:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    extraction, ui = raw.get("extraction", {}), raw.get("ui", {})
    return Settings(
        fakturama_exe=Path(raw["fakturama_exe"]),
        runs_dir=Path(raw.get("runs_dir", "runs")),
        model=extraction.get("model", "gemini-flash-latest"),
        fallback_models=tuple(extraction.get("fallback_models", [])),
        source_date_formats=tuple(extraction.get("source_date_formats", ["%Y-%m-%d"])),
        ui_date_format=ui.get("date_format", "%b {day}, %Y"),
        ocr_language=ui.get("ocr_language", "en"),
        timeouts=Timeouts(**ui.get("timeouts", {})),
        selectors_path=path.parent / "selectors.yaml",
    )
