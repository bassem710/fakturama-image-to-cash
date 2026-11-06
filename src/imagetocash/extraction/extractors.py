"""Spec 1.1: turn the order image into ExtractedOrder.

Two interchangeable implementations of the same protocol (Liskov):
- ClaudeVisionOrderExtractor: the real one (LLM vision + structured outputs).
- SavedJsonOrderExtractor:    replays a previous run's extracted.json (no API call, no cost),
                              so the UI flow can be iterated on quickly.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Protocol, cast

import anthropic
from anthropic.types.beta import BetaImageBlockParam, BetaMessageParam, BetaOutputConfigParam, BetaTextBlockParam

from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.schema import ExtractedOrder

EXTRACTION_INSTRUCTIONS = """\
This image is a single sales order. Extract every field of the schema from it.

Rules:
- Copy text, codes, numbers, percentages and dates EXACTLY as printed. Do not convert,
  round, reformat or translate them. Leave currency codes out of amount fields.
- SKUs are case- and character-exact: distinguish 0 (zero) from O and 1 from I or l.
- Split the contact name into first name and last name.
- Use null for optional fields that are not printed. Never invent a value.
- Items: one entry per printed item row, in printed order; skip empty table rows.
"""


class OrderExtractor(Protocol):
    def extract(self, image_path: Path) -> ExtractedOrder: ...


class ClaudeVisionOrderExtractor:
    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str = "claude-opus-5-5",
        effort: str = "high",
        use_refusal_fallbacks: bool = True,
    ) -> None:
        self._client = client
        self._model = model
        self._effort = effort
        self._use_refusal_fallbacks = use_refusal_fallbacks

    def extract(self, image_path: Path) -> ExtractedOrder:
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        image_block = cast(
            BetaImageBlockParam,
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
        )
        text_block: BetaTextBlockParam = {"type": "text", "text": EXTRACTION_INSTRUCTIONS}
        messages: list[BetaMessageParam] = [{"role": "user", "content": [image_block, text_block]}]
        output_config = cast(BetaOutputConfigParam, {"effort": self._effort})
        if self._use_refusal_fallbacks:
            # Server-side fallback: if Claude Opus 5.5 declines, the API re-runs the request on
            # Anthropic's recommended fallback model inside the same call.
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=16000,
                output_config=output_config,
                output_format=ExtractedOrder,
                messages=messages,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        else:
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=16000,
                output_config=output_config,
                output_format=ExtractedOrder,
                messages=messages,
            )
        if response.stop_reason == "refusal":
            raise ManualReviewRequired("1.1", ReviewReason.EXTRACTION_INVALID, "model declined the image")
        if response.parsed_output is None:
            raise ManualReviewRequired(
                "1.1", ReviewReason.EXTRACTION_INVALID, f"no structured output (stop: {response.stop_reason})"
            )
        return response.parsed_output


class SavedJsonOrderExtractor:
    """Replays a saved extraction. The image path is ignored on purpose."""

    def __init__(self, json_path: Path) -> None:
        self._json_path = json_path

    def extract(self, image_path: Path) -> ExtractedOrder:
        return ExtractedOrder.model_validate_json(self._json_path.read_text(encoding="utf-8"))
