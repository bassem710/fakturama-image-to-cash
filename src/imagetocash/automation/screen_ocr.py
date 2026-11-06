"""Windows OCR (Windows.Media.Ocr via winocr), always run on a rectangle UIA gave us."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageGrab

UPSCALE = 2  # UI text is small; 2x upscaling noticeably improves Windows OCR accuracy


@dataclass(frozen=True)
class ScreenRect:
    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def of(cls, element: Any) -> ScreenRect:
        r = element.rectangle()
        return cls(r.left, r.top, r.right, r.bottom)


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center(self) -> tuple[int, int]:
        return int((self.left + self.right) / 2), int((self.top + self.bottom) / 2)

    @property
    def middle_y(self) -> float:
        return (self.top + self.bottom) / 2


class WindowsScreenOcr:
    def __init__(self, language: str = "en") -> None:
        self._language = language

    def capture(self, rect: ScreenRect) -> Image.Image:
        return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)

    def read_words(self, rect: ScreenRect) -> list[OcrWord]:
        return self.read_image(self.capture(rect), rect)

    def read_image(self, image: Image.Image, rect: ScreenRect) -> list[OcrWord]:
        """OCR an image captured from `rect`; word boxes are returned in screen coordinates."""
        import winocr  # imported lazily: Windows-only runtime dependency

        image = image.resize((image.width * UPSCALE, image.height * UPSCALE), Image.Resampling.LANCZOS)
        result = winocr.recognize_pil_sync(image, self._language)
        words: list[OcrWord] = []
        for line in result["lines"]:
            for word in line["words"]:
                box = word["bounding_rect"]
                left = rect.left + box["x"] / UPSCALE
                top = rect.top + box["y"] / UPSCALE
                words.append(
                    OcrWord(word["text"], left, top, left + box["width"] / UPSCALE, top + box["height"] / UPSCALE)
                )
        return words


def group_into_rows(words: list[OcrWord], tolerance: float = 6.0) -> list[list[OcrWord]]:
    """Group words whose vertical middles are within `tolerance` px; rows top-to-bottom, words left-to-right."""
    rows: list[list[OcrWord]] = []
    for word in sorted(words, key=lambda w: w.middle_y):
        if rows and abs(rows[-1][0].middle_y - word.middle_y) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda w: w.left) for row in rows]
