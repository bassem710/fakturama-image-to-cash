"""GeminiVisionOrderExtractor against a fake google-genai client (no network)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from imagetocash.domain.review import ManualReviewRequired
from imagetocash.extraction.extractors import GeminiVisionOrderExtractor
from imagetocash.extraction.schema import ExtractedOrder

FIXTURE = Path(__file__).parent.parent / "fixtures" / "northstar_extracted.json"
IMAGE = Path(__file__).parent.parent.parent / "samples" / "order-page3.png"


class FakeModels:
    def __init__(self, response: Any) -> None:
        self.response, self.calls = response, []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def extractor_returning(response: Any) -> tuple[GeminiVisionOrderExtractor, FakeModels]:
    models = FakeModels(response)
    return GeminiVisionOrderExtractor(SimpleNamespace(models=models), model="gemini-test"), models  # type: ignore[arg-type]


def test_sends_image_with_schema_and_returns_parsed_order() -> None:
    expected = ExtractedOrder.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    extractor, models = extractor_returning(SimpleNamespace(parsed=expected, text=None, prompt_feedback=None))
    assert extractor.extract(IMAGE) == expected
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["contents"][0].inline_data.mime_type == "image/png"
    assert call["config"].response_schema is ExtractedOrder
    assert call["config"].response_mime_type == "application/json"


def test_falls_back_to_json_text() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    extractor, _ = extractor_returning(SimpleNamespace(parsed=None, text=text, prompt_feedback=None))
    assert extractor.extract(IMAGE).external_reference == "WEB-2026-0714-A17"


def test_blocked_or_empty_response_stops_at_1_1() -> None:
    blocked = SimpleNamespace(parsed=None, text=None, prompt_feedback=SimpleNamespace(block_reason="SAFETY"))
    extractor, _ = extractor_returning(blocked)
    with pytest.raises(ManualReviewRequired) as stop:
        extractor.extract(IMAGE)
    assert stop.value.spec_step == "1.1" and "SAFETY" in stop.value.detail
