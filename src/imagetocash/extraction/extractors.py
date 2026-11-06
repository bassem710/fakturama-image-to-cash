"""Spec 1.1: turn the order image into ExtractedOrder.

Two interchangeable implementations of the same protocol (Liskov):
- GeminiVisionOrderExtractor: the real one (Gemini vision + response schema).
- SavedJsonOrderExtractor:    replays a previous run's extracted.json (no API call, no cost),
                              so the UI flow can be iterated on quickly.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import httpx
from google import genai
from google.genai import errors, types

from imagetocash.automation.run_log import get_logger
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


RETRYABLE_STATUS = (429, 500, 502, 503, 504)
NEXT_MODEL_STATUS = (*RETRYABLE_STATUS, 404)  # 404: model retired or not offered to this key


def gemini_client() -> genai.Client:
    """Reads GEMINI_API_KEY; retries rate limits and overloads with exponential backoff."""
    retry = types.HttpRetryOptions(
        attempts=4, initial_delay=2.0, max_delay=20.0, http_status_codes=list(RETRYABLE_STATUS)
    )
    return genai.Client(http_options=types.HttpOptions(timeout=60_000, retry_options=retry))


class OrderExtractor(Protocol):
    def extract(self, image_path: Path) -> ExtractedOrder: ...


class GeminiVisionOrderExtractor:
    """Gemini (Google AI Studio) vision with a response schema: the API returns JSON matching
    ExtractedOrder, which the SDK parses into the pydantic model."""

    def __init__(
        self, client: genai.Client, model: str = "gemini-flash-latest", fallback_models: Sequence[str] = ()
    ) -> None:
        self._client = client
        self._models = (model, *fallback_models)

    def extract(self, image_path: Path) -> ExtractedOrder:
        """Try each model in order. The client already retries 429/5xx with backoff; a model that is
        still overloaded after that hands over to the next one."""
        last_error: Exception | None = None
        for model in self._models:
            get_logger().info(f"1.1     reading the image with {model}")
            try:
                return self._extract_with(model, image_path)
            except errors.APIError as error:
                if error.code not in NEXT_MODEL_STATUS:
                    raise
                last_error = error
            except httpx.TransportError as error:  # dropped connection / timeout
                last_error = error
            get_logger().warning(f"1.1     {model} unavailable ({type(last_error).__name__}), trying the next model")
        raise ManualReviewRequired(
            "1.1", ReviewReason.EXTRACTION_INVALID, f"every Gemini model unavailable ({last_error})"
        )

    def _extract_with(self, model: str, image_path: Path) -> ExtractedOrder:
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        contents = types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type=media_type),
                types.Part.from_text(text=EXTRACTION_INSTRUCTIONS),
            ],
        )
        response = self._client.models.generate_content(
            model=model,
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
