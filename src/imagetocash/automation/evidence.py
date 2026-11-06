"""Per-run evidence: one log line per spec step (start, finish, problems), steps.jsonl, a final
report.md, and screenshots at the end of each stage and on any failure.

Everything written here is redacted (automation/run_log.py): values are masked, never stored in
clear text. Screenshots are taken in a background thread so they never slow the run down.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from imagetocash.automation.run_log import get_logger, redact
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
    _shots: list[threading.Thread] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def spec_step(self, spec_step: str, action: str, expected: str = "") -> Iterator[StepRecord]:
        log = get_logger()
        record = StepRecord(spec_step=spec_step, action=redact(action), expected=redact(expected))
        started = time.monotonic()
        try:
            yield record
            record.result = "ok"
        except ManualReviewRequired as stop:
            record.result = "review"
            record.detail = redact(f"{stop.reason}: {stop.detail}")
            raise
        except Exception as error:
            record.result = "error"
            record.detail = redact(f"{type(error).__name__}: {error}")
            raise
        finally:
            record.seconds = round(time.monotonic() - started, 2)
            record.observed = redact(record.observed)
            if record.result != "ok":
                record.screenshot = self.screenshot(f"{len(self.records) + 1:02d}_{spec_step}_failed")
            self.records.append(record)
            with (self.run_dir / "steps.jsonl").open("a", encoding="utf-8") as jsonl:
                jsonl.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            fields = {"spec_step": spec_step, "result": record.result, "seconds": record.seconds}
            line = f"{spec_step:<7} {record.action} ... {record.result.upper()} {record.seconds:.1f} s"
            if record.result == "ok":
                log.info(line, extra={"fields": fields})
            elif record.result == "review":
                log.warning(f"{line} -> manual review: {record.detail}", extra={"fields": fields})
            else:
                log.error(f"{line} -> {record.detail}", extra={"fields": fields})

    def stage_done(self, stage: str) -> None:
        """Screenshot after each stage (spec sections 1-5)."""
        self.screenshot(f"stage_{stage}")
        get_logger().info(f"stage {stage} done")

    def screenshot(self, name: str) -> str:
        """Capture in the background; evidence must never slow down or break the run."""
        if self.screenshotter is None:
            return ""
        filename = name.replace(".", "-") + ".png"
        target = self.run_dir / filename

        def capture() -> None:
            try:
                assert self.screenshotter is not None
                self.screenshotter(target)
            except Exception as error:
                get_logger().warning(f"screenshot {filename} failed: {type(error).__name__}")

        thread = threading.Thread(target=capture, daemon=True)
        thread.start()
        self._shots.append(thread)
        return filename

    def write_report(self, outcome: str) -> Path:
        for thread in self._shots:
            thread.join(timeout=10)
        icons = {"ok": "✔", "review": "✖ review", "error": "✖ error", "running": "…"}
        lines = [
            f"# Run report: {redact(outcome)}",
            "",
            "Values are masked (first/last character and length); see automation/run_log.py.",
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
        total = sum(r.seconds for r in self.records)
        get_logger().info(f"run finished: {redact(outcome)} ({len(self.records)} steps, {total:.0f} s)")
        return path
