"""Spec 1.1: turn the order image into ExtractedOrder.

Two interchangeable implementations of the same protocol (Liskov):
- GeminiVisionOrderExtractor: the real one (Gemini vision + response schema).
- SavedJsonOrderExtractor:    replays a previous run's extracted.json (no API call, no cost),
                              so the UI flow can be iterated on quickly.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import types

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


class GeminiVisionOrderExtractor:
    """Gemini (Google AI Studio) vision with a response schema: the API returns JSON matching
    ExtractedOrder, which the SDK parses into the pydantic model."""

    def __init__(self, client: genai.Client, model: str = "gemini-flash-latest") -> None:
        self._client = client
        self._model = model

    def extract(self, image_path: Path) -> ExtractedOrder:
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        contents = types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type=media_type),
                types.Part.from_text(text=EXTRACTION_INSTRUCTIONS),
            ],
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedOrder,
                temperature=0,  # transcription, not creativity
            ),
        )
        if isinstance(response.parsed, ExtractedOrder):
            return response.parsed
        if response.text:
            try:
                return ExtractedOrder.model_validate_json(response.text)
            except ValueError as error:
                raise ManualReviewRequired("1.1", ReviewReason.EXTRACTION_INVALID, f"invalid JSON: {error}") from error
        feedback = response.prompt_feedback.block_reason if response.prompt_feedback else "empty response"
        raise ManualReviewRequired("1.1", ReviewReason.EXTRACTION_INVALID, f"no structured output ({feedback})")


class SavedJsonOrderExtractor:
    """Replays a saved extraction. The image path is ignored on purpose."""

    def __init__(self, json_path: Path) -> None:
        self._json_path = json_path

    def extract(self, image_path: Path) -> ExtractedOrder:
        return ExtractedOrder.model_validate_json(self._json_path.read_text(encoding="utf-8"))
