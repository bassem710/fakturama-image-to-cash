"""Per-run evidence: one JSON line + one screenshot per spec step, and a final report.md."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from imagetocash.domain.review import ManualReviewRequired

Screenshotter = Callable[[Path], None]


@dataclass
class StepRecord:
    spec_step: str
    action: str
    expected: str = ""
    observed: str = ""
    result: str = "running"  # ok | review | error
    detail: str = ""
    seconds: float = 0.0
    screenshot: str = ""


@dataclass
class EvidenceRecorder:
    run_dir: Path
    screenshotter: Screenshotter | None = None
    records: list[StepRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def spec_step(self, spec_step: str, action: str, expected: str = "") -> Iterator[StepRecord]:
        record = StepRecord(spec_step=spec_step, action=action, expected=expected)
        started = time.monotonic()
        try:
            yield record
            record.result = "ok"
        except ManualReviewRequired as stop:
            record.result, record.detail = "review", str(stop)
            raise
        except Exception as error:
            record.result, record.detail = "error", f"{type(error).__name__}: {error}"
            raise
        finally:
            record.seconds = round(time.monotonic() - started, 2)
            self._screenshot(record)
            self.records.append(record)
            with (self.run_dir / "steps.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def _screenshot(self, record: StepRecord) -> None:
        if self.screenshotter is None:
            return
        name = f"{len(self.records) + 1:02d}_{record.spec_step.replace('.', '-')}.png"
        try:
            self.screenshotter(self.run_dir / name)
            record.screenshot = name
        except Exception as error:  # evidence must never break the run
            record.detail += f" (screenshot failed: {error})"

    def write_report(self, outcome: str) -> Path:
        icons = {"ok": "✔", "review": "✖ review", "error": "✖ error", "running": "…"}
        lines = [
            f"# Run report: {outcome}",
            "",
            "| # | Spec | Action | Expected | Observed | Result | s | Screenshot |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for n, r in enumerate(self.records, 1):
            cells = [
                str(n),
                r.spec_step,
                r.action,
                r.expected,
                r.observed,
                f"{icons.get(r.result, r.result)} {r.detail}".strip(),
                str(r.seconds),
                r.screenshot,
            ]
            lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        path = self.run_dir / "report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
